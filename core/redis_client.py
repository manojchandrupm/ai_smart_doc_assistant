import redis
from config import env

# redis-py v7+ removed the `ssl` kwarg from ConnectionPool.
# This Redis Cloud endpoint uses plain TCP (no SSL on this port).
_REDIS_URL = (
    f"redis://:{env.REDIS_PASSWORD}@{env.REDIS_HOST}:{env.REDIS_PORT}/0"
)

_client: redis.Redis | None = None

def get_redis() -> redis.Redis:
    """Return a lazily-initialised Redis client (decode_responses=True)."""
    global _client
    if _client is None:
        _client = redis.from_url(
            _REDIS_URL,
            decode_responses=True,  # always return str, not bytes
        )
    return _client