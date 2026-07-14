import os
import pymysql
import pandas as pd
from settings import logger

# Global μεταβλητή για το database connection
mysql_connection = None

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
