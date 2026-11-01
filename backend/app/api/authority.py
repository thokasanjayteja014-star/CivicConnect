import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.api.media import read_limited
from app.core.db import get_db
from app.core.errors import err
from app.core.ratelimit import rate_limit
from app.models import Assignment, CitizenFeedback, Complaint, DepartmentUnit, Escalation, Officer, User
from app.models.enums import (
    AssignmentStatus,
    Category,
    ComplaintStatus as S,
    EscalationStatus,
    PriorityLevel,
    ReviewStatus,
    Role,
    RoutingStatus,
)
from app.priority.engine import FACTORS, FactorValue
from app.schemas import (
    AssignRequest,
    PriorityFactorsIn,
    PublicationRequest,
    RemarkRequest,
    ReviewDecision,
    StatusChange,
    VerifyRequest,
)
from app.security.deps import require_staff
from app.security.permissions import Actor, in_department_scope
from app.services import escalation as esc_service, workflow
from app.services.hierarchy import descendant_ids, jurisdiction_path
from app.services.complaints import run_priority
from app.services.views import complaint_detail, list_item

router = APIRouter(prefix="/api/authority", tags=["authority"])


def scope(actor: Actor):
    """SQL twin of permissions.in_department_scope."""
    if actor.is_system_admin:
        return Complaint.routing_status == RoutingStatus.ROUTED
    if actor.role not in (Role.DEPARTMENT_ADMIN, Role.OFFICER) or not actor.officer_active or actor.unit_id is None:
        return Complaint.id.is_(None)
    assigned = exists().where(Assignment.complaint_id == Complaint.id, Assignment.officer_id == actor.officer_id)
    if actor.role == Role.OFFICER:
        in_unit = Complaint.department_unit_id == actor.unit_id
        if actor.area_ids:
            in_unit = and_(in_unit, Complaint.jurisdiction_id.in_(list(actor.area_ids)))
        return or_(in_unit, assigned)
    return Complaint.department_unit_id == actor.unit_id


OPEN = [S.SUBMITTED, S.UNDER_REVIEW, S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.REOPENED]
ACTIVE_ASSIGNMENT = exists().where(Assignment.complaint_id == Complaint.id, Assignment.assignment_status == AssignmentStatus.ACTIVE)
OPEN_ESCALATION = exists().where(Escalation.complaint_id == Complaint.id, Escalation.status == EscalationStatus.OPEN)


def _overdue(now):
    return and_(Complaint.due_at.is_not(None), Complaint.due_at < now, Complaint.status.in_(OPEN))


def _unit_label(db: Session, unit_id):
    u = db.get(DepartmentUnit, unit_id) if unit_id else None
    return {"id": u.id, "department": u.department.name, "jurisdiction": u.jurisdiction.name,
            "jurisdiction_path": jurisdiction_path(db, u.jurisdiction_id)} if u else None


@router.get("/dashboard")
def dashboard(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    esc_service.run_overdue_escalations(db)
    now = datetime.now(timezone.utc)
    sc = scope(actor)
    rows = dict(db.execute(select(Complaint.status, func.count()).where(sc).group_by(Complaint.status)).all())
    prio = dict(db.execute(select(Complaint.priority_level, func.count()).where(sc)
                           .group_by(Complaint.priority_level)).all())
    cats = dict(db.execute(select(Complaint.category, func.count()).where(sc).group_by(Complaint.category)).all())
    count = lambda *w: db.scalar(select(func.count()).select_from(Complaint).where(sc, *w)) or 0  # noqa: E731
    officer_filter = Officer.unit_id == actor.unit_id if not actor.is_system_admin else Officer.id.is_not(None)
    workload = db.execute(
        select(Officer.id, User.full_name, Officer.designation, func.count(Assignment.id))
        .join(User, User.id == Officer.user_id)
        .join(Assignment, (Assignment.officer_id == Officer.id) & (Assignment.assignment_status == AssignmentStatus.ACTIVE), isouter=True)
        .where(officer_filter, User.role == Role.OFFICER)
        .group_by(Officer.id, User.full_name, Officer.designation)
    ).all() if actor.role != Role.OFFICER else []
    pending_reopen = db.scalar(
        select(func.count()).select_from(CitizenFeedback).join(Complaint, Complaint.id == CitizenFeedback.complaint_id)
        .where(sc, CitizenFeedback.review_status == ReviewStatus.PENDING)
    )
    prompt = count(Complaint.needs_prompt_review.is_(True), Complaint.status.in_([S.SUBMITTED, S.UNDER_REVIEW]))
    mine = {}
    if actor.role == Role.OFFICER and actor.officer_id:
        my = and_(Assignment.complaint_id == Complaint.id, Assignment.officer_id == actor.officer_id,
                  Assignment.assignment_status == AssignmentStatus.ACTIVE)
        mine = {"assigned_to_me": count(exists().where(my)),
                "awaiting_acceptance": count(exists().where(my, Assignment.accepted_at.is_(None))),
                "my_overdue": count(exists().where(my), _overdue(now))}
    return {
        "scope": "ALL_ROUTED" if actor.is_system_admin else ("OFFICER" if actor.role == Role.OFFICER else "UNIT"),
        "department_id": actor.department_id,
        "unit": _unit_label(db, actor.unit_id),
        "total": sum(rows.values()),
        "awaiting_review": rows.get(S.SUBMITTED, 0) + rows.get(S.REOPENED, 0),
        "awaiting_assignment": count(Complaint.status.in_([S.SUBMITTED, S.UNDER_REVIEW, S.REOPENED]), ~ACTIVE_ASSIGNMENT),
        "under_review": rows.get(S.UNDER_REVIEW, 0),
        "assigned": rows.get(S.ASSIGNED, 0),
        "in_progress": rows.get(S.IN_PROGRESS, 0),
        "on_hold": rows.get(S.ON_HOLD, 0),
        "awaiting_verification": rows.get(S.RESOLVED_AWAITING_VERIFICATION, 0),
        "verified_resolved": rows.get(S.VERIFIED_RESOLVED, 0),
        "rejected": rows.get(S.REJECTED, 0),
        "overdue": count(_overdue(now)),
        "escalated": count(OPEN_ESCALATION),
        "pending_reopen_reviews": pending_reopen,
        "prompt_safety_reviews": prompt,
        **mine,
        "by_status": {k.value: v for k, v in rows.items()},
        "by_priority": {(k.value if k else "UNSCORED"): v for k, v in prio.items()},
        "by_category": {k.value: v for k, v in cats.items()},
        "officer_workload": [{"officer_id": o, "full_name": n, "designation": d, "active_assignments": c} for o, n, d, c in workload],
    }


@router.get("/complaints")
def complaints(
    actor: Actor = Depends(require_staff), db: Session = Depends(get_db),
    category: Category | None = None, priority: PriorityLevel | None = None, status: S | None = None,
    status_group: str | None = Query(default=None, pattern="^(open|closed)$"),
    date_from: datetime | None = None, date_to: datetime | None = None,
    min_lat: float | None = None, max_lat: float | None = None, min_lng: float | None = None, max_lng: float | None = None,
    officer_id: uuid.UUID | None = None, unscored: bool = False, q: str | None = Query(default=None, max_length=100),
    department_id: uuid.UUID | None = None, unit_id: uuid.UUID | None = None, jurisdiction_id: uuid.UUID | None = None,
    assignment: str | None = Query(default=None, pattern="^(unassigned|assigned|mine|awaiting_acceptance)$"),
    overdue: bool = False, escalated: bool = False, due_within_hours: int | None = Query(default=None, ge=1, le=24 * 60),
    sort: str = Query(default="newest", pattern="^(newest|oldest|priority|due)$"),
    limit: int = Query(default=50, le=200), offset: int = 0,
):
    now = datetime.now(timezone.utc)
    stmt = select(Complaint).where(scope(actor))
    if category:
        stmt = stmt.where(Complaint.category == category)
    if priority:
        stmt = stmt.where(Complaint.priority_level == priority)
    if unscored:
        stmt = stmt.where(Complaint.priority_level.is_(None))
    if status:
        stmt = stmt.where(Complaint.status == status)
    if status_group:
        stmt = stmt.where(Complaint.status.in_(OPEN) if status_group == "open" else Complaint.status.not_in(OPEN))
    if date_from:
        stmt = stmt.where(Complaint.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Complaint.created_at <= date_to)
    if None not in (min_lat, max_lat, min_lng, max_lng):
        stmt = stmt.where(Complaint.latitude.between(min_lat, max_lat), Complaint.longitude.between(min_lng, max_lng))
    if department_id:
        stmt = stmt.where(Complaint.department_id == department_id)
    if unit_id:
        stmt = stmt.where(Complaint.department_unit_id == unit_id)
    if jurisdiction_id:
        stmt = stmt.where(Complaint.jurisdiction_id.in_(list(descendant_ids(db, [jurisdiction_id]))))
    if officer_id:
        stmt = stmt.where(exists().where(Assignment.complaint_id == Complaint.id, Assignment.officer_id == officer_id,
                                         Assignment.assignment_status == AssignmentStatus.ACTIVE))
    if assignment == "unassigned":
        stmt = stmt.where(Complaint.status.in_(OPEN), ~ACTIVE_ASSIGNMENT)
    elif assignment == "assigned":
        stmt = stmt.where(ACTIVE_ASSIGNMENT)
    elif assignment in ("mine", "awaiting_acceptance"):
        conds = [Assignment.complaint_id == Complaint.id, Assignment.officer_id == actor.officer_id,
                 Assignment.assignment_status == AssignmentStatus.ACTIVE]
        if assignment == "awaiting_acceptance":
            conds.append(Assignment.accepted_at.is_(None))
        stmt = stmt.where(exists().where(*conds))
    if overdue:
        stmt = stmt.where(_overdue(now))
    if escalated:
        stmt = stmt.where(OPEN_ESCALATION)
    if due_within_hours:
        stmt = stmt.where(Complaint.status.in_(OPEN), Complaint.due_at.between(now, now + timedelta(hours=due_within_hours)))
    if q:
        stmt = stmt.where(Complaint.reference_id.ilike(f"%{q}%") | Complaint.title.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {
        "newest": [Complaint.created_at.desc()],
        "oldest": [Complaint.created_at.asc()],
        "priority": [Complaint.needs_prompt_review.desc(), Complaint.priority_score.desc().nulls_last(), Complaint.created_at.asc()],
        "due": [Complaint.due_at.asc().nulls_last(), Complaint.created_at.asc()],
    }[sort]
    rows = db.scalars(stmt.order_by(*order).limit(limit).offset(offset)).all()
    return {"total": total, "items": [list_item(db, c, True) for c in rows]}


@router.get("/complaints/{complaint_id}")
def complaint(complaint_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = db.get(Complaint, complaint_id)
    if c is None or not in_department_scope(actor, c, db):
        raise err("COMPLAINT_NOT_FOUND")
    return complaint_detail(db, actor, c)


@router.get("/officers")
def officers(unit_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
             actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    """Officers of a department unit with workload and operational areas (for assignment)."""
    if actor.is_system_admin:
        stmt = select(Officer, User).join(User, User.id == Officer.user_id).where(User.role == Role.OFFICER)
        if unit_id:
            stmt = stmt.where(Officer.unit_id == unit_id)
        elif department_id:
            stmt = stmt.where(Officer.department_id == department_id)
    elif actor.unit_id:
        stmt = select(Officer, User).join(User, User.id == Officer.user_id).where(
            Officer.unit_id == actor.unit_id, User.role == Role.OFFICER)
    else:
        return []
    rows = db.execute(stmt.order_by(User.full_name)).all()
    load = dict(db.execute(select(Assignment.officer_id, func.count()).where(
        Assignment.assignment_status == AssignmentStatus.ACTIVE).group_by(Assignment.officer_id)).all())
    return [{"officer_id": o.id, "user_id": u.id, "full_name": u.full_name, "designation": o.designation, "role": u.role,
             "unit_id": o.unit_id, "active_assignments": int(load.get(o.id, 0)),
             "areas": [{"jurisdiction_id": a.jurisdiction_id, "name": a.jurisdiction.name} for a in o.areas],
             "eligible": o.active and u.account_status.value == "ACTIVE"} for o, u in rows]


@router.post("/complaints/{complaint_id}/accept")
def accept(complaint_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    workflow.accept_assignment(db, actor, complaint_id)
    return complaint_detail(db, actor, db.get(Complaint, complaint_id))


class EscalateIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class ResolveEscalationIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.post("/complaints/{complaint_id}/escalate", status_code=201)
def escalate(complaint_id: uuid.UUID, body: EscalateIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if c is None or not in_department_scope(actor, c, db):
        raise err("COMPLAINT_NOT_FOUND")
    if actor.is_system_admin:
        raise err("FORBIDDEN", message="Main administrators receive escalations; they do not raise them.")
    return esc_service.escalation_dict(esc_service.escalate_manually(db, actor, c, body.reason))


@router.get("/escalations")
def escalations(actor: Actor = Depends(require_staff), db: Session = Depends(get_db),
                status: EscalationStatus | None = EscalationStatus.OPEN, level: int | None = Query(default=None, ge=1, le=2),
                limit: int = Query(default=100, le=500)):
    esc_service.run_overdue_escalations(db)
    stmt = select(Escalation).join(Complaint, Complaint.id == Escalation.complaint_id).where(scope(actor))
    if status:
        stmt = stmt.where(Escalation.status == status)
    if level:
        stmt = stmt.where(Escalation.level == level)
    rows = db.scalars(stmt.order_by(Escalation.level.desc(), Escalation.created_at).limit(limit)).all()
    return [esc_service.escalation_dict(e) | {"unit": _unit_label(db, e.department_unit_id),
                                              "can_resolve": _can_resolve(actor, e)} for e in rows]


def _can_resolve(actor: Actor, e: Escalation) -> bool:
    if e.status != EscalationStatus.OPEN:
        return False
    return actor.is_system_admin or (actor.role == Role.DEPARTMENT_ADMIN and e.level == 1)


@router.post("/escalations/{escalation_id}/resolve")
def resolve_escalation(escalation_id: uuid.UUID, body: ResolveEscalationIn, actor: Actor = Depends(require_staff),
                       db: Session = Depends(get_db)):
    e = db.scalar(select(Escalation).where(Escalation.id == escalation_id).with_for_update())
    if e is None or not in_department_scope(actor, e.complaint, db):
        raise err("NOT_FOUND")
    if not _can_resolve(actor, e):
        raise err("FORBIDDEN", message="Only the department administrator (level 1) or the main administration can close this escalation.")
    return esc_service.escalation_dict(esc_service.resolve_escalation(db, actor, e, body.note or ""))


@router.post("/complaints/{complaint_id}/assign")
def assign(complaint_id: uuid.UUID, body: AssignRequest, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = workflow.assign_officer(db, actor, complaint_id, body.officer_id, body.reason, body.expected_version)
    return complaint_detail(db, actor, c)


@router.post("/complaints/{complaint_id}/status")
def status(complaint_id: uuid.UUID, body: StatusChange, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = workflow.change_status(db, actor, complaint_id, body.status, remarks=body.remarks, internal_note=body.internal_note,
                               reason=body.reason, expected_version=body.expected_version)
    return complaint_detail(db, actor, c)


@router.post("/complaints/{complaint_id}/remarks", status_code=201)
def remarks(complaint_id: uuid.UUID, body: RemarkRequest, clarification: bool = False,
            actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    r = workflow.add_staff_remark(db, actor, complaint_id, body.text, body.visibility, clarification)
    return {"remark_id": r.id, "visibility": r.visibility, "kind": r.kind, "created_at": r.created_at}


@router.post("/complaints/{complaint_id}/evidence", status_code=201,
             dependencies=[Depends(rate_limit("media", "RATE_LIMIT_MEDIA_UPLOAD"))])
async def evidence(complaint_id: uuid.UUID, file: UploadFile = File(...), description: str | None = Form(default=None, max_length=2000),
                   actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    data = await read_limited(file)
    ev = workflow.upload_evidence(db, actor, complaint_id, data, file.filename, description)
    return {"evidence_id": ev.id, "media_id": ev.media_id, "description": ev.description, "created_at": ev.created_at}


@router.post("/complaints/{complaint_id}/verify")
def verify(complaint_id: uuid.UUID, body: VerifyRequest, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = workflow.verify_resolution(db, actor, complaint_id, body.decision, body.reason, body.evidence_reviewed, body.expected_version)
    return complaint_detail(db, actor, c)


@router.post("/complaints/{complaint_id}/priority")
def priority(complaint_id: uuid.UUID, body: PriorityFactorsIn, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    """Record human-confirmed factor values; the backend recomputes the score with the configured formula."""
    c = workflow.lock_for_staff(db, actor, complaint_id, None)
    overrides = {
        f: FactorValue(float(getattr(body, f)), "HUMAN_CONFIRMED", body.explanation.strip(), f"confirmed by {actor.role.value.lower()}")
        for f in FACTORS if getattr(body, f) is not None
    }
    if not overrides:
        raise err("VALIDATION_ERROR", message="Provide at least one factor value.")
    pa = run_priority(db, c, assessed_by=actor.label, overrides=overrides)
    c.version += 1
    audit.record(db, actor_id=actor.user_id, action="PRIORITY_FACTORS_CONFIRMED", entity_type="complaint", entity_id=c.id,
                 details={"factors": {k: v.value for k, v in overrides.items()}, "result_status": pa.assessment_status,
                          "score": pa.priority_score})
    db.commit()
    return complaint_detail(db, actor, c)


@router.post("/complaints/{complaint_id}/publication")
def publication(complaint_id: uuid.UUID, body: PublicationRequest, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = workflow.set_publication(db, actor, complaint_id, body.approve, body.public_summary)
    return {"publication_status": c.publication_status, "public_summary": c.public_summary}


@router.get("/reopen-requests")
def reopen_requests(actor: Actor = Depends(require_staff), db: Session = Depends(get_db), include_decided: bool = False):
    stmt = (select(CitizenFeedback, Complaint).join(Complaint, Complaint.id == CitizenFeedback.complaint_id)
            .where(CitizenFeedback.review_status != ReviewStatus.NOT_REQUIRED))
    if actor.is_system_admin:
        pass
    elif actor.officer_active and actor.unit_id:
        stmt = stmt.where(scope(actor))
    else:
        return []
    if not include_decided:
        stmt = stmt.where(CitizenFeedback.review_status == ReviewStatus.PENDING)
    rows = db.execute(stmt.order_by(CitizenFeedback.created_at)).all()
    return [
        {"feedback_id": f.id, "complaint_id": c.id, "reference_id": c.reference_id, "title": c.title,
         "complaint_status": c.status, "feedback_type": f.feedback_type, "remarks": f.remarks,
         "review_status": f.review_status, "reviewed_by": f.reviewed_by, "reviewed_at": f.reviewed_at,
         "decision_reason": f.decision_reason, "created_at": f.created_at,
         "can_decide": workflow.can_decide_reopening(actor, c)}
        for f, c in rows
    ]


@router.post("/feedback/{feedback_id}/review")
def review(feedback_id: uuid.UUID, body: ReviewDecision, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    fb = workflow.review_feedback(db, actor, feedback_id, body.decision, body.reason)
    return {"feedback_id": fb.id, "complaint_id": fb.complaint_id, "feedback_type": fb.feedback_type,
            "review_status": fb.review_status, "reviewed_by": fb.reviewed_by, "reviewed_at": fb.reviewed_at,
            "decision_reason": fb.decision_reason, "created_at": fb.created_at}
