"""Notifications (spec F13, L13).

In-app notifications are stored in the database (the in-app channel is
delivered once persisted). After the transaction commits, each notification is
also sent over the external channels that are configured and that the
recipient has enabled (email, SMS, browser push; see channels.py). Each attempt
is recorded in notification_deliveries. A unique dedupe_key per
(event, recipient) prevents duplicates from repeated processing.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.environment import is_demo
from app.models import Complaint, Notification, NotificationDelivery, Officer, PushSubscription, User
from app.models.enums import ComplaintStatus, DeliveryStatus, Role
from app.notifications import channels

log = logging.getLogger("civicconnect.notifications")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")

STATUS_MESSAGES = {
    ComplaintStatus.UNDER_REVIEW: "is now under review by the department.",
    ComplaintStatus.ASSIGNED: "has been assigned to an officer.",
    ComplaintStatus.IN_PROGRESS: "is in progress.",
    ComplaintStatus.ON_HOLD: "has been placed on hold.",
    ComplaintStatus.RESOLVED_AWAITING_VERIFICATION: "was marked resolved by the authority and is awaiting verification. Please confirm whether the issue is fixed.",
    ComplaintStatus.VERIFIED_RESOLVED: "has been verified as resolved.",
    ComplaintStatus.REJECTED: "was rejected by the department.",
    ComplaintStatus.REOPENED: "has been reopened.",
}


def notify(
    db: Session,
    *,
    recipient_id: uuid.UUID,
    complaint_id: uuid.UUID | None,
    notification_type: str,
    message: str,
    event_key: str,
) -> Notification | None:
    dedupe_key = f"{event_key}:{recipient_id}"[:200]
    if db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)):
        return None
    n = Notification(
        id=uuid.uuid4(),
        recipient_id=recipient_id,
        complaint_id=complaint_id,
        notification_type=notification_type,
        message=message,
        channel="IN_APP",
        delivery_status=DeliveryStatus.SENT,
        dedupe_key=dedupe_key,
    )
    db.add(n)
    db.info.setdefault("pending_external_notifications", []).append(n.id)
    return n


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    ids = session.info.pop("pending_external_notifications", None)
    if not ids or is_demo():  # the demonstration environment never contacts real people
        return
    st = channels.channel_status()
    if not (st["email"] or st["sms"] or st["push"]):
        return
    if get_settings().NOTIFY_EXTERNAL_SYNC:
        for nid in ids:
            deliver_external(nid)
    else:
        for nid in ids:
            _executor.submit(deliver_external, nid)


@event.listens_for(Session, "after_rollback")
def _drop_on_rollback(session: Session) -> None:
    session.info.pop("pending_external_notifications", None)


def _complaint_link(complaint_id: uuid.UUID | None) -> str | None:
    base = get_settings().FRONTEND_ORIGIN.split(",")[0].strip().rstrip("/")
    return f"{base}/complaints/{complaint_id}" if complaint_id else f"{base}/notifications"


def deliver_external(notification_id: uuid.UUID) -> None:
    """Send one stored notification over every configured channel the recipient enabled."""
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        n = db.get(Notification, notification_id)
        if n is None:
            return
        user = db.get(User, n.recipient_id)
        if user is None:
            return
        link = _complaint_link(n.complaint_id)
        st = channels.channel_status()
        jobs = []
        if st["email"] and user.notify_email and user.email:
            jobs.append(("EMAIL", st["email"], lambda: channels.send_email(user.email, user.full_name, n.message, link)))
        if st["sms"] and user.notify_sms and user.phone:
            jobs.append(("SMS", st["sms"], lambda: channels.send_sms(user.phone, f"CivicConnect: {n.message}")))
        if st["push"] and user.notify_push:
            subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()
            if subs:
                def push_all(subs=subs):
                    ok = 0
                    for sub in subs:
                        try:
                            channels.send_push(sub.endpoint, sub.p256dh, sub.auth, n.message, link)
                            ok += 1
                        except channels.SubscriptionGone:
                            db.delete(sub)
                        except channels.ChannelError as exc:
                            log.warning("push failed: %s", exc)
                    if not ok:
                        raise channels.ChannelError("push: no subscription accepted")
                    return "webpush"
                jobs.append(("PUSH", "webpush", push_all))
        for channel, provider, send in jobs:
            if db.scalar(select(NotificationDelivery.id).where(
                    NotificationDelivery.notification_id == n.id, NotificationDelivery.channel == channel)):
                continue  # already attempted (dedupe)
            d = NotificationDelivery(notification_id=n.id, channel=channel, provider=provider)
            try:
                send()
                d.delivery_status = DeliveryStatus.SENT
                d.sent_at = datetime.now(timezone.utc)
            except channels.ChannelError as exc:
                d.delivery_status = DeliveryStatus.FAILED
                d.error = str(exc)[:300]
                log.warning("notification %s via %s failed: %s", n.id, channel, exc)
            db.add(d)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
    except Exception:  # never let a channel failure affect the request that caused it
        log.exception("external notification delivery crashed")
        db.rollback()
    finally:
        db.close()


def department_staff_ids(db: Session, department_id: uuid.UUID, roles: set[Role] | None = None) -> list[uuid.UUID]:
    stmt = (
        select(User.id, User.role)
        .join(Officer, Officer.user_id == User.id)
        .where(Officer.department_id == department_id, Officer.active.is_(True))
    )
    return [uid for uid, role in db.execute(stmt) if roles is None or role in roles]


def unit_staff_ids(db: Session, unit_id: uuid.UUID | None, roles: set[Role] | None = None) -> list[uuid.UUID]:
    """Active personnel of one department unit (department in a jurisdiction)."""
    if not unit_id:
        return []
    stmt = (
        select(User.id, User.role)
        .join(Officer, Officer.user_id == User.id)
        .where(Officer.unit_id == unit_id, Officer.active.is_(True))
    )
    return [uid for uid, role in db.execute(stmt) if roles is None or role in roles]


def notify_status_change(db: Session, complaint: Complaint, new_status: ComplaintStatus, event_id: uuid.UUID) -> None:
    text = STATUS_MESSAGES.get(new_status)
    if text:
        notify(
            db,
            recipient_id=complaint.citizen_id,
            complaint_id=complaint.id,
            notification_type=f"STATUS_{new_status.value}",
            message=f"Your complaint {complaint.reference_id} {text}",
            event_key=f"status:{event_id}",
        )
