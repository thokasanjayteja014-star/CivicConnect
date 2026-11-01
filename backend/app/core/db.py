from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.environment import DEMO, current_env


class Base(DeclarativeBase):
    pass


# One engine per environment. The demo engine pins search_path to the isolated demo schema
# (PostGIS functions stay reachable through public), so demo data can never be written to
# or read from the production tables.
_engines: dict = {}
_makers: dict[str, sessionmaker] = {}


def get_engine(env: str | None = None):
    env = env or current_env()
    if env not in _engines:
        s = get_settings()
        kwargs = {}
        if env == DEMO:
            kwargs["connect_args"] = {"options": f"-csearch_path={s.DEMO_SCHEMA},public"}
        _engines[env] = create_engine(s.DATABASE_URL, pool_pre_ping=True, future=True, **kwargs)
        _makers[env] = sessionmaker(bind=_engines[env], autoflush=False, expire_on_commit=False)
    return _engines[env]


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
