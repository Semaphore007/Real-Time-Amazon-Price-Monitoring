"""
Redis cache wrapper for the price monitoring API.

Features:
  - Async aioredis client
  - JSON serialisation with datetime support
  - TTL-keyed get/set with automatic prefix namespacing
  - Graceful degradation: cache miss (not crash) when Redis is unavailable
  - cache_response() decorator for use on async route handlers
"""
from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request, Response

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 120  # seconds
_PREFIX = "amazon_monitor"


class _DatetimeEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class RedisCache:
    """
    Thin async Redis wrapper.

    Usage::
        cache = RedisCache("redis://localhost:6379/0")
        await cache.connect()
        await cache.set("key", {"data": 1}, ttl=60)
        val = await cache.get("key")   # dict or None
    """

    def __init__(self, url: str) -> None:
        self.url  = url
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        try:
            self._redis = await aioredis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._redis.ping()
            logger.info("Redis cache connected → %s", self.url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable (%s) — caching disabled", exc)
            self._redis = None

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    # ── Key helpers ───────────────────────────────────────────────────────────

    def _key(self, key: str) -> str:
        return f"{_PREFIX}:{key}"

    # ── Core operations ───────────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(self._key(key))
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cache get error [%s]: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
        if not self._redis:
            return
        try:
            raw = json.dumps(value, cls=_DatetimeEncoder)
            await self._redis.setex(self._key(key), ttl, raw)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cache set error [%s]: %s", key, exc)

    async def delete(self, key: str) -> None:
        if not self._redis:
            return
        try:
            await self._redis.delete(self._key(key))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cache delete error [%s]: %s", key, exc)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""
        if not self._redis:
            return 0
        try:
            keys = await self._redis.keys(self._key(pattern))
            if keys:
                return await self._redis.delete(*keys)
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cache delete_pattern error [%s]: %s", pattern, exc)
            return 0

    @property
    def available(self) -> bool:
        return self._redis is not None


# ── Global singleton (initialised by app startup) ─────────────────────────────
_cache: RedisCache | None = None


def get_cache() -> RedisCache:
    if _cache is None:
        raise RuntimeError("Cache not initialised — call init_cache() first")
    return _cache


async def init_cache(url: str) -> RedisCache:
    global _cache
    _cache = RedisCache(url)
    await _cache.connect()
    return _cache


# ── Decorator ─────────────────────────────────────────────────────────────────

def cache_response(key_template: str, ttl: int = _DEFAULT_TTL):
    """
    Decorator that caches the JSON response of an **async** route handler.

    ``key_template`` may contain ``{param}`` placeholders matching function
    kwargs. Example::

        @router.get("/products/{asin}")
        @cache_response("product:{asin}", ttl=300)
        async def get_product(asin: str, cache: RedisCache = Depends(get_cache)):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            cache: RedisCache | None = kwargs.get("cache")
            key = key_template.format(**kwargs)

            if cache:
                cached = await cache.get(key)
                if cached is not None:
                    logger.debug("Cache HIT  [%s]", key)
                    return cached
                logger.debug("Cache MISS [%s]", key)

            result = await fn(*args, **kwargs)

            if cache:
                await cache.set(key, result, ttl=ttl)

            return result
        return wrapper
    return decorator
