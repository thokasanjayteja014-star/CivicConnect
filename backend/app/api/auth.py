from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.core.db import get_db
from app.core.errors import err
from app.core.ratelimit import rate_limit
from app.models import Department, User
from app.models.enums import AccountStatus, Role
from app.schemas import LoginRequest, MeOut, PreferencesUpdate, RegisterRequest, TokenOut
from app.security import create_access_token, hash_password, verify_password
from app.security.deps import build_actor, get_current_actor, revoke
from app.security.permissions import ROLE_DEFAULT_PERMISSIONS, Actor

router = APIRouter(prefix="/api/auth", tags=["auth"])


def me_out(db: Session, user: User) -> MeOut:
    actor = build_actor(db, user)
    dept = db.get(Department, actor.department_id) if actor.department_id else None
    perms = sorted(ROLE_DEFAULT_PERMISSIONS.get(user.role, set()) | actor.explicit_permissions, key=lambda p: p.value)
    return MeOut(
        **{k: getattr(user, k) for k in ("id", "full_name", "email", "phone", "role", "account_status", "created_at",
                                     "notify_email", "notify_sms", "notify_push", "preferred_language")},
        department_id=actor.department_id,
        department_name=dept.name if dept else None,
        officer_id=actor.officer_id,
        permissions=perms,
    )


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[Depends(rate_limit("auth", "RATE_LIMIT_AUTH"))])
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise err("EMAIL_IN_USE")
    user = User(full_name=body.full_name.strip(), email=email, phone=body.phone, password_hash=hash_password(body.password),
                role=Role.CITIZEN, account_status=AccountStatus.ACTIVE)
    db.add(user)
    db.flush()
    audit.record(db, actor_id=user.id, action="USER_REGISTERED", entity_type="user", entity_id=user.id)
    db.commit()
    token, exp = create_access_token(user.id, user.role.value)
    return TokenOut(access_token=token, expires_at=exp, user=me_out(db, user))


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("auth", "RATE_LIMIT_AUTH"))])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise err("INVALID_CREDENTIALS")
    if user.account_status != AccountStatus.ACTIVE:
        raise err("ACCOUNT_DISABLED")
    token, exp = create_access_token(user.id, user.role.value)
    audit.record(db, actor_id=user.id, action="USER_LOGIN", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(access_token=token, expires_at=exp, user=me_out(db, user))


@router.post("/logout", status_code=204)
def logout(request: Request, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    revoke(db, request.state.token_payload)


@router.get("/me", response_model=MeOut)
def me(actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    return me_out(db, db.get(User, actor.user_id))


@router.patch("/me/preferences", response_model=MeOut)
def update_preferences(body: PreferencesUpdate, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    """Notification channels, phone number for SMS, and interface language."""
    user = db.get(User, actor.user_id)
    changes = body.model_dump(exclude_unset=True)
    if "phone" in changes:
        changes["phone"] = changes["phone"] or None
    for k, v in changes.items():
        if v is not None or k == "phone":
            setattr(user, k, v)
    if user.notify_sms and not (user.phone and user.phone.startswith("+")):
        raise err("VALIDATION_ERROR", message="Add a mobile number in international format (e.g. +919876543210) to receive SMS.",
                  details={"field": "phone"})
    audit.record(db, actor_id=user.id, action="PREFERENCES_UPDATED", entity_type="user", entity_id=user.id,
                 details={k: v for k, v in changes.items() if k != "phone"} | ({"phone_changed": True} if "phone" in changes else {}))
    db.commit()
    return me_out(db, user)
