import logging
import os
import sys

import pymysql
import redis
from dotenv import load_dotenv
from flask import Flask, jsonify, request


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

mysql_connection = None
redis_client = None


def create_mysql_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
    )


def create_redis_client():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD") or None,
        socket_connect_timeout=5,
        socket_timeout=5,
        decode_responses=True,
    )


def setup_database(db_connection):
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS column_exists
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            """,
            ("terminals", "updated_on"),
        )
        result = cursor.fetchone()

        if result["column_exists"] == 0:
            cursor.execute("ALTER TABLE terminals ADD COLUMN updated_on DATETIME")
            logger.info("Added terminals.updated_on column")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS decommission_queue (
                tid VARCHAR(20) NOT NULL PRIMARY KEY,
                queued_on DATETIME,
                delete_after DATETIME,
                FOREIGN KEY (tid) REFERENCES terminals(tid)
            )
            """
        )

    db_connection.commit()


def get_mysql_connection():
    global mysql_connection

    if mysql_connection is None or not mysql_connection.open:
        mysql_connection = create_mysql_connection()

    return mysql_connection


def initialize_mysql():
    global mysql_connection

    try:
        mysql_connection = create_mysql_connection()
        with mysql_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        setup_database(mysql_connection)
        logger.info("MySQL connection initialized")
    except Exception:
        mysql_connection = None
        logger.exception("MySQL connection failed during startup")


def initialize_redis():
    global redis_client

    try:
        redis_client = create_redis_client()
        redis_client.ping()
        logger.info("Redis connection initialized")
    except Exception:
        logger.exception("Redis connection failed during startup")


def check_mysql():
    global mysql_connection

    try:
        db_connection = get_mysql_connection()

        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return True
    except Exception:
        logger.exception("MySQL healthcheck failed")
        mysql_connection = None
        return False


def check_redis():
    global redis_client

    try:
        if redis_client is None:
            redis_client = create_redis_client()

        return bool(redis_client.ping())
    except Exception:
        logger.exception("Redis healthcheck failed")
        return False


@app.errorhandler(Exception)
def handle_exception(error):
    logger.exception("Unhandled exception: %s", error)
    return jsonify({"error": "Internal server error"}), 500


@app.get("/health")
def health():
    mysql_is_up = check_mysql()
    redis_is_up = check_redis()
    status_code = 200 if mysql_is_up and redis_is_up else 503

    return (
        jsonify(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "mysql": "up" if mysql_is_up else "down",
                "redis": "up" if redis_is_up else "down",
            }
        ),
        status_code,
    )


@app.get("/terminals")
def list_terminals():
    enabled = request.args.get("enabled")
    query = """
        SELECT
            t.tid,
            m.mid,
            t.hardware_model,
            t.software_version,
            t.enabled,
            t.last_call_stamp AS last_call
        FROM terminals t
        JOIN merchants m ON m.id = t.merchant_id
    """
    params = ()

    if enabled is not None:
        enabled_value = enabled.lower()
        if enabled_value not in ("true", "false"):
            return jsonify({"error": "enabled must be true or false"}), 400

        query += " WHERE t.enabled = %s"
        params = (1 if enabled_value == "true" else 0,)

    query += " ORDER BY t.tid"

    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(query, params)
            terminals = cursor.fetchall()

        return jsonify(terminals)
    except pymysql.MySQLError:
        logger.exception("Database error while listing terminals")
        return jsonify({"error": "Internal server error"}), 500


@app.get("/terminals/<tid>")
def get_terminal(tid):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    t.id,
                    t.tid,
                    t.merchant_id,
                    m.mid,
                    t.template_id,
                    t.serial_number,
                    t.software_version,
                    t.sdk_version,
                    t.scenario_number,
                    t.hardware_model,
                    t.hardware_family,
                    t.enabled,
                    t.created_on,
                    t.last_call_stamp,
                    t.updated_on
                FROM terminals t
                JOIN merchants m ON m.id = t.merchant_id
                WHERE t.tid = %s
                """,
                (tid,),
            )
            terminal = cursor.fetchone()

        if terminal is None:
            return jsonify({"error": "Not found"}), 404

        return jsonify(terminal)
    except pymysql.MySQLError:
        logger.exception("Database error while fetching terminal %s", tid)
        return jsonify({"error": "Internal server error"}), 500


initialize_mysql()
initialize_redis()


if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_HOST", "0.0.0.0"), port=int(os.getenv("FLASK_PORT", "5000")))
