import os

import redis

from settings import logger


redis_client = None


def create_redis_client():
    """Create a Redis client using the application environment."""
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD") or None,
        socket_connect_timeout=5,
        socket_timeout=5,
        decode_responses=True,
    )


def initialize_redis():
    """Initialize Redis during application startup."""
    global redis_client

    try:
        redis_client = create_redis_client()
        redis_client.ping()
        logger.info("Redis connection initialized")
    except Exception:
        redis_client = None
        logger.exception("Redis connection failed during startup")


def check_redis():
    """Return whether Redis is currently reachable."""
    global redis_client

    try:
        if redis_client is None:
            redis_client = create_redis_client()
        return bool(redis_client.ping())
    except Exception:
        logger.exception("Redis healthcheck failed")
        redis_client = None
        return False


def clear_terminals_cache():
    """Invalidate cached terminal and statistics responses."""
    try:
        if redis_client is None:
            raise redis.ConnectionError("Redis client is not initialized")
        redis_client.flushdb()
    except Exception:
        logger.warning("Redis is down, couldn't clear cache")
