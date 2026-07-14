import json
import pymysql
import pandas as pd
from flask import Blueprint, jsonify, request, Response
from settings import logger
from database import get_mysql_connection
from cache import redis_client, clear_terminals_cache

# Δημιουργία του Blueprint για τα terminals
terminals_bp = Blueprint("terminals", __name__)

@terminals_bp.get("/terminals")
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


@terminals_bp.get("/terminals/<tid>")
def get_terminal(tid):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    t.id, t.tid, t.merchant_id, m.mid, t.template_id,
                    t.serial_number, t.software_version, t.sdk_version,
                    t.scenario_number, t.hardware_model, t.hardware_family,
                    t.enabled, t.created_on, t.last_call_stamp, t.updated_on
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


@terminals_bp.get("/terminals/flagged")
def list_flagged_terminals():
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    t.id, t.tid, t.merchant_id, m.mid, t.template_id,
                    t.serial_number, t.software_version, t.sdk_version,
                    t.scenario_number, t.hardware_model, t.hardware_family,
                    t.enabled, t.created_on, t.last_call_stamp, t.updated_on
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


@terminals_bp.post("/terminals/<tid>/flag")
def flag_terminal(tid):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "scenario_number" not in data:
        return jsonify({"error": "scenario_number is required"}), 400

    new_scenario = str(data["scenario_number"])

    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            # 1. Παίρνουμε την τρέχουσα τιμή για το logging
            cursor.execute("SELECT scenario_number FROM terminals WHERE tid = %s", (tid,))
            terminal = cursor.fetchone()
            if terminal is None:
                return jsonify({"error": "Not found"}), 404

            old_scenario = terminal["scenario_number"] or "NULL"

            # 2. Ενημερώνουμε με τη νέα τιμή
            cursor.execute(
                """
                UPDATE terminals
                SET scenario_number = %s, updated_on = NOW()
                WHERE tid = %s
                """,
                (new_scenario, tid),
            )

        db_connection.commit()

        # 3. Καταγραφή στα logs της αλλαγής (από την παλιά στη νέα τιμή)
        logger.info("Flagged terminal %s: Changed scenario_number from '%s' to '%s'", tid, old_scenario, new_scenario)
        clear_terminals_cache()

        return jsonify({"message": "Terminal flagged", "tid": tid, "scenario_number": new_scenario})
    except pymysql.MySQLError:
        if "db_connection" in locals():
            db_connection.rollback()
        logger.exception("Database error while flagging terminal %s", tid)
        return jsonify({"error": "Internal server error"}), 500


@terminals_bp.post("/terminals/<tid>/unflag")
def unflag_terminal(tid):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT scenario_number FROM terminals WHERE tid = %s", (tid,))
            terminal = cursor.fetchone()

            # ΔΙΟΡΘΩΘΗΚΕ: Έλεγχος αν το terminal βρέθηκε χωρίς διπλό fetchone()
            if terminal is None:
                return jsonify({"error": "Not found"}), 404

            old_scenario = terminal["scenario_number"] or "NULL"

            cursor.execute(
                """
                UPDATE terminals
                SET scenario_number = '0', updated_on = NOW()
                WHERE tid = %s
                """,
                (tid,),
            )

        db_connection.commit()
        logger.info("Unflagged terminal %s: Changed scenario_number from '%s' to '0'", tid, old_scenario)
        clear_terminals_cache()
        return jsonify({"message": "Terminal unflagged", "tid": tid})
    except pymysql.MySQLError:
        if "db_connection" in locals():
            db_connection.rollback()
        logger.exception("Database error while unflagging terminal %s", tid)
        return jsonify({"error": "Internal server error"}), 500


@terminals_bp.post("/terminals/<tid>/decommission")
def decommission_terminal(tid):
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT enabled FROM terminals WHERE tid = %s", (tid,))
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


# GET /terminals/decommissioned (Feature A5 - Βοηθητικό endpoint)
@terminals_bp.get("/terminals/decommissioned")
def list_decommissioned_terminals():
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    tid,
                    queued_on,
                    delete_after,
                    ROUND(TIMESTAMPDIFF(SECOND, NOW(), delete_after) / 86400.0, 2) AS days_remaining
                FROM decommission_queue
                ORDER BY delete_after ASC
                """
            )
            queue = cursor.fetchall()
        return jsonify(queue)
    except pymysql.MySQLError:
        logger.exception("Database error while listing decommissioned terminals")
        return jsonify({"error": "Internal server error"}), 500


# GET /terminals/csv (BONUS: Daily CSV report)
@terminals_bp.get("/terminals/csv")
def export_terminals_csv():
    try:
        db_connection = get_mysql_connection()
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tid, hardware_model, hardware_family, software_version, enabled, last_call_stamp
                FROM terminals
                """
            )
            terminals = cursor.fetchall()

        df = pd.DataFrame(terminals)
        csv_data = df.to_csv(index=False)

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=terminals_basic.csv"}
        )
    except Exception:
        logger.exception("Error while generating CSV report")
        return jsonify({"error": "Internal server error"}), 500


@terminals_bp.post("/terminals/from-template")
def create_terminal_from_template():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "template_id and mid are required"}), 400

    template_id = data.get("template_id")
    mid = data.get("mid")
    if not isinstance(template_id, int) or isinstance(template_id, bool) or not isinstance(mid, str) or not mid:
        return jsonify({"error": "template_id must be an integer and mid must be a string"}), 400

    db_connection = None

    try:
        db_connection = get_mysql_connection()
        db_connection.begin()

        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT hardware_model, hardware_family FROM templates WHERE id = %s",
                (template_id,),
            )
            template = cursor.fetchone()

            if template is None:
                db_connection.rollback()
                return jsonify({"error": "Template not found"}), 404

            cursor.execute("SELECT id FROM merchants WHERE mid = %s", (mid,))
            merchant = cursor.fetchone()

            if merchant is None:
                db_connection.rollback()
                return jsonify({"error": "Merchant not found"}), 404

            merchant_id = merchant["id"]
            cursor.execute(
                "SELECT MAX(tid) AS max_tid FROM terminals WHERE merchant_id = %s",
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
                    tid, merchant_id, template_id, hardware_model, hardware_family, enabled, created_on
                )
                VALUES (%s, %s, %s, %s, %s, 1, NOW())
                """,
                (new_tid, merchant_id, template_id, template["hardware_model"], template["hardware_family"]),
            )

        db_connection.commit()
        logger.info("Created terminal %s from template %s for merchant %s", new_tid, template_id, mid)
        clear_terminals_cache()
        return jsonify({"message": "Terminal created", "tid": new_tid}), 201
    except pymysql.MySQLError:
        if db_connection is not None:
            db_connection.rollback()
        logger.exception("Database error while creating terminal from template %s", template_id)
        return jsonify({"error": "Internal server error"}), 500
