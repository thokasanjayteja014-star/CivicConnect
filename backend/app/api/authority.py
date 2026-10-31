import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.api.media import read_limited
from app.core.db import get_db
from app.core.errors import err
from app.core.ratelimit import rate_limit
from app.models import Assignment, CitizenFeedback, Complaint, Officer, User
from app.models.enums import (
    AssignmentStatus,
    Category,
    ComplaintStatus as S,
    PriorityLevel,
    ReviewStatus,
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
from app.services import workflow
from app.services.complaints import run_priority
from app.services.views import complaint_detail, list_item

router = APIRouter(prefix="/api/authority", tags=["authority"])


def scope(actor: Actor):
    if actor.is_system_admin:
        return Complaint.routing_status == RoutingStatus.ROUTED
    if actor.officer_active and actor.department_id:
        return Complaint.department_id == actor.department_id
    return Complaint.id.is_(None)


@router.get("/dashboard")
def dashboard(actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    rows = dict(db.execute(select(Complaint.status, func.count()).where(scope(actor)).group_by(Complaint.status)).all())
    prio = dict(db.execute(select(Complaint.priority_level, func.count()).where(scope(actor))
                           .group_by(Complaint.priority_level)).all())
    cats = dict(db.execute(select(Complaint.category, func.count()).where(scope(actor)).group_by(Complaint.category)).all())
    workload = db.execute(
        select(Officer.id, User.full_name, Officer.designation, func.count(Assignment.id))
        .join(User, User.id == Officer.user_id)
        .join(Assignment, (Assignment.officer_id == Officer.id) & (Assignment.assignment_status == AssignmentStatus.ACTIVE), isouter=True)
        .join(Complaint, Complaint.id == Assignment.complaint_id, isouter=True)
        .where(Officer.department_id == actor.department_id if not actor.is_system_admin else Officer.id.is_not(None))
        .group_by(Officer.id, User.full_name, Officer.designation)
    ).all()
    pending_reopen = db.scalar(
        select(func.count()).select_from(CitizenFeedback).join(Complaint, Complaint.id == CitizenFeedback.complaint_id)
        .where(scope(actor), CitizenFeedback.review_status == ReviewStatus.PENDING)
    )
    prompt = db.scalar(select(func.count()).select_from(Complaint).where(
        scope(actor), Complaint.needs_prompt_review.is_(True), Complaint.status.in_([S.SUBMITTED, S.UNDER_REVIEW])))
    return {
        "scope": "ALL_ROUTED" if actor.is_system_admin else "DEPARTMENT",
        "department_id": actor.department_id,
        "total": sum(rows.values()),
        "awaiting_review": rows.get(S.SUBMITTED, 0) + rows.get(S.REOPENED, 0),
        "under_review": rows.get(S.UNDER_REVIEW, 0),
        "assigned": rows.get(S.ASSIGNED, 0),
        "in_progress": rows.get(S.IN_PROGRESS, 0),
        "on_hold": rows.get(S.ON_HOLD, 0),
        "awaiting_verification": rows.get(S.RESOLVED_AWAITING_VERIFICATION, 0),
        "verified_resolved": rows.get(S.VERIFIED_RESOLVED, 0),
        "rejected": rows.get(S.REJECTED, 0),
        "pending_reopen_reviews": pending_reopen,
        "prompt_safety_reviews": prompt,
        "by_status": {k.value: v for k, v in rows.items()},
        "by_priority": {(k.value if k else "UNSCORED"): v for k, v in prio.items()},
        "by_category": {k.value: v for k, v in cats.items()},
        "officer_workload": [{"officer_id": o, "full_name": n, "designation": d, "active_assignments": c} for o, n, d, c in workload],
    }


@router.get("/complaints")
def complaints(
    actor: Actor = Depends(require_staff), db: Session = Depends(get_db),
    category: Category | None = None, priority: PriorityLevel | None = None, status: S | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
    min_lat: float | None = None, max_lat: float | None = None, min_lng: float | None = None, max_lng: float | None = None,
    officer_id: uuid.UUID | None = None, unscored: bool = False, q: str | None = Query(default=None, max_length=100),
    sort: str = Query(default="newest", pattern="^(newest|oldest|priority)$"),
    limit: int = Query(default=50, le=200), offset: int = 0,
):
    stmt = select(Complaint).where(scope(actor))
    if category:
        stmt = stmt.where(Complaint.category == category)
    if priority:
        stmt = stmt.where(Complaint.priority_level == priority)
    if unscored:
        stmt = stmt.where(Complaint.priority_level.is_(None))
    if status:
        stmt = stmt.where(Complaint.status == status)
    if date_from:
        stmt = stmt.where(Complaint.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Complaint.created_at <= date_to)
    if None not in (min_lat, max_lat, min_lng, max_lng):
        stmt = stmt.where(Complaint.latitude.between(min_lat, max_lat), Complaint.longitude.between(min_lng, max_lng))
    if officer_id:
        stmt = stmt.join(Assignment, Assignment.complaint_id == Complaint.id).where(
            Assignment.officer_id == officer_id, Assignment.assignment_status == AssignmentStatus.ACTIVE)
    if q:
        stmt = stmt.where(Complaint.reference_id.ilike(f"%{q}%") | Complaint.title.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {
        "newest": [Complaint.created_at.desc()],
        "oldest": [Complaint.created_at.asc()],
        "priority": [Complaint.needs_prompt_review.desc(), Complaint.priority_score.desc().nulls_last(), Complaint.created_at.asc()],
    }[sort]
    rows = db.scalars(stmt.order_by(*order).limit(limit).offset(offset)).all()
    return {"total": total, "items": [list_item(db, c, True) for c in rows]}


@router.get("/complaints/{complaint_id}")
def complaint(complaint_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    c = db.get(Complaint, complaint_id)
    if c is None or not in_department_scope(actor, c.department_id):
        raise err("COMPLAINT_NOT_FOUND")
    return complaint_detail(db, actor, c)


@router.get("/officers")
def officers(department_id: uuid.UUID | None = None, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    dept = department_id if actor.is_system_admin and department_id else actor.department_id
    if dept is None:
        return []
    rows = db.execute(select(Officer, User).join(User, User.id == Officer.user_id).where(Officer.department_id == dept)).all()
    return [{"officer_id": o.id, "full_name": u.full_name, "designation": o.designation, "role": u.role,
             "eligible": o.active and u.account_status.value == "ACTIVE"} for o, u in rows]


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
    elif actor.officer_active and actor.department_id:
        stmt = stmt.where(Complaint.department_id == actor.department_id)
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
