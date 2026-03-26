"""
utils/cache.py — diskcache-backed caching with configurable TTL.

Usage:
    from utils.cache import cached

    @cached(ttl=3600, key_prefix="schedule")
    def get_schedule(date: str):
        ...
"""
from __future__ import annotations
import functools
import hashlib
import json
from typing import Any, Callable

import diskcache

import config
from utils.logger import get_logger

log = get_logger(__name__)

# Single shared cache instance
_cache = diskcache.Cache(str(config.CACHE_DIR))


def cached(ttl: int = 3_600, key_prefix: str = "") -> Callable:
    """
    Decorator that caches the return value of a function in diskcache.

    Args:
        ttl: Time-to-live in seconds.
        key_prefix: Optional prefix to namespace cache keys.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            raw_key = json.dumps(
                {"prefix": key_prefix or fn.__name__, "args": args, "kwargs": kwargs},
                sort_keys=True,
                default=str,
            )
            cache_key = hashlib.sha256(raw_key.encode()).hexdigest()

            if cache_key in _cache:
                log.debug(f"[bold green]Cache HIT[/] → {fn.__name__}")
                return _cache[cache_key]

            log.debug(f"[bold yellow]Cache MISS[/] → {fn.__name__}, fetching…")
            result = fn(*args, **kwargs)
            _cache.set(cache_key, result, expire=ttl)
            return result

        return wrapper
    return decorator


def clear_cache() -> None:
    """Clear all cached entries."""
    _cache.clear()
    log.info("Cache cleared.")


def cache_info() -> dict[str, Any]:
    """Return cache stats."""
    return {
        "size": len(_cache),
        "volume_bytes": _cache.volume(),
        "directory": str(config.CACHE_DIR),
    }
