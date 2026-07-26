# app/services/rate_limit.py
# Redis-backed fixed-window per-IP rate limiting for public unauthenticated
# endpoints (signup-firm, demo-request). Reuses the same redis instance
# already running for OAuth temp-token storage (app/api/auth.py) rather than
# an in-memory counter, which would reset per gunicorn worker process.
import redis
from fastapi import Request

_redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)


def get_client_ip(request: Request) -> str:
    """
    Real client IP behind nginx: X-Forwarded-For's first hop.
    Falls back to request.client.host for local dev with no reverse proxy.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """
    Fixed-window counter. Returns True if the request is within the limit
    (and increments the counter), False if the limit has been exceeded.
    """
    count = _redis_client.incr(key)
    if count == 1:
        _redis_client.expire(key, window_seconds)
    return count <= limit
