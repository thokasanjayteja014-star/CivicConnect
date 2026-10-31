"""Simple in-process sliding-window rate limiter (per client IP + bucket).

Adequate for a single-instance MVP; use a shared store (e.g. Redis) when
running multiple backend replicas.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import err

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def _parse(spec: str) -> tuple[int, int]:
    count, seconds = spec.split("/")
    return int(count), int(seconds)


def rate_limit(bucket: str, setting_name: str):
    def dep(request: Request) -> None:
        s = get_settings()
        if not s.RATE_LIMIT_ENABLED:
            return
        limit, window = _parse(getattr(s, setting_name))
        ip = request.client.host if request.client else "unknown"
        key = f"{bucket}:{ip}"
        now = time.monotonic()
        with _lock:
            q = _hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                raise err("RATE_LIMITED")
            q.append(now)

    return dep


def reset() -> None:
    with _lock:
        _hits.clear()
