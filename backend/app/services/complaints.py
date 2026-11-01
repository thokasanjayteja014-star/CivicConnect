"""Complaint creation pipeline (spec L1, L5-L8) and shared complaint helpers."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Distance, ST_DWithin

from app import audit
from app.ai import ai_service
from app.core.config import get_settings
from app.core.errors import err
from app.duplicate_detection import CandidateInput, cosine, detect_duplicate_candidates
from app.geospatial import (
    any_active_jurisdiction,
    any_sensitive_location,
    make_point,
    matching_sensitive_locations,
    point_wkt,
)
from app.models import (
    AIAnalysis,
    Complaint,
    ComplaintRelationship,
    Assignment,
    Department,
    DepartmentUnit,
    Jurisdiction,
    Media,
    Officer,
    OfficerArea,
    PriorityAssessment,
    PriorityConfig,
    ResponsibilityRule,
    RoutingDecision,
    StatusHistory,
    User,
)
from app.models.enums import (
    AccountStatus,
    AssignmentStatus,
    ComplaintStatus,
    MediaPurpose,
    RelationshipStatus,
    Role,
    RoutingStatus,
)
from app.notifications import notify, unit_staff_ids
from app.priority.engine import (
    DEFAULT_PRIORITY_CONFIG,
    FactorValue,
    assess_priority,
    community_boost,
    level_for_score,
    round2,
    validate_priority_config,
)
from app.routing.engine import (
    DepartmentFact,
    LeafFact,
    OfficerFact,
    RoutingInput,
    RoutingResult,
    UnitFact,
    determine_routing,
)
from app.services import hierarchy
from app.schemas import ComplaintCreate, LocationIn
from app.security.permissions import Actor, can_view_complaint
from app.services.media import check_media_counts

DESCRIPTION_MIN = 10
DESCRIPTION_MAX = 3000


# ---------------- validation ----------------
def validate_complaint_input(description: str | None, has_media: bool) -> str | None:
    """Spec L1 / E1-E3. Returns the stripped description (or None)."""
    text = (description or "").strip()
    if not text and not has_media:
        raise err("EMPTY_COMPLAINT")
    if text and len(text) < DESCRIPTION_MIN:
        raise err("DESCRIPTION_TOO_SHORT", details={"field": "description"})
    if len(text) > DESCRIPTION_MAX:
        raise err("DESCRIPTION_TOO_LONG", details={"field": "description"})
    return text or None


def validate_location(loc: LocationIn | None) -> LocationIn:
    """Spec E4. Coordinates are never invented: both must be supplied and in range."""
    if loc is None or loc.latitude is None or loc.longitude is None:
        raise err("INVALID_COORDINATES", details={"field": "location"})
    if not (-90 <= loc.latitude <= 90) or not (-180 <= loc.longitude <= 180):
        raise err("INVALID_COORDINATES", details={"field": "location"})
    return loc


def generate_complaint_reference(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"CVC-{now:%Y%m%d}-{suffix}"


# ---------------- scope helpers ----------------
def get_visible_complaint(db: Session, actor: Actor, complaint_id: uuid.UUID, lock: bool = False) -> Complaint:
    stmt = select(Complaint).where(Complaint.id == complaint_id)
    if lock:
        stmt = stmt.with_for_update()
    complaint = db.scalar(stmt)
    if complaint is None or not can_view_complaint(actor, complaint, db):
        raise err("COMPLAINT_NOT_FOUND")  # E24: do not reveal existence
    return complaint


# ---------------- priority ----------------
def active_priority_config(db: Session) -> tuple[str, dict]:
    row = db.scalar(select(PriorityConfig).where(PriorityConfig.active.is_(True)).order_by(PriorityConfig.version.desc()))
    if row is None:
        return "v0-default", DEFAULT_PRIORITY_CONFIG
    return f"v{row.version}", validate_priority_config(row.config)


def location_sensitivity_factor(db: Session, lat: float, lng: float, cfg: dict) -> FactorValue | None:
    if not any_sensitive_location(db):
        return None  # no configured data: factor unknown, never invented
    matches = matching_sensitive_locations(db, lat, lng)
    if matches:
        loc, dist = matches[0]
        label = " (prototype configuration)" if loc.is_prototype else ""
        return FactorValue(
            float(loc.sensitivity_score),
            "ADMIN_CONFIGURED_DATA",
            f"Within {dist:.0f} m of '{loc.label}' ({loc.location_type}){label}.",
            "administrator-configured sensitive locations",
        )
    return FactorValue(
        float(cfg["ordinary_location_score"]),
        "ADMIN_CONFIGURED_DATA",
        "Not near any configured sensitive location; treated as an ordinary public area.",
        "administrator-configured sensitive locations",
    )


def run_priority(
    db: Session,
    complaint: Complaint,
    assessed_by: str,
    overrides: dict[str, FactorValue] | None = None,
) -> PriorityAssessment:
    version, cfg = active_priority_config(db)
    previous = db.scalar(
        select(PriorityAssessment)
        .where(PriorityAssessment.complaint_id == complaint.id)
        .order_by(PriorityAssessment.created_at.desc())
    )
    # Keep earlier human-confirmed values when re-assessing.
    carried: dict[str, FactorValue] = {}
    if previous:
        for name, fe in (previous.factor_evidence.get("factors") or {}).items():
            if fe.get("source") == "HUMAN_CONFIRMED":
                carried[name] = FactorValue(fe["value"], fe["source"], fe["explanation"], fe["method"])
    carried.update(overrides or {})

    result = assess_priority(
        citizen_severity=complaint.citizen_severity.value if complaint.citizen_severity else None,
        citizen_safety_risk=complaint.citizen_safety_risk.value if complaint.citizen_safety_risk else None,
        citizen_exposure=complaint.citizen_exposure.value if complaint.citizen_exposure else None,
        occurred_at=complaint.occurred_at,
        reference_time=complaint.created_at or datetime.now(timezone.utc),
        location_sensitivity=location_sensitivity_factor(db, complaint.latitude, complaint.longitude, cfg),
        config=cfg,
        overrides=carried,
    )
    f = result.factors
    others = other_reporters(db, complaint)
    boost = community_boost(others)
    community = {"other_reporters": others, "boost": boost, "base_score": float(result.priority_score)
                 if result.priority_score is not None else None,
                 "explanation": (f"{others} other resident(s) reported the same problem nearby; +{boost:g} points."
                                 if others else "No other residents have reported this problem yet.")}
    if boost and result.priority_score is not None:
        result.priority_score = round2(min(100.0, float(result.priority_score) + boost))
        result.priority_level = level_for_score(float(result.priority_score), cfg["thresholds"])
    pa = PriorityAssessment(
        complaint_id=complaint.id,
        assessment_status=result.assessment_status,
        priority_score=result.priority_score,
        priority_level=result.priority_level,
        severity_score=f["severity"].value,
        safety_risk_score=f["safety_risk"].value,
        location_sensitivity_score=f["location_sensitivity"].value,
        public_exposure_score=f["public_exposure"].value,
        duration_score=f["duration"].value,
        factor_evidence={
            "factors": {k: v.as_dict() for k, v in f.items()},
            "weights": cfg["weights"],
            "review_reasons": result.review_reasons,
            "community": community,
            "config_version": version,
            "disclaimer": "Internal prototype prioritization heuristic, not an official government urgency standard.",
        },
        needs_prompt_review=result.needs_prompt_review,
        rubric_version=f"{result.rubric_version}@{version}",
        assessed_by=assessed_by,
    )
    db.add(pa)
    complaint.priority_score = result.priority_score
    complaint.priority_level = result.priority_level
    complaint.priority_assessment_status = result.assessment_status
    complaint.needs_prompt_review = result.needs_prompt_review
    return pa


def other_reporters(db: Session, complaint: Complaint) -> int:
    """Distinct other citizens whose complaints are linked to this one as the same problem.

    Suggested and confirmed links count; links a reviewer marked NOT_RELATED, rejected complaints and
    repeat reports by the same citizen do not.
    """
    if complaint.id is None:
        return 0
    links = db.execute(select(ComplaintRelationship.source_complaint_id, ComplaintRelationship.related_complaint_id).where(
        ComplaintRelationship.relationship_status != RelationshipStatus.NOT_RELATED,
        (ComplaintRelationship.source_complaint_id == complaint.id)
        | (ComplaintRelationship.related_complaint_id == complaint.id))).all()
    ids = {b if a == complaint.id else a for a, b in links}
    if not ids:
        return 0
    return db.scalar(select(func.count(func.distinct(Complaint.citizen_id))).where(
        Complaint.id.in_(ids), Complaint.status != ComplaintStatus.REJECTED,
        Complaint.citizen_id != complaint.citizen_id)) or 0


def refresh_community_priority(db: Session, complaint_ids) -> None:
    """Re-score open complaints whose number of independent reporters changed."""
    from app.services import escalation  # local import: escalation is imported lazily here too
    db.flush()
    for cid in set(complaint_ids):
        c = db.get(Complaint, cid)
        if c is None or c.status in (ComplaintStatus.VERIFIED_RESOLVED, ComplaintStatus.REJECTED):
            continue
        latest = db.scalar(select(PriorityAssessment).where(PriorityAssessment.complaint_id == c.id)
                           .order_by(PriorityAssessment.created_at.desc()))
        stored = ((latest.factor_evidence or {}).get("community") or {}).get("other_reporters", 0) if latest else 0
        if stored == other_reporters(db, c):
            continue
        before = c.priority_level
        run_priority(db, c, assessed_by="system:community-reports")
        if c.priority_level != before:
            escalation.set_due_at(db, c)


# ---------------- routing ----------------
def _officer_facts(db: Session, unit: DepartmentUnit, chain: list[uuid.UUID], depths: dict) -> list[OfficerFact]:
    rows = db.execute(
        select(Officer, User.full_name)
        .join(User, User.id == Officer.user_id)
        .where(Officer.unit_id == unit.id, Officer.active.is_(True), User.role == Role.OFFICER,
               User.account_status == AccountStatus.ACTIVE)
    ).all()
    if not rows:
        return []
    ids = [o.id for o, _ in rows]
    workload = dict(db.execute(select(Assignment.officer_id, func.count()).where(
        Assignment.officer_id.in_(ids), Assignment.assignment_status == AssignmentStatus.ACTIVE).group_by(Assignment.officer_id)).all())
    areas: dict[uuid.UUID, list[uuid.UUID]] = {}
    for a in db.scalars(select(OfficerArea).where(OfficerArea.officer_id.in_(ids))):
        areas.setdefault(a.officer_id, []).append(a.jurisdiction_id)
    chain_set = set(chain)
    out = []
    for o, name in rows:
        mine = areas.get(o.id, [])
        if not mine:
            match = -1
        else:
            covering = [depths.get(j, 0) for j in mine if j in chain_set]
            match = max(covering) if covering else None
        out.append(OfficerFact(o.id, name, int(workload.get(o.id, 0)), match))
    return out


def gather_routing_input(db: Session, complaint: Complaint) -> RoutingInput:
    s = get_settings()
    rules = db.scalars(select(ResponsibilityRule).where(
        ResponsibilityRule.category == complaint.category, ResponsibilityRule.active.is_(True))).all()
    responsible = {r.department_id: r.department for r in rules}
    leaves_db = hierarchy.containing_leaf_jurisdictions(db, complaint.latitude, complaint.longitude)
    depths = hierarchy.depth_map(db) if leaves_db else {}
    leaves, officers = [], {}
    for leaf in leaves_db:
        chain = hierarchy.ancestor_ids(db, leaf.id)
        fact = LeafFact(leaf.id, leaf.name, hierarchy.jurisdiction_path(db, leaf.id) or leaf.name)
        for dept_id in responsible:
            unit = hierarchy.nearest_unit(db, dept_id, chain)
            if unit is None:
                fact.units[dept_id] = None
                continue
            fact.units[dept_id] = UnitFact(unit.id, dept_id, unit.jurisdiction_id, unit.jurisdiction.name, unit.active)
            if unit.active and unit.id not in officers:
                officers[unit.id] = _officer_facts(db, unit, chain, depths)
        leaves.append(fact)
    return RoutingInput(
        category=complaint.category.value,
        any_jurisdiction_configured=any_active_jurisdiction(db),
        location_uncertain=complaint.accuracy_meters is not None and complaint.accuracy_meters > s.ROUTING_MAX_LOCATION_ACCURACY_M,
        accuracy_meters=complaint.accuracy_meters,
        leaves=leaves,
        responsible=[DepartmentFact(d.id, d.name, d.active) for d in sorted(responsible.values(), key=lambda d: d.name)],
        officers=officers,
    )


def apply_routing(
    db: Session,
    complaint: Complaint,
    result: RoutingResult,
    actor_id: uuid.UUID | None,
    reviewed_by: uuid.UUID | None = None,
    auto_assign: bool = True,
) -> RoutingDecision:
    from app.services import escalation, workflow  # local import: workflow imports this module

    decision = RoutingDecision(
        complaint_id=complaint.id,
        department_id=result.department_id,
        department_unit_id=result.unit_id,
        jurisdiction_id=result.jurisdiction_id,
        officer_id=result.officer_id if auto_assign else None,
        routing_status=result.routing_status,
        reason_code=result.reason_code,
        rule_version=get_settings().ROUTING_RULE_VERSION,
        explanation=result.explanation + (f" {result.officer_reason}" if result.officer_reason and auto_assign else ""),
        candidates=result.candidates,
        reviewed_by=reviewed_by,
    )
    db.add(decision)
    db.flush()
    previous_unit = complaint.department_unit_id
    routed = result.routing_status == RoutingStatus.ROUTED
    complaint.routing_status = result.routing_status
    complaint.department_id = result.department_id if routed else None
    complaint.department_unit_id = result.unit_id if routed else None
    if result.jurisdiction_id:
        complaint.jurisdiction_id = result.jurisdiction_id
    audit.record(
        db,
        actor_id=actor_id,
        actor_label=None if actor_id else "system:routing-engine",
        action="ROUTING_DECISION",
        entity_type="complaint",
        entity_id=complaint.id,
        details={
            "routing_status": result.routing_status,
            "reason_code": result.reason_code,
            "department_id": result.department_id,
            "unit_id": result.unit_id,
            "jurisdiction_id": result.jurisdiction_id,
            "officer_id": result.officer_id if auto_assign else None,
            "rule_version": decision.rule_version,
            "reviewed_by": reviewed_by,
        },
    )
    if routed and complaint.department_unit_id != previous_unit:
        escalation.set_due_at(db, complaint)
        dept = db.get(Department, complaint.department_id)
        notify(
            db,
            recipient_id=complaint.citizen_id,
            complaint_id=complaint.id,
            notification_type="ROUTED",
            message=f"Your complaint {complaint.reference_id} was routed to {dept.name}.",
            event_key=f"routing:{decision.id}",
        )
        assigned = False
        if auto_assign and result.officer_id:
            assigned = workflow.auto_assign(db, complaint, result.officer_id, result.officer_reason)
        if not assigned:
            for uid in unit_staff_ids(db, complaint.department_unit_id, {Role.DEPARTMENT_ADMIN}):
                notify(
                    db,
                    recipient_id=uid,
                    complaint_id=complaint.id,
                    notification_type="AWAITING_ASSIGNMENT",
                    message=f"New complaint {complaint.reference_id} ({complaint.category.value}) is waiting for an officer to be assigned.",
                    event_key=f"routing:{decision.id}",
                )
    return decision


def run_routing(db: Session, complaint: Complaint, actor_id: uuid.UUID | None = None) -> RoutingResult:
    result = determine_routing(gather_routing_input(db, complaint))
    apply_routing(db, complaint, result, actor_id)
    return result


# ---------------- duplicates ----------------
def run_duplicate_detection(db: Session, complaint: Complaint) -> list[ComplaintRelationship]:
    s = get_settings()
    pt = cast(make_point(complaint.latitude, complaint.longitude), Geography)
    dist = ST_Distance(Complaint.location, pt)
    rows = db.execute(
        select(Complaint, dist)
        .where(Complaint.id != complaint.id)
        .where(ST_DWithin(Complaint.location, pt, s.DUPLICATE_RADIUS_M))
    ).all()
    hashes: dict = {}
    ids = [c.id for c, _ in rows] + [complaint.id]
    for cid, h in db.execute(select(Media.complaint_id, Media.perceptual_hash).where(
            Media.complaint_id.in_(ids), Media.perceptual_hash.is_not(None),
            Media.purpose == MediaPurpose.COMPLAINT)):
        hashes.setdefault(cid, []).append(h)
    candidates = [
        CandidateInput(str(c.id), c.category.value, c.created_at, float(d), c.citizen_confirmed_description,
                       hashes.get(c.id, []))
        for c, d in rows
    ]
    method, threshold, sim_fn = "lexical-token-cosine", s.DUPLICATE_LEXICAL_SIMILARITY, None
    base = ai_service.generate_text_embedding(complaint.citizen_confirmed_description) if candidates else None
    if base is not None and base.available:
        cache: dict[str, list[float] | None] = {}

        def sim_fn(_a: str, b: str) -> float:
            if b not in cache:
                r = ai_service.generate_text_embedding(b)
                cache[b] = r.embedding if r.available else None
            return cosine(base.embedding or [], cache[b] or [])

        method, threshold = f"embedding-cosine:{base.model}", s.DUPLICATE_TEXT_SIMILARITY

    kwargs = {"similarity_fn": sim_fn} if sim_fn else {}
    found = detect_duplicate_candidates(
        category=complaint.category.value,
        created_at=complaint.created_at,
        text=complaint.citizen_confirmed_description,
        candidates=candidates,
        radius_m=s.DUPLICATE_RADIUS_M,
        window_days=s.DUPLICATE_WINDOW_DAYS,
        text_threshold=threshold,
        text_method=method,
        image_hashes=hashes.get(complaint.id, []),
        image_max_distance=s.DUPLICATE_IMAGE_MAX_DISTANCE,
        **kwargs,
    )
    rels = []
    for cand in found:
        rel = ComplaintRelationship(
            source_complaint_id=complaint.id,
            related_complaint_id=uuid.UUID(cand.complaint_id),
            similarity_score=cand.similarity_score,
            distance_m=cand.distance_m,
            text_similarity=cand.text_similarity,
            text_similarity_method=cand.text_similarity_method,
            match_reasons=cand.match_reasons,
            relationship_status=RelationshipStatus.SUGGESTED,
        )
        db.add(rel)
        rels.append(rel)
    return rels


# ---------------- creation ----------------
def _request_hash(payload: ComplaintCreate) -> str:
    data = payload.model_dump(mode="json")
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def create_complaint(
    db: Session, actor: Actor, payload: ComplaintCreate, idempotency_key: str | None
) -> tuple[Complaint, bool, RoutingResult | None, int]:
    """Returns (complaint, created, routing_result, related_count)."""
    req_hash = _request_hash(payload)
    if idempotency_key:
        existing = db.scalar(
            select(Complaint).where(Complaint.citizen_id == actor.user_id, Complaint.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.request_hash != req_hash:
                raise err("DUPLICATE_SUBMISSION")
            return existing, False, None, 0

    if not payload.confirmed:
        raise err("VALIDATION_ERROR", message="Please review and confirm the complaint details before submitting.",
                  details={"field": "confirmed"})

    media = []
    if payload.media_ids:
        media = db.scalars(select(Media).where(Media.id.in_(payload.media_ids))).all()
        if len(media) != len(set(payload.media_ids)) or any(
            m.uploaded_by != actor.user_id or m.complaint_id is not None or m.purpose != MediaPurpose.COMPLAINT
            for m in media
        ):
            raise err("MEDIA_NOT_AVAILABLE", status_code=422,
                      message="One or more attached files are not available. Please upload them again.")
        check_media_counts([m.media_type for m in media])

    original = (payload.original_description or "").strip() or None
    if original and len(original) > DESCRIPTION_MAX:
        raise err("DESCRIPTION_TOO_LONG", details={"field": "original_description"})
    confirmed = validate_complaint_input(payload.description, bool(media))
    if confirmed is None:
        raise err("EMPTY_COMPLAINT", message="Please confirm a written description for the attached media before submitting.")
    loc = validate_location(payload.location)
    if payload.occurred_at and payload.occurred_at.replace(tzinfo=payload.occurred_at.tzinfo or timezone.utc) > datetime.now(timezone.utc):
        raise err("VALIDATION_ERROR", message="The occurrence date cannot be in the future.", details={"field": "occurred_at"})

    analysis = None
    if payload.analysis_id:
        analysis = db.get(AIAnalysis, payload.analysis_id)
        if analysis is None or analysis.requested_by != actor.user_id or analysis.complaint_id is not None:
            raise err("VALIDATION_ERROR", message="The referenced analysis is not available.", details={"field": "analysis_id"})

    now = datetime.now(timezone.utc)
    complaint = Complaint(
        reference_id=generate_complaint_reference(now),
        citizen_id=actor.user_id,
        title=payload.title.strip(),
        original_description=original if original is not None else (payload.description or "").strip() or None,
        citizen_confirmed_description=confirmed,
        category=payload.category,
        location=point_wkt(loc.latitude, loc.longitude),
        latitude=loc.latitude,
        longitude=loc.longitude,
        accuracy_meters=loc.accuracy_meters,
        location_source=loc.location_source,
        landmark=loc.landmark,
        address_text=loc.address_text,
        occurred_at=payload.occurred_at,
        additional_details=payload.additional_details,
        citizen_severity=payload.observed_severity,
        citizen_safety_risk=payload.safety_risk,
        citizen_exposure=payload.public_exposure,
        status=ComplaintStatus.SUBMITTED,
        routing_status=RoutingStatus.PENDING_REVIEW,  # replaced by the routing evaluation below
        allow_public_display=payload.allow_public_display,
        ai_analysis_id=analysis.id if analysis else None,
        ai_review_required=bool(analysis and analysis.review_required),
        idempotency_key=idempotency_key,
        request_hash=req_hash,
        created_at=now,
        updated_at=now,
    )
    for _ in range(5):
        if not db.scalar(select(Complaint.id).where(Complaint.reference_id == complaint.reference_id)):
            break
        complaint.reference_id = generate_complaint_reference(now)
    db.add(complaint)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if idempotency_key:  # concurrent retry with same key
            existing = db.scalar(
                select(Complaint).where(Complaint.citizen_id == actor.user_id, Complaint.idempotency_key == idempotency_key)
            )
            if existing and existing.request_hash == req_hash:
                return existing, False, None, 0
        raise err("DUPLICATE_SUBMISSION")

    for m in media:
        m.complaint_id = complaint.id
    if analysis:
        analysis.complaint_id = complaint.id

    hist = StatusHistory(
        complaint_id=complaint.id,
        previous_status=None,
        new_status=ComplaintStatus.SUBMITTED,
        actor_id=actor.user_id,
        actor_role=Role.CITIZEN,
        remarks="Complaint submitted by citizen.",
        created_at=now,
    )
    db.add(hist)
    db.flush()

    run_priority(db, complaint, assessed_by="system:priority-engine")
    routing = run_routing(db, complaint)
    related = run_duplicate_detection(db, complaint)
    if related:
        refresh_community_priority(db, [complaint.id] + [r.related_complaint_id for r in related])

    notify(
        db,
        recipient_id=actor.user_id,
        complaint_id=complaint.id,
        notification_type="SUBMITTED",
        message=f"Your complaint {complaint.reference_id} was submitted successfully.",
        event_key=f"status:{hist.id}",
    )
    audit.record(
        db,
        actor_id=actor.user_id,
        action="COMPLAINT_CREATED",
        entity_type="complaint",
        entity_id=complaint.id,
        details={"reference_id": complaint.reference_id, "media": [m.id for m in media], "analysis_id": complaint.ai_analysis_id},
    )
    db.commit()
    return complaint, True, routing, len(related)


def latest_routing_decision(db: Session, complaint_id: uuid.UUID) -> RoutingDecision | None:
    return db.scalar(
        select(RoutingDecision).where(RoutingDecision.complaint_id == complaint_id).order_by(RoutingDecision.decided_at.desc())
    )


def latest_priority(db: Session, complaint_id: uuid.UUID) -> PriorityAssessment | None:
    return db.scalar(
        select(PriorityAssessment)
        .where(PriorityAssessment.complaint_id == complaint_id)
        .order_by(PriorityAssessment.created_at.desc())
    )


def count_by_status(db: Session, base_filter) -> dict[str, int]:
    rows = db.execute(select(Complaint.status, func.count()).where(base_filter).group_by(Complaint.status)).all()
    return {s.value: n for s, n in rows}
