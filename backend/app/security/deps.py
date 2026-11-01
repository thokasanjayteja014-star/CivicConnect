"""FastAPI dependencies for authentication."""
import uuid
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import err
from app.models import Officer, RevokedToken, User
from app.models.enums import AccountStatus, Role
from app.security import decode_token
from app.security.permissions import STAFF_ROLES, Actor


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def build_actor(db: Session, user: User) -> Actor:
    from app.services.hierarchy import descendant_ids

    officer = db.scalar(select(Officer).where(Officer.user_id == user.id))
    areas: frozenset = frozenset()
    if officer and user.role == Role.OFFICER and officer.areas:
        areas = frozenset(descendant_ids(db, [a.jurisdiction_id for a in officer.areas]))
    return Actor(
        user_id=user.id,
        role=user.role,
        full_name=user.full_name,
        department_id=officer.department_id if officer else None,
        officer_id=officer.id if officer else None,
        officer_active=bool(officer and officer.active),
        explicit_permissions={p.permission for p in user.permissions},
        unit_id=officer.unit_id if officer else None,
        area_ids=areas,
    )


def _actor_from_token(db: Session, token: str) -> tuple[Actor, dict]:
    payload = decode_token(token)
    if db.get(RevokedToken, payload["jti"]):
        raise err("UNAUTHENTICATED")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise err("UNAUTHENTICATED")
    if user.account_status != AccountStatus.ACTIVE:
        raise err("ACCOUNT_DISABLED")
    return build_actor(db, user), payload


def get_current_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    token = _bearer(request)
    if not token:
        raise err("UNAUTHENTICATED")
    actor, payload = _actor_from_token(db, token)
    request.state.token_payload = payload
    return actor


def get_optional_actor(request: Request, db: Session = Depends(get_db)) -> Actor | None:
    token = _bearer(request)
    if not token:
        return None
    return _actor_from_token(db, token)[0]


def require_roles(*roles: Role):
    allowed = set(roles)

    def dep(actor: Actor = Depends(get_current_actor)) -> Actor:
        if actor.role not in allowed:
            raise err("FORBIDDEN")
        return actor

    return dep


require_citizen = require_roles(Role.CITIZEN)
require_staff = require_roles(*STAFF_ROLES)
require_system_admin = require_roles(Role.SYSTEM_ADMIN)
require_admin = require_roles(Role.SYSTEM_ADMIN, Role.DEPARTMENT_ADMIN)


def revoke(db: Session, payload: dict) -> None:
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    if not db.get(RevokedToken, payload["jti"]):
        db.add(RevokedToken(jti=payload["jti"], expires_at=exp))
        db.commit()
