"""Administration overview (real governance statistics) and Public Issues.

Public Issues are a transparency feature, not a copy of the complaint list: department staff
group verified complaints into one issue, assess its public impact, and an authorized
administrator publishes it. The public view never contains citizen personal information.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app import audit
from app.core.db import get_db
from app.core.errors import err
from app.models import (
    Assignment,
    Complaint,
    Department,
    DepartmentUnit,
    Jurisdiction,
    Officer,
    PublicIssue,
    PublicIssueComplaint,
    PublicIssueUpdate,
    ResponsibilityRule,
    StatusHistory,
    User,
)
from app.models.enums import (
    AssignmentStatus,
    Category,
    ComplaintStatus as S,
    PublicIssueProgress,
    PublicIssueStatus,
    Role,
    RoutingStatus,
    VerificationStatus,
)
from app.security.deps import require_staff, require_system_admin
from app.security.permissions import Actor, in_department_scope
from app.services import escalation as esc_service
from app.services.hierarchy import jurisdiction_path

admin_router = APIRouter(prefix="/api/admin", tags=["governance"], dependencies=[Depends(require_system_admin)])
staff_router = APIRouter(prefix="/api/authority/public-issues", tags=["public-issues"])
public_router = APIRouter(prefix="/api/public/issues", tags=["public"])

OPEN = [S.SUBMITTED, S.UNDER_REVIEW, S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.REOPENED]
INVESTIGATING = [S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD]
RESOLVED = [S.RESOLVED_AWAITING_VERIFICATION, S.VERIFIED_RESOLVED]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ====================== administration overview ======================
def _resolution_hours(db: Session, where=None) -> tuple[float | None, int]:
    """Average hours from submission to the first verified resolution."""
    first = (select(StatusHistory.complaint_id, func.min(StatusHistory.created_at).label("at"))
             .where(StatusHistory.new_status == S.VERIFIED_RESOLVED).group_by(StatusHistory.complaint_id).subquery())
    stmt = select(func.avg(func.extract("epoch", first.c.at - Complaint.created_at) / 3600.0), func.count()).join(
        first, first.c.complaint_id == Complaint.id)
    if where is not None:
        stmt = stmt.where(where)
    avg, n = db.execute(stmt).one()
    return (round(float(avg), 1) if avg is not None else None), int(n or 0)


@admin_router.get("/overview")
def overview(db: Session = Depends(get_db)):
    esc_service.run_overdue_escalations(db)
    now = _now()
    total = db.scalar(select(func.count()).select_from(Complaint)) or 0
    by_status = {k.value: v for k, v in db.execute(select(Complaint.status, func.count()).group_by(Complaint.status)).all()}
    g = lambda *ss: sum(by_status.get(s.value, 0) for s in ss)  # noqa: E731
    active_assignment = exists().where(Assignment.complaint_id == Complaint.id, Assignment.assignment_status == AssignmentStatus.ACTIVE)
    overdue_cond = and_(Complaint.due_at.is_not(None), Complaint.due_at < now, Complaint.status.in_(OPEN))
    count = lambda *w: db.scalar(select(func.count()).select_from(Complaint).where(*w)) or 0  # noqa: E731
    avg_hours, resolved_n = _resolution_hours(db)

    # department performance
    perf = []
    for d in db.scalars(select(Department).order_by(Department.name)):
        dtotal = count(Complaint.department_id == d.id)
        if not dtotal and not d.active:
            continue
        resolved = count(Complaint.department_id == d.id, Complaint.status.in_(RESOLVED))
        avg_d, _ = _resolution_hours(db, Complaint.department_id == d.id)
        perf.append({"department_id": d.id, "department": d.name, "active": d.active, "total": dtotal,
                     "open": count(Complaint.department_id == d.id, Complaint.status.in_(OPEN)),
                     "resolved": resolved,
                     "overdue": count(Complaint.department_id == d.id, overdue_cond),
                     "escalated": esc_service.open_escalation_count(db, Complaint.department_id == d.id),
                     "resolution_rate": round(100 * resolved / dtotal, 1) if dtotal else None,
                     "avg_resolution_hours": avg_d})

    # by jurisdiction (where the complaint is located)
    by_j = []
    for jid, n in db.execute(select(Complaint.jurisdiction_id, func.count()).where(Complaint.jurisdiction_id.is_not(None))
                             .group_by(Complaint.jurisdiction_id).order_by(func.count().desc()).limit(15)).all():
        by_j.append({"jurisdiction_id": jid, "name": jurisdiction_path(db, jid), "count": n,
                     "open": count(Complaint.jurisdiction_id == jid, Complaint.status.in_(OPEN))})

    # weekly trend, last 12 weeks (submitted vs verified resolved)
    start = (now - timedelta(weeks=11)).replace(hour=0, minute=0, second=0, microsecond=0)
    start -= timedelta(days=start.weekday())
    wk_c = func.date_trunc("week", Complaint.created_at)
    created = dict(db.execute(select(wk_c, func.count()).where(Complaint.created_at >= start).group_by(wk_c)).all())
    wk_r = func.date_trunc("week", StatusHistory.created_at)
    resolved_w = dict(db.execute(select(wk_r, func.count()).where(
        StatusHistory.created_at >= start, StatusHistory.new_status == S.VERIFIED_RESOLVED).group_by(wk_r)).all())

    def _wk(d: dict, week: datetime) -> int:
        return sum(v for k, v in d.items() if k and k.date() == week.date())
    trend = []
    for i in range(12):
        week = start + timedelta(weeks=i)
        trend.append({"week_start": week.date().isoformat(), "submitted": _wk(created, week), "resolved": _wk(resolved_w, week)})

    # recent activity (human readable, no technical identifiers)
    recent = []
    for h, c in db.execute(select(StatusHistory, Complaint).join(Complaint, Complaint.id == StatusHistory.complaint_id)
                           .order_by(StatusHistory.created_at.desc()).limit(12)).all():
        who = db.get(User, h.actor_id).full_name if h.actor_id else "Automatic routing"
        recent.append({"at": h.created_at, "reference_id": c.reference_id, "complaint_id": c.id, "title": c.title,
                       "status": h.new_status, "by": who,
                       "department": c.department.name if c.department_id and c.department else None})

    # configuration items needing attention (actionable, real counts)
    units_without_officers = db.scalars(select(DepartmentUnit).where(
        DepartmentUnit.active.is_(True),
        ~exists().where(Officer.unit_id == DepartmentUnit.id, Officer.active.is_(True), User.id == Officer.user_id,
                        User.role == Role.OFFICER))).all()
    attention = {
        "routing_review": count(Complaint.routing_status == RoutingStatus.PENDING_REVIEW, Complaint.status.in_(OPEN)),
        "units_without_officers": [{"unit_id": u.id, "label": f"{u.department.name} — {u.jurisdiction.name}"}
                                   for u in units_without_officers][:20],
        "pending_verification": {
            "departments": db.scalar(select(func.count()).select_from(Department).where(
                Department.verification_status == VerificationStatus.PENDING_VERIFICATION)) or 0,
            "jurisdictions": db.scalar(select(func.count()).select_from(Jurisdiction).where(
                Jurisdiction.verification_status == VerificationStatus.PENDING_VERIFICATION)) or 0,
            "responsibilities": db.scalar(select(func.count()).select_from(ResponsibilityRule).where(
                ResponsibilityRule.verification_status == VerificationStatus.PENDING_VERIFICATION)) or 0,
        },
        "public_issues_awaiting_publication": db.scalar(select(func.count()).select_from(PublicIssue).where(
            PublicIssue.status == PublicIssueStatus.VERIFIED)) or 0,
    }
    return {
        "generated_at": now,
        "totals": {
            "total": total,
            "new": g(S.SUBMITTED),
            "pending": g(*OPEN),
            "awaiting_assignment": count(Complaint.routing_status == RoutingStatus.ROUTED,
                                         Complaint.status.in_([S.SUBMITTED, S.UNDER_REVIEW, S.REOPENED]), ~active_assignment),
            "under_investigation": g(*INVESTIGATING),
            "resolved": g(*RESOLVED),
            "verified_resolved": g(S.VERIFIED_RESOLVED),
            "rejected": g(S.REJECTED),
            "overdue": count(overdue_cond),
            "escalated": esc_service.open_escalation_count(db),
            "avg_resolution_hours": avg_hours,
            "resolved_sample": resolved_n,
        },
        "by_status": by_status,
        "by_department": [{"department": p["department"], "count": p["total"]} for p in perf if p["total"]],
        "by_jurisdiction": by_j,
        "department_performance": perf,
        "trend_weekly": trend,
        "recent_activity": recent,
        "attention": attention,
        "configuration": {
            "departments": db.scalar(select(func.count()).select_from(Department).where(Department.active.is_(True))) or 0,
            "jurisdictions": db.scalar(select(func.count()).select_from(Jurisdiction).where(Jurisdiction.active.is_(True))) or 0,
            "units": db.scalar(select(func.count()).select_from(DepartmentUnit).where(DepartmentUnit.active.is_(True))) or 0,
            "officers": db.scalar(select(func.count()).select_from(Officer).join(User, User.id == Officer.user_id).where(
                Officer.active.is_(True), User.role == Role.OFFICER)) or 0,
            "department_admins": db.scalar(select(func.count()).select_from(Officer).join(User, User.id == Officer.user_id).where(
                Officer.active.is_(True), User.role == Role.DEPARTMENT_ADMIN)) or 0,
        },
    }


# ====================== public issues (staff) ======================
class IssueIn(BaseModel):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    general_location: str | None = Field(default=None, max_length=200)
    complaint_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class IssuePatch(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=160)
    description: str | None = Field(default=None, min_length=10, max_length=4000)
    general_location: str | None = Field(default=None, max_length=200)


class VerifyIssueIn(BaseModel):
    impact_level: str = Field(pattern="^(LOW|MODERATE|HIGH)$")
    impact_assessment: str = Field(min_length=10, max_length=4000)


class IssueUpdateIn(BaseModel):
    message: str = Field(min_length=5, max_length=2000)
    progress: PublicIssueProgress | None = None
    resolution_info: str | None = Field(default=None, max_length=4000)


class LinkIn(BaseModel):
    complaint_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


def _can_approve(actor: Actor) -> bool:
    return actor.is_system_admin or (actor.role == Role.DEPARTMENT_ADMIN and actor.officer_active)


def _issue_scope(actor: Actor):
    if actor.is_system_admin:
        return PublicIssue.id.is_not(None)
    if actor.unit_id and actor.officer_active:
        return PublicIssue.department_unit_id == actor.unit_id
    return PublicIssue.id.is_(None)


def _get_issue(db: Session, actor: Actor, issue_id: uuid.UUID, lock: bool = False) -> PublicIssue:
    stmt = select(PublicIssue).where(PublicIssue.id == issue_id, _issue_scope(actor))
    issue = db.scalar(stmt.with_for_update() if lock else stmt)
    if issue is None:
        raise err("NOT_FOUND")
    return issue


def _linked(db: Session, issue_id: uuid.UUID) -> list[Complaint]:
    return list(db.scalars(select(Complaint).join(PublicIssueComplaint, PublicIssueComplaint.complaint_id == Complaint.id)
                           .where(PublicIssueComplaint.issue_id == issue_id).order_by(Complaint.created_at)))


def _approx(complaints: list[Complaint]) -> tuple[float | None, float | None]:
    pts = [(c.latitude, c.longitude) for c in complaints if c.latitude is not None]
    if not pts:
        return None, None
    # ~110 m precision: enough to show the area, not a doorstep.
    return round(sum(p[0] for p in pts) / len(pts), 3), round(sum(p[1] for p in pts) / len(pts), 3)


def _updates(db: Session, issue_id: uuid.UUID) -> list[PublicIssueUpdate]:
    return list(db.scalars(select(PublicIssueUpdate).where(PublicIssueUpdate.issue_id == issue_id)
                           .order_by(PublicIssueUpdate.created_at.desc())))


def staff_issue_dict(db: Session, actor: Actor, i: PublicIssue, detail: bool = False) -> dict:
    linked = _linked(db, i.id)
    out = {"id": i.id, "title": i.title, "description": i.description, "general_location": i.general_location,
           "category": i.category, "status": i.status, "progress": i.progress, "impact_level": i.impact_level,
           "impact_assessment": i.impact_assessment, "resolution_info": i.resolution_info,
           "department": i.department.name if i.department else None,
           "jurisdiction": jurisdiction_path(db, i.jurisdiction_id), "related_complaints": len(linked),
           "latitude": i.latitude, "longitude": i.longitude,
           "verified_at": i.verified_at, "published_at": i.published_at, "resolved_at": i.resolved_at,
           "created_at": i.created_at, "updated_at": i.updated_at,
           "can_approve": _can_approve(actor)}
    if detail:
        out["complaints"] = [{"complaint_id": c.id, "reference_id": c.reference_id, "title": c.title, "status": c.status,
                              "created_at": c.created_at} for c in linked]
        out["updates"] = [{"id": u.id, "message": u.message, "progress": u.progress, "created_at": u.created_at,
                           "author": db.get(User, u.author_id).full_name} for u in _updates(db, i.id)]
    return out


def _complaints_for_link(db: Session, actor: Actor, ids: list[uuid.UUID], unit_id=None) -> list[Complaint]:
    rows = db.scalars(select(Complaint).where(Complaint.id.in_(ids))).all()
    if len(rows) != len(set(ids)) or any(not in_department_scope(actor, c, db) for c in rows):
        raise err("VALIDATION_ERROR", message="Some complaints were not found in your department.", details={"field": "complaint_ids"})
    if any(c.routing_status != RoutingStatus.ROUTED or c.department_unit_id is None for c in rows):
        raise err("VALIDATION_ERROR", message="Only complaints routed to a department can be linked.", details={"field": "complaint_ids"})
    units = {c.department_unit_id for c in rows} | ({unit_id} if unit_id else set())
    if len(units) > 1:
        raise err("VALIDATION_ERROR", message="All linked complaints must belong to the same department unit.",
                  details={"field": "complaint_ids"})
    taken = db.scalars(select(PublicIssueComplaint.complaint_id).where(PublicIssueComplaint.complaint_id.in_(ids))).all()
    if taken:
        raise err("CONFLICT", message="A complaint is already linked to another public issue.")
    return list(rows)


def _log(db: Session, actor: Actor, action: str, issue: PublicIssue, details: dict | None = None) -> None:
    audit.record(db, actor_id=actor.user_id, action=action, entity_type="public_issue", entity_id=issue.id, details=details or {})


@staff_router.get("")
def list_issues(actor: Actor = Depends(require_staff), db: Session = Depends(get_db),
                status: PublicIssueStatus | None = None, progress: PublicIssueProgress | None = None,
                category: Category | None = None, q: str | None = Query(default=None, max_length=100)):
    stmt = select(PublicIssue).where(_issue_scope(actor))
    if status:
        stmt = stmt.where(PublicIssue.status == status)
    if progress:
        stmt = stmt.where(PublicIssue.progress == progress)
    if category:
        stmt = stmt.where(PublicIssue.category == category)
    if q:
        stmt = stmt.where(PublicIssue.title.ilike(f"%{q}%"))
    return [staff_issue_dict(db, actor, i) for i in db.scalars(stmt.order_by(PublicIssue.updated_at.desc()))]


@staff_router.post("", status_code=201)
def create_issue(body: IssueIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    complaints = _complaints_for_link(db, actor, body.complaint_ids)
    first = complaints[0]
    lat, lng = _approx(complaints)
    issue = PublicIssue(title=body.title.strip(), description=body.description.strip(),
                        general_location=(body.general_location or "").strip() or None, latitude=lat, longitude=lng,
                        category=first.category, department_id=first.department_id, department_unit_id=first.department_unit_id,
                        jurisdiction_id=first.jurisdiction_id, created_by=actor.user_id)
    db.add(issue)
    db.flush()
    for c in complaints:
        db.add(PublicIssueComplaint(issue_id=issue.id, complaint_id=c.id, linked_by=actor.user_id))
    _log(db, actor, "PUBLIC_ISSUE_CREATED", issue, {"complaints": [c.reference_id for c in complaints]})
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.get("/{issue_id}")
def get_issue(issue_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    return staff_issue_dict(db, actor, _get_issue(db, actor, issue_id), True)


@staff_router.patch("/{issue_id}")
def update_issue(issue_id: uuid.UUID, body: IssuePatch, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    issue = _get_issue(db, actor, issue_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(issue, k, v.strip() if isinstance(v, str) else v)
    _log(db, actor, "PUBLIC_ISSUE_UPDATED", issue, changes)
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.post("/{issue_id}/verify")
def verify_issue(issue_id: uuid.UUID, body: VerifyIssueIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    if not _can_approve(actor):
        raise err("FORBIDDEN", message="Only a department administrator can verify a public issue.")
    issue = _get_issue(db, actor, issue_id, lock=True)
    issue.impact_level, issue.impact_assessment = body.impact_level, body.impact_assessment.strip()
    if issue.status == PublicIssueStatus.DRAFT:
        issue.status = PublicIssueStatus.VERIFIED
    issue.verified_by, issue.verified_at = actor.user_id, _now()
    _log(db, actor, "PUBLIC_ISSUE_VERIFIED", issue, body.model_dump())
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.post("/{issue_id}/publish")
def publish_issue(issue_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    if not _can_approve(actor):
        raise err("FORBIDDEN", message="Publishing needs approval from a department administrator.")
    issue = _get_issue(db, actor, issue_id, lock=True)
    if issue.status not in (PublicIssueStatus.VERIFIED, PublicIssueStatus.UNPUBLISHED) or not issue.impact_assessment:
        raise err("INVALID_STATUS_TRANSITION", message="Verify the issue and record its impact assessment before publishing.")
    issue.status, issue.published_by, issue.published_at = PublicIssueStatus.PUBLISHED, actor.user_id, _now()
    _log(db, actor, "PUBLIC_ISSUE_PUBLISHED", issue)
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.post("/{issue_id}/unpublish")
def unpublish_issue(issue_id: uuid.UUID, body: ReasonIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    if not _can_approve(actor):
        raise err("FORBIDDEN")
    issue = _get_issue(db, actor, issue_id, lock=True)
    if issue.status != PublicIssueStatus.PUBLISHED:
        raise err("INVALID_STATUS_TRANSITION", message="Only a published issue can be unpublished.")
    issue.status = PublicIssueStatus.UNPUBLISHED
    _log(db, actor, "PUBLIC_ISSUE_UNPUBLISHED", issue, {"reason": body.reason})
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.post("/{issue_id}/updates", status_code=201)
def add_update(issue_id: uuid.UUID, body: IssueUpdateIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    issue = _get_issue(db, actor, issue_id, lock=True)
    if body.progress == PublicIssueProgress.RESOLVED:
        if not _can_approve(actor):
            raise err("FORBIDDEN", message="Only a department administrator can mark a public issue resolved.")
        if not (body.resolution_info or "").strip():
            raise err("REASON_REQUIRED", message="Describe how the issue was resolved.", details={"field": "resolution_info"})
        issue.resolution_info, issue.resolved_at = body.resolution_info.strip(), _now()
    if body.progress:
        issue.progress = body.progress
    db.add(PublicIssueUpdate(issue_id=issue.id, message=body.message.strip(), progress=body.progress, author_id=actor.user_id))
    issue.updated_at = _now()
    _log(db, actor, "PUBLIC_ISSUE_PROGRESS", issue, body.model_dump())
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.post("/{issue_id}/complaints")
def link_complaints(issue_id: uuid.UUID, body: LinkIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    issue = _get_issue(db, actor, issue_id, lock=True)
    complaints = _complaints_for_link(db, actor, body.complaint_ids, issue.department_unit_id)
    for c in complaints:
        db.add(PublicIssueComplaint(issue_id=issue.id, complaint_id=c.id, linked_by=actor.user_id))
    db.flush()
    issue.latitude, issue.longitude = _approx(_linked(db, issue.id))
    _log(db, actor, "PUBLIC_ISSUE_LINKED", issue, {"complaints": [c.reference_id for c in complaints]})
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


@staff_router.delete("/{issue_id}/complaints/{complaint_id}")
def unlink_complaint(issue_id: uuid.UUID, complaint_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    issue = _get_issue(db, actor, issue_id, lock=True)
    link = db.scalar(select(PublicIssueComplaint).where(PublicIssueComplaint.issue_id == issue.id,
                                                        PublicIssueComplaint.complaint_id == complaint_id))
    if link is None:
        raise err("NOT_FOUND")
    if db.scalar(select(func.count()).select_from(PublicIssueComplaint).where(PublicIssueComplaint.issue_id == issue.id)) <= 1:
        raise err("CONFLICT", message="A public issue needs at least one related complaint.")
    db.delete(link)
    db.flush()
    issue.latitude, issue.longitude = _approx(_linked(db, issue.id))
    _log(db, actor, "PUBLIC_ISSUE_UNLINKED", issue, {"complaint_id": complaint_id})
    db.commit()
    return staff_issue_dict(db, actor, issue, True)


# ====================== public issues (public, PII-free) ======================
def public_issue_dict(db: Session, i: PublicIssue, detail: bool = False) -> dict:
    n = db.scalar(select(func.count()).select_from(PublicIssueComplaint).where(PublicIssueComplaint.issue_id == i.id)) or 0
    ups = _updates(db, i.id)
    out = {"id": i.id, "title": i.title, "description": i.description, "general_location": i.general_location,
           "category": i.category, "department": i.department.name if i.department else None,
           "area": i.jurisdiction.name if i.jurisdiction else None,
           "verification": "Verified by the department" if i.verified_at else None, "impact_level": i.impact_level,
           "related_complaints": n, "progress": i.progress, "resolution_info": i.resolution_info,
           "latitude": i.latitude, "longitude": i.longitude, "published_at": i.published_at, "resolved_at": i.resolved_at,
           "last_update": ups[0].created_at if ups else i.published_at}
    if detail:
        out["updates"] = [{"message": u.message, "progress": u.progress, "created_at": u.created_at} for u in ups]
    return out


@public_router.get("")
def public_issues(db: Session = Depends(get_db), category: Category | None = None, progress: PublicIssueProgress | None = None,
                  q: str | None = Query(default=None, max_length=100), limit: int = Query(default=50, le=200), offset: int = 0):
    stmt = select(PublicIssue).where(PublicIssue.status == PublicIssueStatus.PUBLISHED)
    if category:
        stmt = stmt.where(PublicIssue.category == category)
    if progress:
        stmt = stmt.where(PublicIssue.progress == progress)
    if q:
        stmt = stmt.where(PublicIssue.title.ilike(f"%{q}%") | PublicIssue.general_location.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(PublicIssue.updated_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [public_issue_dict(db, i) for i in rows]}


@public_router.get("/{issue_id}")
def public_issue(issue_id: uuid.UUID, db: Session = Depends(get_db)):
    i = db.scalar(select(PublicIssue).where(PublicIssue.id == issue_id, PublicIssue.status == PublicIssueStatus.PUBLISHED))
    if i is None:
        raise err("NOT_FOUND")
    return public_issue_dict(db, i, True)

