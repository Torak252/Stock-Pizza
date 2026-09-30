from __future__ import annotations

import functools
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def ttl_cache(seconds: float) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Memoize by positional/keyword args for `seconds`. Exceptions are not cached."""

    def wrap(fn: Callable[..., T]) -> Callable[..., T]:
        store: dict[tuple, tuple[float, T]] = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def inner(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with lock:
                hit = store.get(key)
                if hit and now - hit[0] < seconds:
                    return hit[1]
            value = fn(*args, **kwargs)
            with lock:
                store[key] = (now, value)
            return value

        inner.cache_clear = store.clear  # type: ignore[attr-defined]
        return inner

    return wrap
