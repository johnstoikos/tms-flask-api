import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd
import pymysql
import redis
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


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


def get_terminals_df():
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    tid,
                    hardware_model,
                    hardware_family,
                    enabled,
                    last_call_stamp
                FROM terminals
                """
            )
            terminals = cursor.fetchall()

        return pd.DataFrame(terminals)
    except pymysql.MySQLError as error:
        raise error


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


def clear_terminals_cache():
    try:
        redis_client.flushdb()
    except Exception:
        logger.warning("Redis is down, couldn't clear cache")


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
    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code

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


@app.get("/stats/by-hardware")
def stats_by_hardware():
    try:
        terminals_df = get_terminals_df()
        terminals_df["hardware_model"] = terminals_df["hardware_model"].fillna(
            "Unknown"
        )
        hardware_counts = terminals_df.groupby("hardware_model").size().to_dict()
        return jsonify(hardware_counts)
    except Exception:
        logger.exception("Error while calculating hardware statistics")
        return jsonify({"error": "Internal server error"}), 500


@app.get("/stats/by-hardware-family")
def stats_by_hardware_family():
    try:
        terminals_df = get_terminals_df()
        terminals_df["hardware_family"] = terminals_df["hardware_family"].fillna(
            "Unknown"
        )
        family_counts = terminals_df.groupby("hardware_family").size().to_dict()
        return jsonify(family_counts)
    except Exception:
        logger.exception("Error while calculating hardware family statistics")
        return jsonify({"error": "Internal server error"}), 500


@app.get("/stats/by-state")
def stats_by_state():
    try:
        terminals_df = get_terminals_df()
        terminals_df["state"] = (
            terminals_df["enabled"]
            .map({1: "Active", 0: "Inactive"})
            .fillna("Unknown")
        )
        state_counts = terminals_df.groupby("state").size().to_dict()
        return jsonify(state_counts)
    except Exception:
        logger.exception("Error while calculating terminal state statistics")
        return jsonify({"error": "Internal server error"}), 500


@app.get("/stats/idle-distribution")
def stats_idle_distribution():
    try:
        terminals_df = get_terminals_df()
        last_calls = pd.to_datetime(terminals_df["last_call_stamp"], errors="coerce")
        idle_hours = (datetime.now() - last_calls).dt.total_seconds() / 3600
        categories = ["0-24h", "1-7 days", "7+ days", "Never"]

        terminals_df["idle_category"] = "Never"
        has_called = idle_hours.notna()
        terminals_df.loc[has_called, "idle_category"] = pd.cut(
            idle_hours[has_called],
            bins=[-float("inf"), 24, 168, float("inf")],
            labels=categories[:3],
            include_lowest=True,
        ).astype("string")

        idle_counts = (
            terminals_df.groupby("idle_category")
            .size()
            .reindex(categories, fill_value=0)
            .to_dict()
        )
        return jsonify(idle_counts)
    except Exception:
        logger.exception("Error while calculating idle distribution statistics")
        return jsonify({"error": "Internal server error"}), 500


@app.get("/terminals")
def list_terminals():
    enabled = request.args.get("enabled")
    enabled_value = None

    if enabled is not None:
        enabled_value = enabled.lower()
        if enabled_value not in ("true", "false"):
            return jsonify({"error": "enabled must be true or false"}), 400

    cache_key = f"cache_terminals_{enabled_value}"

    try:
        cached_terminals = redis_client.get(cache_key)
        if cached_terminals is not None:
            logger.info("Cache HIT")
            return jsonify(json.loads(cached_terminals))
    except Exception:
        logger.warning("Redis is down, couldn't read cache")

    logger.info("Cache MISS")
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

    if enabled_value is not None:
        query += " WHERE t.enabled = %s"
        params = (1 if enabled_value == "true" else 0,)

    query += " ORDER BY t.tid"

    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(query, params)
            terminals = cursor.fetchall()

        try:
            json_data = json.dumps(terminals, default=str)
            redis_client.setex(cache_key, 30, json_data)
        except Exception:
            logger.warning("Redis is down, couldn't write cache")

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


@app.get("/templates")
def list_templates():
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, template_name, hardware_model, hardware_family
                FROM templates
                ORDER BY id
                """
            )
            templates = cursor.fetchall()

        return jsonify(templates)
    except pymysql.MySQLError:
        logger.exception("Database error while listing templates")
        return jsonify({"error": "Internal server error"}), 500


@app.get("/templates/<template_id>")
def get_template(template_id):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, template_name, hardware_model, hardware_family
                FROM templates
                WHERE id = %s
                """,
                (template_id,),
            )
            template = cursor.fetchone()

        if template is None:
            return jsonify({"error": "Not found"}), 404

        return jsonify(template)
    except pymysql.MySQLError:
        logger.exception("Database error while fetching template %s", template_id)
        return jsonify({"error": "Internal server error"}), 500


@app.post("/terminals/from-template")
def create_terminal_from_template():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "template_id and mid are required"}), 400

    template_id = data.get("template_id")
    mid = data.get("mid")
    if (
        not isinstance(template_id, int)
        or isinstance(template_id, bool)
        or not isinstance(mid, str)
        or not mid
    ):
        return jsonify(
            {"error": "template_id must be an integer and mid must be a string"}
        ), 400

    db_connection = None

    try:
        db_connection = get_mysql_connection()
        db_connection.begin()

        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT hardware_model, hardware_family
                FROM templates
                WHERE id = %s
                """,
                (template_id,),
            )
            template = cursor.fetchone()

            if template is None:
                db_connection.rollback()
                return jsonify({"error": "Template not found"}), 404

            cursor.execute(
                "SELECT id FROM merchants WHERE mid = %s",
                (mid,),
            )
            merchant = cursor.fetchone()

            if merchant is None:
                db_connection.rollback()
                return jsonify({"error": "Merchant not found"}), 404

            merchant_id = merchant["id"]
            cursor.execute(
                """
                SELECT MAX(tid) AS max_tid
                FROM terminals
                WHERE merchant_id = %s
                """,
                (merchant_id,),
            )
            terminal = cursor.fetchone()
            previous_tid = terminal["max_tid"] if terminal else None

            if previous_tid is None:
                new_tid = f"T{mid[-4:]}001"
            else:
                next_number = int(previous_tid[-3:]) + 1
                new_tid = f"{previous_tid[:-3]}{next_number:03d}"

            cursor.execute(
                """
                INSERT INTO terminals (
                    tid,
                    merchant_id,
                    template_id,
                    hardware_model,
                    hardware_family,
                    enabled,
                    created_on
                )
                VALUES (%s, %s, %s, %s, %s, 1, NOW())
                """,
                (
                    new_tid,
                    merchant_id,
                    template_id,
                    template["hardware_model"],
                    template["hardware_family"],
                ),
            )

        db_connection.commit()
        logger.info(
            "Created terminal %s from template %s for merchant %s",
            new_tid,
            template_id,
            mid,
        )
        clear_terminals_cache()
        return jsonify({"message": "Terminal created", "tid": new_tid}), 201
    except pymysql.MySQLError:
        if db_connection is not None:
            db_connection.rollback()
        logger.exception(
            "Database error while creating terminal from template %s", template_id
        )
        return jsonify({"error": "Internal server error"}), 500


@app.get("/terminals/flagged")
def list_flagged_terminals():
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
                WHERE t.scenario_number IS NOT NULL
                  AND t.scenario_number <> ''
                  AND t.scenario_number <> '0'
                ORDER BY t.tid
                """
            )
            terminals = cursor.fetchall()

        return jsonify(terminals)
    except pymysql.MySQLError:
        logger.exception("Database error while listing flagged terminals")
        return jsonify({"error": "Internal server error"}), 500


@app.post("/terminals/<tid>/flag")
def flag_terminal(tid):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "scenario_number" not in data:
        return jsonify({"error": "scenario_number is required"}), 400

    scenario_number = data["scenario_number"]

    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM terminals WHERE tid = %s", (tid,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Not found"}), 404

            cursor.execute(
                """
                UPDATE terminals
                SET scenario_number = %s, updated_on = NOW()
                WHERE tid = %s
                """,
                (scenario_number, tid),
            )

        db_connection.commit()
        logger.info(
            "Flagged terminal %s with scenario_number %s", tid, scenario_number
        )
        clear_terminals_cache()
        return jsonify(
            {
                "message": "Terminal flagged",
                "tid": tid,
                "scenario_number": scenario_number,
            }
        )
    except pymysql.MySQLError:
        if "db_connection" in locals():
            db_connection.rollback()
        logger.exception("Database error while flagging terminal %s", tid)
        return jsonify({"error": "Internal server error"}), 500


@app.post("/terminals/<tid>/unflag")
def unflag_terminal(tid):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM terminals WHERE tid = %s", (tid,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Not found"}), 404

            cursor.execute(
                """
                UPDATE terminals
                SET scenario_number = '0', updated_on = NOW()
                WHERE tid = %s
                """,
                (tid,),
            )

        db_connection.commit()
        logger.info("Unflagged terminal %s", tid)
        clear_terminals_cache()
        return jsonify({"message": "Terminal unflagged", "tid": tid})
    except pymysql.MySQLError:
        if "db_connection" in locals():
            db_connection.rollback()
        logger.exception("Database error while unflagging terminal %s", tid)
        return jsonify({"error": "Internal server error"}), 500


@app.post("/terminals/<tid>/decommission")
def decommission_terminal(tid):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT enabled FROM terminals WHERE tid = %s", (tid,)
            )
            terminal = cursor.fetchone()

            if terminal is None:
                return jsonify({"error": "Not found"}), 404

            if terminal["enabled"] == 0:
                return jsonify({"error": "Terminal is already decommissioned"}), 409

            cursor.execute(
                """
                UPDATE terminals
                SET enabled = 0, updated_on = NOW()
                WHERE tid = %s
                """,
                (tid,),
            )
            cursor.execute(
                """
                INSERT INTO decommission_queue (tid, queued_on, delete_after)
                VALUES (%s, NOW(), NOW() + INTERVAL 3 DAY)
                """,
                (tid,),
            )

        db_connection.commit()
        logger.info("Decommissioned terminal %s", tid)
        clear_terminals_cache()
        return jsonify({"message": "Terminal decommissioned", "tid": tid})
    except pymysql.MySQLError:
        if "db_connection" in locals():
            db_connection.rollback()
        logger.exception("Database error while decommissioning terminal %s", tid)
        return jsonify({"error": "Internal server error"}), 500


initialize_mysql()
initialize_redis()


if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_HOST", "0.0.0.0"), port=int(os.getenv("FLASK_PORT", "5000")))
