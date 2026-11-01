"""System administration (spec F14, 7.G). SYSTEM_ADMIN only."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.ai import ai_service
from app.core.db import get_db
from app.core.errors import err
from app.geospatial import InvalidGeometry, geojson_to_geometry, geometry_as_geojson, point_wkt
from app.models import (
    AIAnalysis,
    AuditLog,
    Complaint,
    ComplaintRelationship,
    Department,
    DepartmentUnit,
    Jurisdiction,
    Officer,
    PriorityConfig,
    ResponsibilityRule,
    SensitiveLocation,
    User,
    UserPermission,
)
from app.models.enums import AccountStatus, RelationshipStatus, Role, RoutingStatus
from app.priority.engine import DEFAULT_PRIORITY_CONFIG, PriorityConfigError, validate_priority_config
from app.routing.engine import RoutingResult
from app.schemas import PriorityConfigIn, RoutingOverride, SensitiveLocationIn
from app.security.deps import require_system_admin
from app.security.permissions import Actor
from app.routing.engine import choose_officer
from app.services import hierarchy
from app.services.complaints import _officer_facts, active_priority_config, apply_routing
from app.services.lifecycle import PERMITTED_TRANSITIONS, REASON_REQUIRED, WORKFLOW_ONLY
from app.services.storage import get_storage
from app.services.views import list_item

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_system_admin)])


# ---------------- sensitive locations ----------------
def sens_dict(db: Session, s: SensitiveLocation) -> dict:
    lat, lng = db.execute(select(func.ST_Y(func.ST_GeomFromWKB(func.ST_AsBinary(SensitiveLocation.point))),
                                 func.ST_X(func.ST_GeomFromWKB(func.ST_AsBinary(SensitiveLocation.point))))
                          .where(SensitiveLocation.id == s.id)).one()
    return {"id": s.id, "label": s.label, "location_type": s.location_type, "latitude": lat, "longitude": lng,
            "radius_m": s.radius_m, "sensitivity_score": s.sensitivity_score, "is_prototype": s.is_prototype,
            "source_reference": s.source_reference, "active": s.active}


@router.get("/sensitive-locations")
def list_sensitive(db: Session = Depends(get_db)):
    return [sens_dict(db, s) for s in db.scalars(select(SensitiveLocation).order_by(SensitiveLocation.label))]


@router.post("/sensitive-locations", status_code=201)
def create_sensitive(body: SensitiveLocationIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    s = SensitiveLocation(label=body.label, location_type=body.location_type, point=point_wkt(body.latitude, body.longitude),
                          radius_m=body.radius_m, sensitivity_score=body.sensitivity_score, is_prototype=body.is_prototype,
                          source_reference=body.source_reference)
    db.add(s)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="SENSITIVE_LOCATION_CREATED", entity_type="sensitive_location", entity_id=s.id,
                 details=body.model_dump())
    db.commit()
    return sens_dict(db, s)


class ActiveToggle(BaseModel):
    active: bool


@router.patch("/sensitive-locations/{loc_id}")
def toggle_sensitive(loc_id: uuid.UUID, body: ActiveToggle, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    s = db.get(SensitiveLocation, loc_id)
    if s is None:
        raise err("NOT_FOUND")
    s.active = body.active
    audit.record(db, actor_id=actor.user_id, action="SENSITIVE_LOCATION_UPDATED", entity_type="sensitive_location", entity_id=s.id,
                 details={"active": body.active})
    db.commit()
    return sens_dict(db, s)


# ---------------- priority configuration ----------------
@router.get("/priority-config")
def get_priority_config(db: Session = Depends(get_db)):
    version, cfg = active_priority_config(db)
    history = db.scalars(select(PriorityConfig).order_by(PriorityConfig.version.desc())).all()
    return {"active_version": version, "config": cfg, "default": DEFAULT_PRIORITY_CONFIG,
            "history": [{"version": h.version, "active": h.active, "created_by": h.created_by, "created_at": h.created_at} for h in history],
            "disclaimer": "Prototype configuration, not an official civic or government standard."}


@router.post("/priority-config", status_code=201)
def set_priority_config(body: PriorityConfigIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    try:
        merged = validate_priority_config(body.config)
    except (PriorityConfigError, KeyError, TypeError) as exc:
        raise err("VALIDATION_ERROR", message=f"Invalid priority configuration: {exc}")
    latest = db.scalar(select(func.max(PriorityConfig.version))) or 0
    for row in db.scalars(select(PriorityConfig).where(PriorityConfig.active.is_(True))):
        row.active = False
    row = PriorityConfig(version=latest + 1, config=merged, active=True, created_by=actor.user_id)
    db.add(row)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="PRIORITY_CONFIG_CHANGED", entity_type="priority_config", entity_id=row.id,
                 details={"version": row.version, "config": merged})
    db.commit()
    return {"version": row.version, "config": merged}


# ---------------- review queues ----------------
@router.get("/routing-queue")
def routing_queue(db: Session = Depends(get_db), status: RoutingStatus = RoutingStatus.PENDING_REVIEW):
    """PENDING_REVIEW = actionable queue. UNROUTED = monitoring view (no pending action implied)."""
    if status == RoutingStatus.ROUTED:
        raise err("VALIDATION_ERROR", message="Use PENDING_REVIEW or UNROUTED.")
    from app.services.complaints import latest_routing_decision
    rows = db.scalars(select(Complaint).where(Complaint.routing_status == status).order_by(Complaint.created_at)).all()
    out = []
    for c in rows:
        rd = latest_routing_decision(db, c.id)
        out.append({**list_item(db, c, True), "reason_code": rd.reason_code if rd else None,
                    "explanation": rd.explanation if rd else None, "candidates": rd.candidates if rd else {}})
    return out


@router.post("/complaints/{complaint_id}/routing")
def override_routing(complaint_id: uuid.UUID, body: RoutingOverride, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Administrative routing correction: an authorized human confirms the responsible department."""
    c = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if c is None:
        raise err("COMPLAINT_NOT_FOUND")
    d = db.get(Department, body.department_id)
    if d is None or not d.active:
        raise err("VALIDATION_ERROR", message="Choose an active configured department.", details={"field": "department_id"})
    chain = hierarchy.ancestor_ids(db, c.jurisdiction_id) if c.jurisdiction_id else []
    if body.unit_id:
        unit = db.get(DepartmentUnit, body.unit_id)
        if unit is None or unit.department_id != d.id:
            raise err("VALIDATION_ERROR", message="The unit does not belong to this department.", details={"field": "unit_id"})
    else:
        unit = hierarchy.nearest_unit(db, d.id, chain)
        if unit is None:
            units = db.scalars(select(DepartmentUnit).where(DepartmentUnit.department_id == d.id,
                                                            DepartmentUnit.active.is_(True))).all()
            unit = units[0] if len(units) == 1 else None
        if unit is None:
            raise err("VALIDATION_ERROR", message="Choose the department unit (jurisdiction) that should handle this complaint.",
                      details={"field": "unit_id"})
    if not unit.active:
        raise err("VALIDATION_ERROR", message="This department unit is deactivated.", details={"field": "unit_id"})
    officer, officer_reason = choose_officer(_officer_facts(db, unit, chain, hierarchy.depth_map(db)))
    result = RoutingResult(RoutingStatus.ROUTED, "ADMIN_CONFIRMED",
                           f"'{d.name}' ({unit.jurisdiction.name}) confirmed by a system administrator. "
                           f"Reason: {body.reason.strip()}",
                           department_id=d.id, unit_id=unit.id, jurisdiction_id=c.jurisdiction_id,
                           officer_id=officer.id if officer else None, officer_reason=officer_reason)
    apply_routing(db, c, result, actor.user_id, reviewed_by=actor.user_id)
    c.version += 1
    db.commit()
    return list_item(db, c, True)


@router.get("/ai-review-queue")
def ai_review_queue(db: Session = Depends(get_db)):
    flagged = db.scalars(select(Complaint).where(Complaint.ai_review_required.is_(True)).order_by(Complaint.created_at.desc()).limit(200)).all()
    failures = db.scalars(select(AuditLog).where(AuditLog.action == "AI_ANALYSIS_FAILED").order_by(AuditLog.created_at.desc()).limit(50)).all()
    prompt = db.scalars(select(Complaint).where(Complaint.needs_prompt_review.is_(True)).order_by(Complaint.created_at.desc()).limit(200)).all()
    return {
        "low_confidence_or_flagged": [
            {**list_item(db, c, True), "analysis": (lambda a: {"analysis_id": a.id, "confidence_band": a.confidence_band,
                                                                "review_reasons": a.structured_output.get("review_reasons", []),
                                                                "reviewed": a.reviewed_by is not None})(db.get(AIAnalysis, c.ai_analysis_id))
             if c.ai_analysis_id else None}
            for c in flagged
        ],
        "prompt_safety_reviews": [list_item(db, c, True) for c in prompt],
        "recent_ai_failures": [{"code": f.details.get("code"), "created_at": f.created_at} for f in failures],
    }


@router.post("/ai-review/{complaint_id}/ack")
def ack_ai_review(complaint_id: uuid.UUID, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    c = db.get(Complaint, complaint_id)
    if c is None:
        raise err("COMPLAINT_NOT_FOUND")
    c.ai_review_required = False
    if c.ai_analysis_id:
        db.get(AIAnalysis, c.ai_analysis_id).reviewed_by = actor.user_id
    audit.record(db, actor_id=actor.user_id, action="AI_REVIEW_ACKNOWLEDGED", entity_type="complaint", entity_id=c.id)
    db.commit()
    return {"ok": True}


@router.get("/relationships")
def relationships(db: Session = Depends(get_db), status: RelationshipStatus = RelationshipStatus.SUGGESTED):
    rows = db.scalars(select(ComplaintRelationship).where(ComplaintRelationship.relationship_status == status)
                      .order_by(ComplaintRelationship.created_at.desc()).limit(200)).all()
    out = []
    for r in rows:
        a, b = db.get(Complaint, r.source_complaint_id), db.get(Complaint, r.related_complaint_id)
        out.append({"relationship_id": r.id, "source": {"complaint_id": a.id, "reference_id": a.reference_id, "title": a.title},
                    "related": {"complaint_id": b.id, "reference_id": b.reference_id, "title": b.title},
                    "similarity_score": r.similarity_score, "distance_m": r.distance_m, "text_similarity": r.text_similarity,
                    "text_similarity_method": r.text_similarity_method, "match_reasons": r.match_reasons,
                    "relationship_status": r.relationship_status, "created_at": r.created_at})
    return out


class MisuseFlag(BaseModel):
    flagged: bool
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/complaints/{complaint_id}/misuse")
def flag_misuse(complaint_id: uuid.UUID, body: MisuseFlag, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Hide reported spam/inappropriate content from public views. The record itself is preserved."""
    c = db.get(Complaint, complaint_id)
    if c is None:
        raise err("COMPLAINT_NOT_FOUND")
    c.flagged_misuse = body.flagged
    audit.record(db, actor_id=actor.user_id, action="MISUSE_FLAG", entity_type="complaint", entity_id=c.id, details=body.model_dump())
    db.commit()
    return {"flagged_misuse": c.flagged_misuse}


@router.get("/lifecycle")
def lifecycle_rules():
    """Permitted transitions are enforced in code (read-only here) so they cannot be weakened at runtime."""
    return {"transitions": {k.value: sorted(v.value for v in vs) for k, vs in PERMITTED_TRANSITIONS.items()},
            "reason_required": sorted(s.value for s in REASON_REQUIRED) + ["REASSIGNMENT"],
            "workflow_only": {k.value: v for k, v in WORKFLOW_ONLY.items()}}


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db), action: str | None = Query(default=None, max_length=80),
               entity_id: str | None = Query(default=None, max_length=64), entity_type: str | None = Query(default=None, max_length=40),
               date_from: datetime | None = None, date_to: datetime | None = None,
               limit: int = Query(default=100, le=500), offset: int = 0):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()
    names = _audit_names(db, rows)
    return {"total": total, "items": [{"id": r.id, "actor_id": r.actor_id, "actor_label": r.actor_label,
                                        "actor_name": names.get(("user", str(r.actor_id))) if r.actor_id else None,
                                        "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
                                        "entity_name": names.get((r.entity_type, str(r.entity_id))) if r.entity_id else None,
                                        "details": r.details, "request_id": r.request_id, "created_at": r.created_at}
                                       for r in rows]}


def _audit_names(db: Session, rows) -> dict[tuple[str, str], str]:
    """Readable names for audit actors and entities, looked up in one query per entity type."""
    wanted: dict[str, set[uuid.UUID]] = {}

    def want(kind: str, value) -> None:
        try:
            wanted.setdefault(kind, set()).add(uuid.UUID(str(value)))
        except (ValueError, TypeError):
            pass

    for r in rows:
        if r.actor_id:
            want("user", r.actor_id)
        if r.entity_id and r.entity_type:
            want(r.entity_type, r.entity_id)
    out: dict[tuple[str, str], str] = {}
    simple = {"user": (User, lambda u: f"{u.full_name} ({u.role.value.replace('_', ' ').title()})"),
              "department": (Department, lambda d: d.name),
              "jurisdiction": (Jurisdiction, lambda j: j.name),
              "sensitive_location": (SensitiveLocation, lambda x: x.label),
              "complaint": (Complaint, lambda c: f"{c.reference_id} · {c.title}")}
    for kind, (model, fmt) in simple.items():
        if wanted.get(kind):
            for obj in db.scalars(select(model).where(model.id.in_(wanted[kind]))):
                out[(kind, str(obj.id))] = fmt(obj)
    if wanted.get("responsibility_rule"):
        for rule, dept in db.execute(select(ResponsibilityRule, Department.name)
                                     .join(Department, Department.id == ResponsibilityRule.department_id)
                                     .where(ResponsibilityRule.id.in_(wanted["responsibility_rule"]))):
            out[("responsibility_rule", str(rule.id))] = f"{rule.category.value.replace('_', ' ').title()} → {dept}"
    return out


@router.get("/system")
def system(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        postgis = db.scalar(text("SELECT postgis_version()"))
        db_ok = True
    except Exception:
        db_ok, postgis = False, None
    storage = get_storage()
    counts = {
        "users": db.scalar(select(func.count()).select_from(User)),
        "complaints": db.scalar(select(func.count()).select_from(Complaint)),
        "departments": db.scalar(select(func.count()).select_from(Department)),
        "jurisdictions": db.scalar(select(func.count()).select_from(Jurisdiction)),
        "routing_pending_review": db.scalar(select(func.count()).select_from(Complaint).where(Complaint.routing_status == RoutingStatus.PENDING_REVIEW)),
        "unrouted": db.scalar(select(func.count()).select_from(Complaint).where(Complaint.routing_status == RoutingStatus.UNROUTED)),
    }
    return {"database": {"ok": db_ok, "postgis": postgis}, "storage": {"kind": storage.kind, "ok": storage.healthy()},
            "ai": ai_service.ai_status().model_dump(), "counts": counts, "checked_at": datetime.now(timezone.utc)}
