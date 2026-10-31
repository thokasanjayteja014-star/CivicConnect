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
from app.schemas import (
    DepartmentIn,
    DepartmentPatch,
    JurisdictionIn,
    PriorityConfigIn,
    ResponsibilityIn,
    RoutingOverride,
    SensitiveLocationIn,
    StaffCreate,
    UserPatch,
)
from app.security import hash_password
from app.security.deps import require_system_admin
from app.security.permissions import Actor
from app.services.complaints import active_priority_config, apply_routing
from app.services.lifecycle import PERMITTED_TRANSITIONS, REASON_REQUIRED, WORKFLOW_ONLY
from app.services.storage import get_storage
from app.services.views import list_item

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_system_admin)])


def dept_dict(d: Department) -> dict:
    return {"id": d.id, "name": d.name, "description": d.description, "active": d.active, "is_prototype": d.is_prototype,
            "source_reference": d.source_reference, "supported_categories": [c.value for c in d.supported_categories],
            "jurisdiction_ids": [j.id for j in d.jurisdictions], "created_at": d.created_at}


# ---------------- departments ----------------
@router.get("/departments")
def list_departments(db: Session = Depends(get_db)):
    return [dept_dict(d) for d in db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    d = Department(**body.model_dump())
    db.add(d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise err("CONFLICT", message="A department with this name already exists.")
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_CREATED", entity_type="department", entity_id=d.id, details=body.model_dump())
    db.commit()
    return dept_dict(d)


@router.patch("/departments/{department_id}")
def update_department(department_id: uuid.UUID, body: DepartmentPatch, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    d = db.get(Department, department_id)
    if d is None:
        raise err("NOT_FOUND")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(d, k) for k in changes}
    for k, v in changes.items():
        setattr(d, k, v)
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_UPDATED", entity_type="department", entity_id=d.id,
                 details={"before": before, "after": changes})
    db.commit()
    return dept_dict(d)


# ---------------- jurisdictions ----------------
def juris_dict(db: Session, j: Jurisdiction) -> dict:
    return {"id": j.id, "name": j.name, "active": j.active, "is_prototype": j.is_prototype, "source_reference": j.source_reference,
            "last_verified_at": j.last_verified_at, "department_ids": [d.id for d in j.departments],
            "departments": [{"id": d.id, "name": d.name} for d in j.departments],
            "boundary": geometry_as_geojson(db, j.id), "created_at": j.created_at}


@router.get("/jurisdictions")
def list_jurisdictions(db: Session = Depends(get_db)):
    return [juris_dict(db, j) for j in db.scalars(select(Jurisdiction).order_by(Jurisdiction.name))]


@router.post("/jurisdictions")
def upsert_jurisdiction(body: JurisdictionIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    try:
        geom = geojson_to_geometry(db, body.boundary)
    except InvalidGeometry as exc:
        raise err("VALIDATION_ERROR", message=str(exc), details={"field": "boundary"})
    depts = db.scalars(select(Department).where(Department.id.in_(body.department_ids))).all() if body.department_ids else []
    if len(depts) != len(set(body.department_ids)):
        raise err("VALIDATION_ERROR", message="Unknown department in department_ids.", details={"field": "department_ids"})
    if body.id:
        j = db.get(Jurisdiction, body.id)
        if j is None:
            raise err("NOT_FOUND")
        action = "JURISDICTION_UPDATED"
    else:
        j = Jurisdiction()
        db.add(j)
        action = "JURISDICTION_CREATED"
    j.name, j.boundary, j.active, j.is_prototype = body.name, geom, body.active, body.is_prototype
    j.source_reference, j.last_verified_at = body.source_reference, body.last_verified_at
    j.departments = list(depts)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action=action, entity_type="jurisdiction", entity_id=j.id,
                 details={**body.model_dump(exclude={"boundary"}), "boundary_type": body.boundary.get("type")})
    db.commit()
    return juris_dict(db, j)


# ---------------- responsibility rules ----------------
def rule_dict(r: ResponsibilityRule) -> dict:
    return {"id": r.id, "department_id": r.department_id, "department_name": r.department.name, "category": r.category,
            "active": r.active, "verified": r.verified, "source_reference": r.source_reference,
            "verified_at": r.verified_at, "verified_by": r.verified_by}


@router.get("/responsibilities")
def list_rules(db: Session = Depends(get_db)):
    return [rule_dict(r) for r in db.scalars(select(ResponsibilityRule).order_by(ResponsibilityRule.category))]


@router.post("/responsibilities")
def upsert_rule(body: ResponsibilityIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    if db.get(Department, body.department_id) is None:
        raise err("VALIDATION_ERROR", message="Unknown department.", details={"field": "department_id"})
    r = db.scalar(select(ResponsibilityRule).where(ResponsibilityRule.department_id == body.department_id,
                                                   ResponsibilityRule.category == body.category))
    before = rule_dict(r) if r else None
    if r is None:
        r = ResponsibilityRule(department_id=body.department_id, category=body.category)
        db.add(r)
    r.active, r.source_reference = body.active, body.source_reference
    if body.verified and not r.verified:
        r.verified_by, r.verified_at = actor.user_id, datetime.now(timezone.utc)
    r.verified = body.verified
    db.flush()
    db.refresh(r)
    audit.record(db, actor_id=actor.user_id, action="RESPONSIBILITY_RULE_SAVED", entity_type="responsibility_rule", entity_id=r.id,
                 details={"before": before, "after": body.model_dump()})
    db.commit()
    return rule_dict(r)


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


# ---------------- users / officers ----------------
def user_dict(db: Session, u: User) -> dict:
    o = db.scalar(select(Officer).where(Officer.user_id == u.id))
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone, "role": u.role,
            "account_status": u.account_status, "created_at": u.created_at,
            "officer": ({"officer_id": o.id, "department_id": o.department_id, "department_name": o.department.name,
                         "designation": o.designation, "active": o.active} if o else None),
            "permissions": [p.permission for p in u.permissions]}


@router.get("/users")
def list_users(db: Session = Depends(get_db), role: Role | None = None, q: str | None = Query(default=None, max_length=100),
               limit: int = Query(default=100, le=500), offset: int = 0):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.full_name.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    return {"total": total, "items": [user_dict(db, u) for u in db.scalars(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))]}


@router.post("/users", status_code=201)
def create_user(body: StaffCreate, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise err("EMAIL_IN_USE")
    if body.role in (Role.OFFICER, Role.DEPARTMENT_ADMIN):
        if not body.department_id or db.get(Department, body.department_id) is None:
            raise err("VALIDATION_ERROR", message="Department users need a valid department.", details={"field": "department_id"})
    u = User(full_name=body.full_name, email=body.email.lower(), phone=body.phone, password_hash=hash_password(body.password),
             role=body.role, account_status=AccountStatus.ACTIVE)
    db.add(u)
    db.flush()
    if body.role in (Role.OFFICER, Role.DEPARTMENT_ADMIN):
        db.add(Officer(user_id=u.id, department_id=body.department_id,
                       designation=body.designation or ("Department administrator" if body.role == Role.DEPARTMENT_ADMIN else "Officer")))
    audit.record(db, actor_id=actor.user_id, action="USER_CREATED", entity_type="user", entity_id=u.id,
                 details={"role": body.role, "department_id": body.department_id})
    db.commit()
    db.refresh(u)
    return user_dict(db, u)


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserPatch, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise err("NOT_FOUND")
    if u.id == actor.user_id and (body.role not in (None, Role.SYSTEM_ADMIN) or body.account_status not in (None, AccountStatus.ACTIVE)):
        raise err("CONFLICT", message="You cannot remove your own administrator access.")
    before = user_dict(db, u)
    if body.full_name is not None:
        u.full_name = body.full_name
    if body.role is not None:
        u.role = body.role
    if body.account_status is not None:
        u.account_status = body.account_status
    officer = db.scalar(select(Officer).where(Officer.user_id == u.id))
    if u.role in (Role.OFFICER, Role.DEPARTMENT_ADMIN):
        dept_id = body.department_id or (officer.department_id if officer else None)
        if dept_id is None or db.get(Department, dept_id) is None:
            raise err("VALIDATION_ERROR", message="Department users need a valid department.", details={"field": "department_id"})
        if officer is None:
            officer = Officer(user_id=u.id, department_id=dept_id, designation=body.designation or "Officer")
            db.add(officer)
        officer.department_id = dept_id
        if body.designation:
            officer.designation = body.designation
        if body.officer_active is not None:
            officer.active = body.officer_active
    elif officer is not None:
        officer.active = False
    for p in body.grant_permissions:
        if not any(x.permission == p for x in u.permissions):
            db.add(UserPermission(user_id=u.id, permission=p, granted_by=actor.user_id))
    for p in body.revoke_permissions:
        for x in list(u.permissions):
            if x.permission == p:
                db.delete(x)
    db.flush()
    db.refresh(u)
    after = user_dict(db, u)
    audit.record(db, actor_id=actor.user_id, action="USER_UPDATED", entity_type="user", entity_id=u.id,
                 details={"before": before, "after": after})
    db.commit()
    return after


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
    result = RoutingResult(RoutingStatus.ROUTED, "ADMIN_CONFIRMED",
                           f"Department '{d.name}' confirmed by a system administrator. Reason: {body.reason.strip()}",
                           department_id=d.id, jurisdiction_id=c.jurisdiction_id)
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
               entity_id: str | None = Query(default=None, max_length=64), limit: int = Query(default=100, le=500), offset: int = 0):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [{"id": r.id, "actor_id": r.actor_id, "actor_label": r.actor_label, "action": r.action,
                                        "entity_type": r.entity_type, "entity_id": r.entity_id, "details": r.details,
                                        "request_id": r.request_id, "created_at": r.created_at} for r in rows]}


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
