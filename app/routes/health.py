from flask import Blueprint, jsonify
from database import check_mysql
from cache import check_redis

# Δημιουργία του Blueprint για το health check
health_bp = Blueprint("health", __name__)

@health_bp.get("/health")
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
