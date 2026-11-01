import uuid

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import cast, func, or_, select
from sqlalchemy.orm import Session

from geoalchemy2 import Geography
from geoalchemy2.functions import ST_DWithin

from app import audit
from app.ai import ai_service
from app.ai.ai_service import AIUnavailable, MediaInput
from app.core.db import get_db
from app.core.errors import err
from app.core.ratelimit import rate_limit
from app.geospatial import make_point
from app.models import AIAnalysis, Complaint, Media, StatusHistory
from app.models.enums import Category, ComplaintStatus, MediaPurpose
from app.schemas import (
    AnalyzeRequest,
    ComplaintCreate,
    ComplaintCreated,
    ComplaintPatch,
    FeedbackOut,
    FeedbackRequest,
    RelationshipDecision,
)
from app.security.deps import get_current_actor, require_citizen, require_staff, require_system_admin
from app.security.permissions import Actor, in_department_scope
from app.services import workflow
from app.services.complaints import (
    get_visible_complaint,
    run_routing,
    validate_complaint_input,
    validate_location,
)
from app.services.media import check_media_counts
from app.services.storage import StorageError, get_storage
from app.services.views import (
    ROLE_LABEL,
    complaint_detail,
    filter_public_complaint,
    is_public,
    list_item,
    related_view,
)

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


class TranscribeRequest(BaseModel):
    media_id: uuid.UUID


@router.post("/transcribe")
def transcribe(body: TranscribeRequest, actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    """Speech-to-text for a voice note the citizen just uploaded, so they can review and edit the text.
    Works for any language the speech model supports. Returns 503 AI_NOT_CONFIGURED when unavailable."""
    m = db.get(Media, body.media_id)
    if m is None or m.uploaded_by != actor.user_id or m.complaint_id is not None or m.media_type.value != "AUDIO":
        raise err("MEDIA_NOT_AVAILABLE", status_code=422)
    try:
        data = get_storage().get(m.storage_key)
    except StorageError:
        raise err("MEDIA_STORAGE_FAILURE")
    try:
        result = ai_service.transcribe_audio(MediaInput(str(m.id), "AUDIO", m.mime_type, data))
    except AIUnavailable as exc:
        raise err(exc.code, details={"ai_status": exc.code, "manual_submission_available": True})
    audit.record(db, actor_id=actor.user_id, action="AUDIO_TRANSCRIBED", entity_type="media", entity_id=m.id)
    db.commit()
    return {"transcription": result.transcription, "language": result.language,
            "note": "Machine transcription. Please check and correct it before submitting."}


@router.post("/analyze")
def analyze(body: AnalyzeRequest, actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    """Analyze text and/or media and return a structured preview. Never creates a complaint."""
    media = []
    if body.media_ids:
        media = db.scalars(select(Media).where(Media.id.in_(body.media_ids))).all()
        if len(media) != len(set(body.media_ids)) or any(m.uploaded_by != actor.user_id or m.complaint_id is not None for m in media):
            raise err("MEDIA_NOT_AVAILABLE", status_code=422)
        check_media_counts([m.media_type for m in media])
    description = validate_complaint_input(body.description, bool(media))
    if body.location is not None and (body.location.latitude is not None or body.location.longitude is not None):
        validate_location(body.location)

    try:
        inputs = []
        if ai_service.ai_status().mode == "configured":
            for m in media:
                try:
                    inputs.append(MediaInput(str(m.id), m.media_type.value, m.mime_type, get_storage().get(m.storage_key)))
                except StorageError:
                    raise err("MEDIA_STORAGE_FAILURE")
        loc_meta = body.location.model_dump(mode="json") if body.location else {}
        loc_meta["citizen_category"] = body.category.value if body.category else None
        analysis = ai_service.analyze_complaint(description, inputs, loc_meta)
    except AIUnavailable as exc:
        audit.record(db, actor_id=actor.user_id, action="AI_ANALYSIS_FAILED", entity_type="ai", details={"code": exc.code})
        db.commit()
        raise err(exc.code, details={"ai_status": exc.code, "manual_submission_available": True})

    from app.core.config import get_settings
    s = get_settings()
    row = AIAnalysis(
        requested_by=actor.user_id, model_identifier=f"{s.AI_PROVIDER}:{s.AI_MODEL_NAME}", model_version=None,
        suggested_category=analysis.suggested_category, summary=analysis.suggested_summary,
        confidence=analysis.classification_confidence, confidence_band=analysis.confidence_band,
        confidence_method=analysis.confidence_method, structured_output=analysis.model_dump(mode="json"),
        input_media_ids=[str(m.id) for m in media], review_required=analysis.requires_human_review,
    )
    db.add(row)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="AI_ANALYSIS_CREATED", entity_type="ai_analysis", entity_id=row.id,
                 details={"review_required": row.review_required})
    db.commit()
    return {"analysis_id": row.id, "is_ai_suggestion": True, "model_identifier": row.model_identifier,
            **analysis.model_dump(mode="json")}


@router.post("", status_code=201, response_model=ComplaintCreated,
             dependencies=[Depends(rate_limit("complaint_create", "RATE_LIMIT_COMPLAINT_CREATE"))])
def create(body: ComplaintCreate, response: Response, actor: Actor = Depends(require_citizen), db: Session = Depends(get_db),
           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=100)):
    from app.services.complaints import create_complaint, latest_routing_decision
    from app.routing.engine import MESSAGES

    complaint, created, routing, related = create_complaint(db, actor, body, idempotency_key)
    if not created:
        response.status_code = 200
    rd = latest_routing_decision(db, complaint.id)
    return ComplaintCreated(
        complaint_id=complaint.id,
        reference_id=complaint.reference_id,
        status=complaint.status,
        priority_score=float(complaint.priority_score) if complaint.priority_score is not None else None,
        priority_level=complaint.priority_level,
        priority_assessment_status=complaint.priority_assessment_status,
        routing_status=complaint.routing_status,
        routing_message=MESSAGES.get(rd.reason_code, MESSAGES[complaint.routing_status.value]) if rd else "",
        department={"id": str(complaint.department.id), "name": complaint.department.name} if complaint.department else None,
        related_candidates=related,
        created_at=complaint.created_at,
    )


def _scope_filter(actor: Actor):
    if actor.role.value == "CITIZEN":
        return Complaint.citizen_id == actor.user_id
    if actor.is_system_admin:
        return Complaint.id.is_not(None)
    if actor.officer_active and actor.department_id:
        return Complaint.department_id == actor.department_id
    return Complaint.id.is_(None)


@router.get("")
def list_complaints(
    actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db),
    status: ComplaintStatus | None = None, category: Category | None = None,
    q: str | None = Query(default=None, max_length=100), limit: int = Query(default=50, le=200), offset: int = 0,
):
    stmt = select(Complaint).where(_scope_filter(actor))
    if status:
        stmt = stmt.where(Complaint.status == status)
    if category:
        stmt = stmt.where(Complaint.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Complaint.reference_id.ilike(like), Complaint.title.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Complaint.created_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [list_item(db, c, actor.is_staff) for c in rows]}


@router.get("/summary")
def citizen_summary(actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    rows = dict(db.execute(select(Complaint.status, func.count()).where(Complaint.citizen_id == actor.user_id)
                           .group_by(Complaint.status)).all())
    g = lambda *ss: sum(rows.get(s, 0) for s in ss)  # noqa: E731
    return {
        "total": sum(rows.values()),
        "under_review": g(ComplaintStatus.SUBMITTED, ComplaintStatus.UNDER_REVIEW, ComplaintStatus.REOPENED),
        "in_progress": g(ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS, ComplaintStatus.ON_HOLD),
        "awaiting_verification": g(ComplaintStatus.RESOLVED_AWAITING_VERIFICATION),
        "verified_resolved": g(ComplaintStatus.VERIFIED_RESOLVED),
        "rejected": g(ComplaintStatus.REJECTED),
        "by_status": {k.value: v for k, v in rows.items()},
    }


@router.get("/nearby")
def nearby_public(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                  category: Category | None = None, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    """E18 pre-submission check: privacy-filtered public reports near a location."""
    from app.core.config import get_settings
    pt = cast(make_point(latitude, longitude), Geography)
    stmt = select(Complaint).where(ST_DWithin(Complaint.location, pt, get_settings().DUPLICATE_RADIUS_M * 2))
    if category:
        stmt = stmt.where(Complaint.category == category)
    rows = [c for c in db.scalars(stmt.limit(50)) if is_public(c)]
    items = [filter_public_complaint(c) for c in rows]
    return {
        "items": items,
        "message": "We found potentially related reports. Please review them before submitting." if items else None,
        "note": "Only privacy-reviewed public reports are shown. Your own complaint is always kept as a separate record.",
    }


@router.get("/{complaint_id}")
def get_complaint(complaint_id: uuid.UUID, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    return complaint_detail(db, actor, get_visible_complaint(db, actor, complaint_id))


@router.patch("/{complaint_id}")
def patch_complaint(complaint_id: uuid.UUID, body: ComplaintPatch, actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    complaint = get_visible_complaint(db, actor, complaint_id, lock=True)
    if complaint.status != ComplaintStatus.SUBMITTED:
        raise err("CONFLICT", message="This complaint can no longer be edited because review has started.")
    changes = body.model_dump(exclude_unset=True)
    if "description" in changes:
        changes["citizen_confirmed_description"] = validate_complaint_input(changes.pop("description"), False)
        if not changes["citizen_confirmed_description"]:
            raise err("EMPTY_COMPLAINT")
    before = {k: getattr(complaint, k) for k in changes}
    for k, v in changes.items():
        setattr(complaint, k, v.strip() if isinstance(v, str) else v)
    complaint.version += 1
    audit.record(db, actor_id=actor.user_id, action="COMPLAINT_EDITED", entity_type="complaint", entity_id=complaint.id,
                 details={"before": before, "after": changes})
    db.commit()
    return complaint_detail(db, actor, complaint)


@router.get("/{complaint_id}/history")
def history(complaint_id: uuid.UUID, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)):
    complaint = get_visible_complaint(db, actor, complaint_id)
    rows = db.scalars(select(StatusHistory).where(StatusHistory.complaint_id == complaint.id).order_by(StatusHistory.created_at)).all()
    return [
        {"previous_status": h.previous_status, "new_status": h.new_status, "actor_role": ROLE_LABEL[h.actor_role] if h.actor_role else "CivicConnect (automatic)",
         **({"actor_id": h.actor_id} if actor.is_staff else {}), "remarks": h.remarks, "created_at": h.created_at}
        for h in rows
    ]


@router.post("/{complaint_id}/feedback", status_code=201, response_model=FeedbackOut)
def feedback(complaint_id: uuid.UUID, body: FeedbackRequest, actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    complaint = get_visible_complaint(db, actor, complaint_id, lock=True)
    fb = workflow.submit_feedback(db, actor, complaint, body.feedback_type, body.remarks)
    return FeedbackOut(feedback_id=fb.id, complaint_id=fb.complaint_id, feedback_type=fb.feedback_type, remarks=fb.remarks,
                       review_status=fb.review_status, reviewed_by=fb.reviewed_by, reviewed_at=fb.reviewed_at,
                       decision_reason=fb.decision_reason, created_at=fb.created_at)


class CitizenReply(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/{complaint_id}/remarks", status_code=201)
def citizen_reply(complaint_id: uuid.UUID, body: CitizenReply, actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    """Citizen reply, e.g. to a clarification request. Always citizen-visible."""
    complaint = get_visible_complaint(db, actor, complaint_id)
    r = workflow.add_citizen_reply(db, actor, complaint, body.text)
    return {"remark_id": r.id, "created_at": r.created_at}


@router.get("/{complaint_id}/related")
def related(complaint_id: uuid.UUID, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    complaint = get_visible_complaint(db, actor, complaint_id)
    return related_view(db, actor, complaint)


@router.post("/{complaint_id}/relationships")
def relationship(complaint_id: uuid.UUID, body: RelationshipDecision, actor: Actor = Depends(require_staff), db: Session = Depends(get_db)):
    rel = workflow.decide_relationship(db, actor, complaint_id, body.related_complaint_id, body.relationship_status)
    return {"relationship_id": rel.id, "relationship_status": rel.relationship_status, "reviewed_at": rel.reviewed_at}


@router.post("/{complaint_id}/route")
def route(complaint_id: uuid.UUID, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Re-run deterministic routing (e.g. after configuration changes)."""
    complaint = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if complaint is None:
        raise err("COMPLAINT_NOT_FOUND")
    result = run_routing(db, complaint, actor_id=actor.user_id)
    db.commit()
    return {"routing_status": result.routing_status, "reason_code": result.reason_code, "message": result.message,
            "explanation": result.explanation, "department_id": result.department_id}
