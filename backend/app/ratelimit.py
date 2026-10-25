import logging
import time

import redis

from app.config import get_settings

log = logging.getLogger(__name__)
_redis: redis.Redis | None = None


def redis_client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(get_settings().redis_url)
    return _redis


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window rate limiter. Returns True if the call is allowed."""
    client = redis_client()
    try:
        now = int(time.time())
        window_key = f"{key}:{now // window_seconds}"
        count = client.incr(window_key)
        if count == 1:
            client.expire(window_key, window_seconds * 2)
        allowed = count <= limit
        if not allowed:
            log.warning("rate limit hit for %s (%d/%d)", key, count, limit)
        return allowed
    except Exception:
        log.exception("redis unavailable; allowing call for %s", key)
        return True


class RateLimitExceeded(RuntimeError):
    pass
