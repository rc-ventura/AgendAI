"""B4 (ADR-025): Redis cache backend for LangGraph.

Builds and returns a RedisCache instance if REDIS_URI is configured,
otherwise returns None (no caching).
"""
import logging
import os

logger = logging.getLogger(__name__)


def build_cache():
    """Build Redis cache for LangGraph if REDIS_URI is configured.

    Returns:
        RedisCache instance if Redis is available, None otherwise.
    """
    uri = os.getenv("REDIS_URI")
    if not uri:
        logger.info("cache=disabled reason=no_redis_uri")
        return None
    try:
        import redis.asyncio as aioredis
        from langgraph.cache.redis import RedisCache

        client = aioredis.from_url(uri)
        logger.info("cache=redis prefix=langgraph:cache:")
        return RedisCache(redis=client, prefix="langgraph:cache:")
    except Exception:
        logger.warning("cache=disabled reason=build_failed", exc_info=True)
        return None
