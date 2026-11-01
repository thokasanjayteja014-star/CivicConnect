from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.environment import DEMO, current_env


class Base(DeclarativeBase):
    pass


# One engine per environment. The demo engine pins search_path to the isolated demo schema
# (PostGIS functions stay reachable through public) with a SET on every new connection, so demo
# data can never be written to or read from the production tables.
_engines: dict = {}
_makers: dict[str, sessionmaker] = {}


def get_engine(env: str | None = None):
    env = env or current_env()
    if env not in _engines:
        s = get_settings()
        engine = create_engine(s.DATABASE_URL, pool_pre_ping=True, future=True)
        if env == DEMO:
            _pin_search_path(engine, s.DEMO_SCHEMA)
        _engines[env] = engine
        _makers[env] = sessionmaker(bind=_engines[env], autoflush=False, expire_on_commit=False)
    return _engines[env]


def _pin_search_path(engine, schema: str) -> None:
    """Point every demo connection at the demo schema with a real SET statement.

    A libpq startup option (``options=-csearch_path=...``) is not enough: connection poolers
    such as Supabase's Supavisor or PgBouncer drop it silently, and the demo would then read
    and write the production tables. A SET on each new connection works through a session
    pooler, and the check refuses the connection outright if the schema is not in effect.
    """

    @event.listens_for(engine, "connect", insert=True)
    def _on_connect(dbapi_connection, _record):
        autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            cur = dbapi_connection.cursor()
            try:
                cur.execute(f'SET SESSION search_path TO "{schema}", public')
                cur.execute("SELECT current_schema()")
                current = cur.fetchone()[0]
            finally:
                cur.close()
        finally:
            dbapi_connection.autocommit = autocommit
        if current != schema:
            raise RuntimeError(
                f"Demo connection is using schema {current!r} instead of {schema!r}; refusing to "
                "continue so demo data cannot reach production. Create the demo schema first "
                "(python -m app.demo ensure) and use a session pooler, not a transaction pooler."
            )


def reset_engine(env: str | None = None) -> None:
    """Dispose pooled connections (tests after changing DATABASE_URL; demo reset)."""
    for key in ([env] if env else list(_engines)):
        eng = _engines.pop(key, None)
        _makers.pop(key, None)
        if eng is not None:
            eng.dispose()


def SessionLocal(env: str | None = None) -> Session:
    env = env or current_env()
    get_engine(env)
    return _makers[env]()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
