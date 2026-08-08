from __future__ import annotations

import time
from typing import Any, Callable

# Simple in-memory TTL cache. Good enough for a single process; keeps the
# api-football free tier (100 requests/day) well within budget.

_store: dict[str, tuple[float, Any]] = {}


def get(key: str, ttl: int) -> Any | None:
    item = _store.get(key)
    if item is None:
        return None
    expires_at, value = item
    if time.monotonic() > expires_at:
        _store.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl: int) -> None:
    _store[key] = (time.monotonic() + ttl, value)


def cached(ttl: int) -> Callable:
    def decorator(fn: Callable) -> Callable:
        def wrapper(key: str, *args: Any, **kwargs: Any) -> Any:
            hit = get(key, ttl)
            if hit is not None:
                return hit
            value = fn(key, *args, **kwargs)
            set(key, value, ttl)
            return value

        return wrapper

    return decorator
