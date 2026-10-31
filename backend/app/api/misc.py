"""Departments (read), AI status, notifications and system health."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ai import ai_service
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import err
from app.models import Department, Notification, NotificationDelivery, PushSubscription, ResponsibilityRule
from app.notifications import channels, notify
from app.schemas import PushSubscriptionIn
from app.security.deps import get_current_actor
from app.security.permissions import Actor
from app.services.storage import get_storage

router = APIRouter(tags=["misc"])


@router.get("/api/departments")
def departments(actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    """Citizens and staff see active departments; system admins see all."""
    stmt = select(Department).order_by(Department.name)
    if not actor.is_system_admin:
        stmt = stmt.where(Department.active.is_(True))
    return [{"id": d.id, "name": d.name, "description": d.description, "active": d.active, "is_prototype": d.is_prototype,
             "supported_categories": [c.value for c in d.supported_categories]} for d in db.scalars(stmt)]


@router.get("/api/departments/{department_id}/responsibilities")
def responsibilities(department_id: uuid.UUID, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    d = db.get(Department, department_id)
    if d is None or (not d.active and not actor.is_system_admin):
        raise err("NOT_FOUND")
    rules = db.scalars(select(ResponsibilityRule).where(ResponsibilityRule.department_id == d.id)).all()
    visible = rules if actor.is_staff else [r for r in rules if r.active and r.verified]
    return {"department_id": d.id, "department_name": d.name, "is_prototype": d.is_prototype,
            "responsibilities": [{"category": r.category, "active": r.active, "verified": r.verified,
                                  "source_reference": r.source_reference} for r in visible]}


@router.get("/api/ai/status")
def ai_status():
    return ai_service.ai_status()


@router.get("/api/notifications")
def notifications(actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db), unread_only: bool = False):
    stmt = select(Notification).where(Notification.recipient_id == actor.user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(100)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.recipient_id == actor.user_id, Notification.read_at.is_(None)))
    deliveries: dict = {}
    if rows:
        for d in db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id.in_([n.id for n in rows]))):
            deliveries.setdefault(d.notification_id, []).append({"channel": d.channel, "status": d.delivery_status})
    return {"unread": unread, "items": [{"id": n.id, "complaint_id": n.complaint_id, "notification_type": n.notification_type,
                                         "message": n.message, "channel": n.channel, "delivery_status": n.delivery_status,
                                         "external_deliveries": deliveries.get(n.id, []),
                                         "read_at": n.read_at, "created_at": n.created_at} for n in rows]}


@router.get("/api/notifications/channels")
def notification_channels():
    """Which delivery channels this deployment has configured, plus the public VAPID key for browser push."""
    st = channels.channel_status()
    return {**{k: bool(v) for k, v in st.items()}, "vapid_public_key": get_settings().VAPID_PUBLIC_KEY or None}


@router.post("/api/notifications/push-subscriptions", status_code=201)
def add_push_subscription(body: PushSubscriptionIn, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    if not channels.push_configured():
        raise err("VALIDATION_ERROR", message="Browser notifications are not configured on this deployment.")
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(user_id=actor.user_id, endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth)
        db.add(sub)
    else:  # same browser, possibly a different account now
        sub.user_id, sub.p256dh, sub.auth = actor.user_id, body.p256dh, body.auth
    db.commit()
    return {"ok": True}


@router.delete("/api/notifications/push-subscriptions", status_code=204)
def remove_push_subscription(endpoint: str, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint,
                                                   PushSubscription.user_id == actor.user_id))
    if sub:
        db.delete(sub)
        db.commit()


@router.post("/api/notifications/test")
def test_notification(actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    """Send yourself a test notification on every channel you have enabled."""
    notify(db, recipient_id=actor.user_id, complaint_id=None, notification_type="TEST",
           message="This is a test notification from CivicConnect. Your notification settings work.",
           event_key=f"test:{uuid.uuid4()}")
    db.commit()
    return {"ok": True, "channels": channels.channel_status()}


@router.post("/api/notifications/read-all")
def read_all(actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    for n in db.scalars(select(Notification).where(Notification.recipient_id == actor.user_id, Notification.read_at.is_(None))):
        n.read_at = now
    db.commit()
    return {"ok": True}


@router.post("/api/notifications/{notification_id}/read")
def read_one(notification_id: uuid.UUID, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_id != actor.user_id:
        raise err("NOT_FOUND")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.get("/api/health")
def health():
    return {"status": "ok", "service": "civicconnect-backend", "time": datetime.now(timezone.utc)}


@router.get("/api/ready")
def ready(db: Session = Depends(get_db)):
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
        checks["postgis"] = "ok" if db.scalar(text("SELECT postgis_version()")) else "missing"
    except Exception:
        checks["database"] = "unavailable"
    checks["storage"] = "ok" if get_storage().healthy() else "unavailable"
    checks["ai"] = ai_service.ai_status().mode  # "stub" is acceptable: AI is optional for core workflow
    ok = checks.get("database") == "ok" and checks.get("postgis") == "ok" and checks["storage"] == "ok"
    if not ok:
        raise err("DATABASE_UNAVAILABLE" if checks.get("database") != "ok" else "MEDIA_STORAGE_FAILURE",
                  message="Service not ready.", details=checks, status_code=503)
    return {"status": "ready", "checks": checks}
