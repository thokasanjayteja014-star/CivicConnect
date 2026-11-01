"""Resolution deadlines (SLA) and escalations.

Deadlines come from EscalationPolicy rows (department-specific first, then global), falling
back to the built-in prototype defaults below. Overdue complaints are escalated automatically:
level 1 to the unit's department administrators at the deadline, level 2 to the main
administrators when half of the window has passed again without resolution.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app import audit
from app.core.errors import err
from app.models import Complaint, EscalationPolicy, Escalation, Officer, User
from app.models.enums import AccountStatus, ComplaintStatus as S, EscalationStatus, Role, RoutingStatus
from app.notifications import notify
from app.security.permissions import Actor

# Prototype defaults (hours), not an official service-level standard.
DEFAULT_HOURS = {"CRITICAL": 48, "HIGH": 120, "MEDIUM": 240, "LOW": 360, "UNSCORED": 240}
PRIORITY_KEYS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNSCORED"]
OPEN_STATUSES = [S.SUBMITTED, S.UNDER_REVIEW, S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.REOPENED]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def policy_hours(db: Session, department_id: uuid.UUID | None, priority: str | None) -> int:
    key = priority or "UNSCORED"
    rows = db.scalars(select(EscalationPolicy).where(EscalationPolicy.priority_level == key)).all()
    dept = next((r for r in rows if department_id and r.department_id == department_id), None)
    glob = next((r for r in rows if r.department_id is None), None)
    return (dept or glob).resolve_within_hours if (dept or glob) else DEFAULT_HOURS[key]


def effective_policies(db: Session) -> list[dict]:
    rows = db.scalars(select(EscalationPolicy)).all()
    out = []
    for key in PRIORITY_KEYS:
        glob = next((r for r in rows if r.department_id is None and r.priority_level == key), None)
        out.append({"priority_level": key, "resolve_within_hours": glob.resolve_within_hours if glob else DEFAULT_HOURS[key],
                    "source": "configured" if glob else "default"})
    overrides = [{"department_id": r.department_id, "priority_level": r.priority_level,
                  "resolve_within_hours": r.resolve_within_hours} for r in rows if r.department_id]
    return out + overrides


def set_due_at(db: Session, complaint: Complaint) -> None:
    if complaint.routing_status != RoutingStatus.ROUTED:
        return
    level = complaint.priority_level.value if complaint.priority_level else None
    start = complaint.created_at or _now()
    complaint.due_at = start + timedelta(hours=policy_hours(db, complaint.department_id, level))


def _unit_admin_ids(db: Session, unit_id: uuid.UUID | None) -> list[uuid.UUID]:
    if not unit_id:
        return []
    return list(db.scalars(select(User.id).join(Officer, Officer.user_id == User.id).where(
        Officer.unit_id == unit_id, Officer.active.is_(True), User.role == Role.DEPARTMENT_ADMIN,
        User.account_status == AccountStatus.ACTIVE)))


def _system_admin_ids(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(select(User.id).where(User.role == Role.SYSTEM_ADMIN, User.account_status == AccountStatus.ACTIVE)))


def _open_escalation(db: Session, complaint_id: uuid.UUID, level: int | None = None):
    stmt = select(Escalation).where(Escalation.complaint_id == complaint_id, Escalation.status == EscalationStatus.OPEN)
    if level is not None:
        stmt = stmt.where(Escalation.level == level)
    return db.scalar(stmt.order_by(Escalation.level.desc()))


def _raise(db: Session, complaint: Complaint, level: int, code: str, reason: str, by: uuid.UUID | None) -> Escalation:
    esc = Escalation(complaint_id=complaint.id, department_unit_id=complaint.department_unit_id, level=level,
                     reason_code=code, reason=reason, raised_by=by)
    db.add(esc)
    db.flush()
    recipients = _unit_admin_ids(db, complaint.department_unit_id) if level == 1 else _system_admin_ids(db)
    for uid in recipients:
        notify(db, recipient_id=uid, complaint_id=complaint.id, notification_type="ESCALATED",
               message=f"Complaint {complaint.reference_id} was escalated (level {level}): {reason}",
               event_key=f"escalation:{esc.id}")
    audit.record(db, actor_id=by, actor_label=None if by else "system:escalation", action="COMPLAINT_ESCALATED",
                 entity_type="complaint", entity_id=complaint.id, details={"level": level, "reason_code": code, "reason": reason})
    return esc


def run_overdue_escalations(db: Session, limit: int = 200) -> int:
    """Escalate overdue open complaints. Idempotent; safe to call on every dashboard load."""
    now = _now()
    open_l1 = exists().where(and_(Escalation.complaint_id == Complaint.id, Escalation.status == EscalationStatus.OPEN,
                                  Escalation.reason_code == "OVERDUE"))
    created = 0
    for c in db.scalars(select(Complaint).where(
            Complaint.routing_status == RoutingStatus.ROUTED, Complaint.status.in_(OPEN_STATUSES),
            Complaint.due_at.is_not(None), Complaint.due_at < now, ~open_l1).limit(limit)):
        _raise(db, c, 1, "OVERDUE", f"Resolution deadline passed on {c.due_at:%d %b %Y %H:%M} UTC.", None)
        created += 1
    for esc in db.scalars(select(Escalation).where(Escalation.status == EscalationStatus.OPEN, Escalation.level == 1,
                                                   Escalation.reason_code == "OVERDUE").limit(limit)):
        c = esc.complaint
        if c.status not in OPEN_STATUSES or not c.due_at or _open_escalation(db, c.id, 2):
            continue
        window = max(c.due_at - c.created_at, timedelta(hours=1))
        if now > c.due_at + window / 2:
            _raise(db, c, 2, "OVERDUE", "Still unresolved well after the deadline; escalated to the main administration.", None)
            created += 1
    if created:
        db.commit()
    return created


def escalate_manually(db: Session, actor: Actor, complaint: Complaint, reason: str) -> Escalation:
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise err("REASON_REQUIRED", details={"field": "reason"})
    if complaint.status not in OPEN_STATUSES:
        raise err("INVALID_STATUS_TRANSITION", message="Only open complaints can be escalated.")
    current = _open_escalation(db, complaint.id)
    # Officers escalate to their department administrator; department administrators to the main administration.
    level = 1 if actor.role == Role.OFFICER else 2
    if current and current.level >= level:
        raise err("ALREADY_UPDATED", message="This complaint already has an open escalation at this level.")
    esc = _raise(db, complaint, level, "MANUAL", reason, actor.user_id)
    db.commit()
    return esc


def resolve_escalation(db: Session, actor: Actor, esc: Escalation, note: str) -> Escalation:
    if esc.status != EscalationStatus.OPEN:
        raise err("ALREADY_UPDATED")
    esc.status, esc.resolution_note, esc.resolved_by, esc.resolved_at = EscalationStatus.RESOLVED, (note or "").strip() or None, actor.user_id, _now()
    audit.record(db, actor_id=actor.user_id, action="ESCALATION_RESOLVED", entity_type="complaint",
                 entity_id=esc.complaint_id, details={"escalation_id": esc.id, "note": esc.resolution_note})
    db.commit()
    return esc


def close_escalations_for(db: Session, complaint_id: uuid.UUID, actor_id: uuid.UUID | None, note: str) -> None:
    for esc in db.scalars(select(Escalation).where(Escalation.complaint_id == complaint_id, Escalation.status == EscalationStatus.OPEN)):
        esc.status, esc.resolution_note, esc.resolved_by, esc.resolved_at = EscalationStatus.RESOLVED, note, actor_id, _now()


def escalation_dict(e: Escalation) -> dict:
    return {"id": e.id, "complaint_id": e.complaint_id, "reference_id": e.complaint.reference_id, "title": e.complaint.title,
            "level": e.level, "reason_code": e.reason_code, "reason": e.reason, "status": e.status,
            "created_at": e.created_at, "resolved_at": e.resolved_at, "resolution_note": e.resolution_note,
            "complaint_status": e.complaint.status, "due_at": e.complaint.due_at}


def open_escalation_count(db: Session, where=None) -> int:
    stmt = select(func.count(func.distinct(Escalation.complaint_id))).select_from(Escalation).join(
        Complaint, Complaint.id == Escalation.complaint_id).where(Escalation.status == EscalationStatus.OPEN)
    if where is not None:
        stmt = stmt.where(where)
    return db.scalar(stmt) or 0
