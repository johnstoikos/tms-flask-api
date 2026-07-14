import pymysql
from flask import Blueprint, jsonify
from settings import logger
from database import get_mysql_connection

# Δημιουργία του Blueprint για τα templates
templates_bp = Blueprint("templates", __name__)

@templates_bp.get("/templates")
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

@templates_bp.get("/templates/<template_id>")
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
