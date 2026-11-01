"""Production / demonstration environment selection.

The demo environment is strictly isolated: it uses its own PostgreSQL schema ("demo"),
its own storage prefix, tokens bound to the environment, and never sends external
notifications. A request selects the demo environment with the `X-CC-Env: demo`
header (or `cc_env=demo` query parameter for signed media links).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

PRODUCTION = "production"
DEMO = "demo"
ENV_HEADER = b"x-cc-env"

_current: ContextVar[str] = ContextVar("cc_env", default=PRODUCTION)


def current_env() -> str:
    return _current.get()


def is_demo() -> bool:
    return _current.get() == DEMO


@contextmanager
def use_env(env: str):
    token = _current.set(env)
    try:
        yield
    finally:
        _current.reset(token)


def storage_prefix() -> str:
    return "demo/" if is_demo() else ""


class EnvironmentMiddleware:
    """Pure ASGI middleware so the context variable reaches sync endpoints and dependencies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        from app.core.config import get_settings

        wanted = PRODUCTION
        for k, v in scope.get("headers", []):
            if k == ENV_HEADER and v.decode("latin-1").strip().lower() == DEMO:
                wanted = DEMO
        if wanted == PRODUCTION and b"cc_env=demo" in scope.get("query_string", b""):
            wanted = DEMO
        if wanted == DEMO and not get_settings().DEMO_ENABLED:
            wanted = PRODUCTION
        token = _current.set(wanted)
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
