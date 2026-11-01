"""Main Administrator configuration: jurisdiction hierarchy, department registry,
department-jurisdiction mapping (units), responsibilities, personnel, escalation policy
and source references. Only SYSTEM_ADMIN can reach these endpoints.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit
from app.core.db import get_db
from app.core.errors import err
from app.geospatial import InvalidGeometry, geojson_to_geometry, geometry_as_geojson
from app.models import (
    Assignment,
    AuditLog,
    Complaint,
    Department,
    DepartmentUnit,
    EscalationPolicy,
    Jurisdiction,
    Officer,
    OfficerArea,
    PublicIssue,
    ResponsibilityRule,
    RoutingDecision,
    User,
    UserPermission,
)
from app.models.enums import AccountStatus, Role
from app.schemas import (
    DepartmentIn,
    DepartmentPatch,
    JurisdictionIn,
    JurisdictionPatch,
    ResponsibilityIn,
    StaffCreate,
    UnitIn,
    UnitPatch,
    UserPatch,
)
from app.security import hash_password
from app.security.deps import require_system_admin
from app.security.permissions import Actor
from app.services import escalation as esc_service
from app.services.hierarchy import (
    JURISDICTION_TYPES,
    apply_status,
    depth_map,
    descendant_ids,
    jurisdiction_path,
    would_create_cycle,
)

router = APIRouter(prefix="/api/admin", tags=["admin-config"], dependencies=[Depends(require_system_admin)])


def _count(db: Session, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


# ---------------- departments (central registry) ----------------
def dept_dict(db: Session, d: Department) -> dict:
    units = db.scalars(select(DepartmentUnit).where(DepartmentUnit.department_id == d.id)).all()
    return {"id": d.id, "name": d.name, "description": d.description, "category": d.category, "active": d.active,
            "verification_status": d.verification_status, "is_prototype": d.is_prototype,
            "source_reference": d.source_reference, "supported_categories": [c.value for c in d.supported_categories],
            "jurisdiction_ids": [u.jurisdiction_id for u in units],
            "units": [{"id": u.id, "jurisdiction_id": u.jurisdiction_id, "jurisdiction_name": u.jurisdiction.name,
                       "active": u.active} for u in units],
            "personnel_count": db.scalar(select(func.count()).select_from(Officer).where(Officer.department_id == d.id)) or 0,
            "created_at": d.created_at}


@router.get("/departments")
def list_departments(db: Session = Depends(get_db)):
    return [dept_dict(db, d) for d in db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    d = Department(name=body.name.strip(), description=body.description, category=body.category, active=body.active,
                   source_reference=(body.source_reference or "").strip() or None, is_prototype=body.is_prototype)
    apply_status(d)
    db.add(d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise err("CONFLICT", message="A department with this name already exists in the registry.")
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_CREATED", entity_type="department", entity_id=d.id,
                 details={**body.model_dump(), "verification_status": d.verification_status})
    db.commit()
    return dept_dict(db, d)


@router.patch("/departments/{department_id}")
def update_department(department_id: uuid.UUID, body: DepartmentPatch, actor: Actor = Depends(require_system_admin),
                      db: Session = Depends(get_db)):
    d = db.get(Department, department_id)
    if d is None:
        raise err("NOT_FOUND")
    changes = body.model_dump(exclude_unset=True)
    if "source_reference" in changes:
        changes["source_reference"] = (changes["source_reference"] or "").strip() or None
    before = {k: getattr(d, k) for k in changes} | {"verification_status": d.verification_status}
    for k, v in changes.items():
        setattr(d, k, v)
    apply_status(d, changes)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise err("CONFLICT", message="A department with this name already exists in the registry.")
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_UPDATED", entity_type="department", entity_id=d.id,
                 details={"before": before, "after": changes | {"verification_status": d.verification_status}})
    db.commit()
    return dept_dict(db, d)


def department_dependencies(db: Session, d: Department) -> dict:
    """What depends on a department. Operational history blocks deletion; pure configuration
    (responsibilities, empty mappings, escalation overrides) is removed together with it."""
    unit_ids = list(db.scalars(select(DepartmentUnit.id).where(DepartmentUnit.department_id == d.id)))
    blocking = [
        ("Department personnel (administrators and officers)", _count(db, select(Officer.id).where(Officer.department_id == d.id))),
        ("Complaints handled by this department", _count(db, select(Complaint.id).where(
            or_(Complaint.department_id == d.id, Complaint.department_unit_id.in_(unit_ids) if unit_ids else False)))),
        ("Complaint assignments", _count(db, select(Assignment.id).where(Assignment.department_id == d.id))),
        ("Routing decisions", _count(db, select(RoutingDecision.id).where(RoutingDecision.department_id == d.id))),
        ("Public issues", _count(db, select(PublicIssue.id).where(PublicIssue.department_id == d.id))),
    ]
    removable = [
        ("Department-jurisdiction mappings", len(unit_ids)),
        ("Responsibilities", _count(db, select(ResponsibilityRule.id).where(ResponsibilityRule.department_id == d.id))),
        ("Escalation policy overrides", _count(db, select(EscalationPolicy.id).where(EscalationPolicy.department_id == d.id))),
    ]
    audit_count = _count(db, select(AuditLog.id).where(AuditLog.entity_type == "department", AuditLog.entity_id == str(d.id)))
    return _deps_payload(d.name, blocking, removable, audit_count)


def _deps_payload(name: str, blocking, removable, audit_count: int) -> dict:
    b = [{"label": label, "count": n} for label, n in blocking if n]
    return {"name": name, "can_delete": not b, "blocking": b,
            "removed_with_it": [{"label": label, "count": n} for label, n in removable if n],
            "audit_entries_preserved": audit_count,
            "recommendation": None if not b else "Deactivate instead. Historical complaints, assignments and audit records are preserved."}


@router.get("/departments/{department_id}/dependencies")
def department_deps(department_id: uuid.UUID, db: Session = Depends(get_db)):
    d = db.get(Department, department_id)
    if d is None:
        raise err("NOT_FOUND")
    return department_dependencies(db, d)


@router.delete("/departments/{department_id}")
def delete_department(department_id: uuid.UUID, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    d = db.scalar(select(Department).where(Department.id == department_id).with_for_update())
    if d is None:
        raise err("NOT_FOUND")
    deps = department_dependencies(db, d)
    if not deps["can_delete"]:
        raise err("DELETE_BLOCKED", details=deps)
    for rule in db.scalars(select(ResponsibilityRule).where(ResponsibilityRule.department_id == d.id)):
        db.delete(rule)
    for unit in db.scalars(select(DepartmentUnit).where(DepartmentUnit.department_id == d.id)):
        db.delete(unit)
    for pol in db.scalars(select(EscalationPolicy).where(EscalationPolicy.department_id == d.id)):
        db.delete(pol)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_DELETED", entity_type="department", entity_id=d.id,
                 details={"name": d.name, "removed_with_it": deps["removed_with_it"]})
    db.delete(d)
    db.commit()
    return {"deleted": True, "id": department_id}


# ---------------- jurisdictions (hierarchy) ----------------
def juris_dict(db: Session, j: Jurisdiction, depths: dict | None = None, with_boundary: bool = True) -> dict:
    units = db.scalars(select(DepartmentUnit).where(DepartmentUnit.jurisdiction_id == j.id)).all()
    return {"id": j.id, "name": j.name, "jurisdiction_type": j.jurisdiction_type, "parent_id": j.parent_id,
            "description": j.description, "active": j.active, "verification_status": j.verification_status,
            "is_prototype": j.is_prototype, "source_reference": j.source_reference, "last_verified_at": j.last_verified_at,
            "depth": (depths or {}).get(j.id, 0), "path": jurisdiction_path(db, j.id),
            "department_ids": [u.department_id for u in units],
            "departments": [{"id": u.department_id, "name": u.department.name, "unit_id": u.id, "active": u.active} for u in units],
            "has_boundary": j.boundary is not None,
            "boundary": geometry_as_geojson(db, j.id) if with_boundary and j.boundary is not None else None,
            "created_at": j.created_at}


@router.get("/jurisdictions")
def list_jurisdictions(db: Session = Depends(get_db), boundaries: bool = True):
    depths = depth_map(db)
    rows = db.scalars(select(Jurisdiction)).all()
    # Tree order: parents before children, siblings by name.
    by_parent: dict = {}
    for j in rows:
        by_parent.setdefault(j.parent_id, []).append(j)
    out, seen = [], set()

    def walk(pid):
        for j in sorted(by_parent.get(pid, []), key=lambda x: x.name.lower()):
            if j.id in seen:
                continue
            seen.add(j.id)
            out.append(juris_dict(db, j, depths, boundaries))
            walk(j.id)
    walk(None)
    out += [juris_dict(db, j, depths, boundaries) for j in rows if j.id not in seen]
    return out


@router.get("/jurisdiction-types")
def jurisdiction_types():
    return JURISDICTION_TYPES


def _geometry(db: Session, boundary: dict | None):
    if boundary is None:
        return None
    try:
        return geojson_to_geometry(db, boundary)
    except InvalidGeometry as exc:
        raise err("VALIDATION_ERROR", message=str(exc), details={"field": "boundary"})


@router.post("/jurisdictions", status_code=201)
def create_jurisdiction(body: JurisdictionIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    if body.parent_id and db.get(Jurisdiction, body.parent_id) is None:
        raise err("VALIDATION_ERROR", message="Unknown parent jurisdiction.", details={"field": "parent_id"})
    depts = db.scalars(select(Department).where(Department.id.in_(body.department_ids))).all() if body.department_ids else []
    if len(depts) != len(set(body.department_ids)):
        raise err("VALIDATION_ERROR", message="Unknown department in department_ids.", details={"field": "department_ids"})
    j = Jurisdiction(name=body.name.strip(), jurisdiction_type=body.jurisdiction_type.strip().upper(), parent_id=body.parent_id,
                     description=body.description, boundary=_geometry(db, body.boundary), active=body.active,
                     source_reference=(body.source_reference or "").strip() or None, is_prototype=body.is_prototype)
    apply_status(j)
    db.add(j)
    db.flush()
    for d in depts:
        db.add(DepartmentUnit(department_id=d.id, jurisdiction_id=j.id))
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="JURISDICTION_CREATED", entity_type="jurisdiction", entity_id=j.id,
                 details={**body.model_dump(exclude={"boundary"}), "has_boundary": body.boundary is not None,
                          "verification_status": j.verification_status})
    db.commit()
    return juris_dict(db, j, depth_map(db))


@router.patch("/jurisdictions/{jurisdiction_id}")
def update_jurisdiction(jurisdiction_id: uuid.UUID, body: JurisdictionPatch, actor: Actor = Depends(require_system_admin),
                        db: Session = Depends(get_db)):
    j = db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise err("NOT_FOUND")
    changes = body.model_dump(exclude_unset=True)
    if "parent_id" in changes:
        pid = changes["parent_id"]
        if pid and db.get(Jurisdiction, pid) is None:
            raise err("VALIDATION_ERROR", message="Unknown parent jurisdiction.", details={"field": "parent_id"})
        if pid == j.id or would_create_cycle(db, j.id, pid):
            raise err("VALIDATION_ERROR", message="A jurisdiction cannot be placed under itself or its own sub-area.",
                      details={"field": "parent_id"})
    if "boundary" in changes:
        changes["boundary_changed"] = True
        j.boundary = _geometry(db, changes.pop("boundary"))
    if "source_reference" in changes:
        changes["source_reference"] = (changes["source_reference"] or "").strip() or None
    if "jurisdiction_type" in changes and changes["jurisdiction_type"]:
        changes["jurisdiction_type"] = changes["jurisdiction_type"].strip().upper()
    for k, v in changes.items():
        if k != "boundary_changed":
            setattr(j, k, v)
    apply_status(j, changes)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="JURISDICTION_UPDATED", entity_type="jurisdiction", entity_id=j.id,
                 details={"changes": {k: v for k, v in changes.items()}, "verification_status": j.verification_status})
    db.commit()
    return juris_dict(db, j, depth_map(db))


def jurisdiction_dependencies(db: Session, j: Jurisdiction) -> dict:
    units = db.scalars(select(DepartmentUnit).where(DepartmentUnit.jurisdiction_id == j.id)).all()
    unit_ids = [u.id for u in units]
    staffed = _count(db, select(Officer.id).where(Officer.unit_id.in_(unit_ids))) if unit_ids else 0
    unit_complaints = _count(db, select(Complaint.id).where(Complaint.department_unit_id.in_(unit_ids))) if unit_ids else 0
    blocking = [
        ("Sub-jurisdictions", _count(db, select(Jurisdiction.id).where(Jurisdiction.parent_id == j.id))),
        ("Complaints located here", _count(db, select(Complaint.id).where(Complaint.jurisdiction_id == j.id))),
        ("Complaints handled by department units here", unit_complaints),
        ("Personnel assigned to department units here", staffed),
        ("Officer operational areas", _count(db, select(OfficerArea.id).where(OfficerArea.jurisdiction_id == j.id))),
        ("Routing decisions", _count(db, select(RoutingDecision.id).where(RoutingDecision.jurisdiction_id == j.id))),
        ("Public issues", _count(db, select(PublicIssue.id).where(PublicIssue.jurisdiction_id == j.id))),
    ]
    removable = [("Department-jurisdiction mappings", len(units))]
    audit_count = _count(db, select(AuditLog.id).where(AuditLog.entity_type == "jurisdiction", AuditLog.entity_id == str(j.id)))
    return _deps_payload(j.name, blocking, removable, audit_count)


@router.get("/jurisdictions/{jurisdiction_id}/dependencies")
def jurisdiction_deps(jurisdiction_id: uuid.UUID, db: Session = Depends(get_db)):
    j = db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise err("NOT_FOUND")
    return jurisdiction_dependencies(db, j)


@router.delete("/jurisdictions/{jurisdiction_id}")
def delete_jurisdiction(jurisdiction_id: uuid.UUID, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    j = db.scalar(select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id).with_for_update())
    if j is None:
        raise err("NOT_FOUND")
    deps = jurisdiction_dependencies(db, j)
    if not deps["can_delete"]:
        raise err("DELETE_BLOCKED", details=deps)
    for unit in db.scalars(select(DepartmentUnit).where(DepartmentUnit.jurisdiction_id == j.id)):
        db.delete(unit)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="JURISDICTION_DELETED", entity_type="jurisdiction", entity_id=j.id,
                 details={"name": j.name, "removed_with_it": deps["removed_with_it"]})
    db.delete(j)
    db.commit()
    return {"deleted": True, "id": jurisdiction_id}


# ---------------- department-jurisdiction mapping (units) ----------------
def unit_dict(db: Session, u: DepartmentUnit) -> dict:
    staff = db.execute(select(User.role, func.count()).join(Officer, Officer.user_id == User.id)
                       .where(Officer.unit_id == u.id, Officer.active.is_(True)).group_by(User.role)).all()
    counts = {r.value: n for r, n in staff}
    return {"id": u.id, "department_id": u.department_id, "department_name": u.department.name,
            "department_active": u.department.active, "jurisdiction_id": u.jurisdiction_id,
            "jurisdiction_name": u.jurisdiction.name, "jurisdiction_type": u.jurisdiction.jurisdiction_type,
            "jurisdiction_path": jurisdiction_path(db, u.jurisdiction_id), "active": u.active,
            "administrators": counts.get("DEPARTMENT_ADMIN", 0), "officers": counts.get("OFFICER", 0),
            "label": f"{u.department.name} — {u.jurisdiction.name}", "created_at": u.created_at}


@router.get("/units")
def list_units(db: Session = Depends(get_db), department_id: uuid.UUID | None = None, jurisdiction_id: uuid.UUID | None = None):
    stmt = select(DepartmentUnit).join(Department).join(Jurisdiction)
    if department_id:
        stmt = stmt.where(DepartmentUnit.department_id == department_id)
    if jurisdiction_id:
        stmt = stmt.where(DepartmentUnit.jurisdiction_id == jurisdiction_id)
    return [unit_dict(db, u) for u in db.scalars(stmt.order_by(Department.name, Jurisdiction.name))]


@router.post("/units", status_code=201)
def create_unit(body: UnitIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    if db.get(Department, body.department_id) is None or db.get(Jurisdiction, body.jurisdiction_id) is None:
        raise err("VALIDATION_ERROR", message="Unknown department or jurisdiction.")
    if db.scalar(select(DepartmentUnit.id).where(DepartmentUnit.department_id == body.department_id,
                                                 DepartmentUnit.jurisdiction_id == body.jurisdiction_id)):
        raise err("CONFLICT", message="This department is already mapped to this jurisdiction.")
    u = DepartmentUnit(department_id=body.department_id, jurisdiction_id=body.jurisdiction_id, active=body.active)
    db.add(u)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_MAPPED", entity_type="department_unit", entity_id=u.id,
                 details=body.model_dump())
    db.commit()
    return unit_dict(db, u)


@router.patch("/units/{unit_id}")
def update_unit(unit_id: uuid.UUID, body: UnitPatch, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    u = db.get(DepartmentUnit, unit_id)
    if u is None:
        raise err("NOT_FOUND")
    u.active = body.active
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_MAPPING_UPDATED", entity_type="department_unit", entity_id=u.id,
                 details={"active": body.active})
    db.commit()
    return unit_dict(db, u)


def unit_dependencies(db: Session, u: DepartmentUnit) -> dict:
    blocking = [
        ("Personnel assigned to this unit", _count(db, select(Officer.id).where(Officer.unit_id == u.id))),
        ("Complaints handled by this unit", _count(db, select(Complaint.id).where(Complaint.department_unit_id == u.id))),
        ("Complaint assignments", _count(db, select(Assignment.id).where(Assignment.department_unit_id == u.id))),
        ("Public issues", _count(db, select(PublicIssue.id).where(PublicIssue.department_unit_id == u.id))),
    ]
    return _deps_payload(f"{u.department.name} — {u.jurisdiction.name}", blocking, [], 0)


@router.get("/units/{unit_id}/dependencies")
def unit_deps(unit_id: uuid.UUID, db: Session = Depends(get_db)):
    u = db.get(DepartmentUnit, unit_id)
    if u is None:
        raise err("NOT_FOUND")
    return unit_dependencies(db, u)


@router.delete("/units/{unit_id}")
def delete_unit(unit_id: uuid.UUID, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    u = db.get(DepartmentUnit, unit_id)
    if u is None:
        raise err("NOT_FOUND")
    deps = unit_dependencies(db, u)
    if not deps["can_delete"]:
        raise err("DELETE_BLOCKED", details=deps)
    audit.record(db, actor_id=actor.user_id, action="DEPARTMENT_UNMAPPED", entity_type="department_unit", entity_id=u.id,
                 details={"department_id": u.department_id, "jurisdiction_id": u.jurisdiction_id})
    db.delete(u)
    db.commit()
    return {"deleted": True, "id": unit_id}


# ---------------- responsibilities ----------------
def rule_dict(r: ResponsibilityRule) -> dict:
    return {"id": r.id, "department_id": r.department_id, "department_name": r.department.name, "category": r.category,
            "name": r.name, "description": r.description, "active": r.active,
            "verification_status": r.verification_status, "is_prototype": r.verification_status.value == "PROTOTYPE",
            "verified": r.verified, "source_reference": r.source_reference, "created_at": r.created_at}


@router.get("/responsibilities")
def list_rules(db: Session = Depends(get_db)):
    return [rule_dict(r) for r in db.scalars(select(ResponsibilityRule).join(Department)
                                             .order_by(ResponsibilityRule.category, Department.name))]


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
    r.active, r.name, r.description = body.active, (body.name or "").strip() or None, body.description
    r.source_reference = (body.source_reference or "").strip() or None
    r.is_prototype = body.is_prototype  # transient attribute used by apply_status
    apply_status(r)
    r.verified = r.verification_status.value == "VERIFIED"
    db.flush()
    db.refresh(r)
    audit.record(db, actor_id=actor.user_id, action="RESPONSIBILITY_RULE_SAVED", entity_type="responsibility_rule", entity_id=r.id,
                 details={"before": before, "after": body.model_dump(exclude={"verified"})})
    db.commit()
    return rule_dict(r)


@router.delete("/responsibilities/{rule_id}")
def delete_rule(rule_id: uuid.UUID, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    r = db.get(ResponsibilityRule, rule_id)
    if r is None:
        raise err("NOT_FOUND")
    audit.record(db, actor_id=actor.user_id, action="RESPONSIBILITY_RULE_DELETED", entity_type="responsibility_rule",
                 entity_id=r.id, details={"department_id": r.department_id, "category": r.category, "name": r.name})
    db.delete(r)
    db.commit()
    return {"deleted": True, "id": rule_id}


# ---------------- users / personnel ----------------
def user_dict(db: Session, u: User) -> dict:
    o = db.scalar(select(Officer).where(Officer.user_id == u.id))
    officer = None
    if o:
        officer = {"officer_id": o.id, "department_id": o.department_id, "department_name": o.department.name,
                   "unit_id": o.unit_id, "unit_label": (f"{o.unit.department.name} — {o.unit.jurisdiction.name}" if o.unit else None),
                   "jurisdiction_name": o.unit.jurisdiction.name if o.unit else None,
                   "designation": o.designation, "active": o.active,
                   "areas": [{"jurisdiction_id": a.jurisdiction_id, "name": a.jurisdiction.name} for a in o.areas]}
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone, "role": u.role,
            "account_status": u.account_status, "created_at": u.created_at, "officer": officer,
            "permissions": [p.permission for p in u.permissions]}


def _resolve_unit(db: Session, unit_id: uuid.UUID | None, department_id: uuid.UUID | None) -> DepartmentUnit:
    if unit_id:
        u = db.get(DepartmentUnit, unit_id)
        if u is None:
            raise err("VALIDATION_ERROR", message="Unknown department unit.", details={"field": "unit_id"})
        return u
    if department_id:
        units = db.scalars(select(DepartmentUnit).where(DepartmentUnit.department_id == department_id)).all()
        if len(units) == 1:
            return units[0]
        if not units:
            raise err("VALIDATION_ERROR", message="Map this department to a jurisdiction before adding personnel.",
                      details={"field": "unit_id"})
    raise err("VALIDATION_ERROR", message="Department personnel need a department unit (department and jurisdiction).",
              details={"field": "unit_id"})


def _set_areas(db: Session, officer: Officer, unit: DepartmentUnit, area_ids: list[uuid.UUID]) -> None:
    allowed = descendant_ids(db, [unit.jurisdiction_id])
    bad = [a for a in area_ids if a not in allowed]
    if bad:
        raise err("VALIDATION_ERROR", message="Operational areas must lie inside the unit's jurisdiction.",
                  details={"field": "area_jurisdiction_ids"})
    officer.areas = [OfficerArea(jurisdiction_id=a) for a in dict.fromkeys(area_ids)]


@router.get("/users")
def list_users(db: Session = Depends(get_db), role: Role | None = None, q: str | None = Query(default=None, max_length=100),
               unit_id: uuid.UUID | None = None, limit: int = Query(default=100, le=500), offset: int = 0):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if unit_id:
        stmt = stmt.join(Officer, Officer.user_id == User.id).where(Officer.unit_id == unit_id)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.full_name.ilike(f"%{q}%"))
    total = _count(db, stmt)
    return {"total": total, "items": [user_dict(db, u) for u in db.scalars(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))]}


@router.post("/users", status_code=201)
def create_user(body: StaffCreate, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise err("EMAIL_IN_USE")
    unit = None
    if body.role in (Role.OFFICER, Role.DEPARTMENT_ADMIN):
        unit = _resolve_unit(db, body.unit_id, body.department_id)
    elif body.role == Role.CITIZEN:
        raise err("VALIDATION_ERROR", message="Citizens register themselves.", details={"field": "role"})
    u = User(full_name=body.full_name, email=body.email.lower(), phone=body.phone, password_hash=hash_password(body.password),
             role=body.role, account_status=AccountStatus.ACTIVE)
    db.add(u)
    db.flush()
    if unit:
        o = Officer(user_id=u.id, department_id=unit.department_id, unit_id=unit.id,
                    designation=body.designation or ("Department administrator" if body.role == Role.DEPARTMENT_ADMIN else "Officer"))
        db.add(o)
        db.flush()
        if body.role == Role.OFFICER and body.area_jurisdiction_ids:
            _set_areas(db, o, unit, body.area_jurisdiction_ids)
    audit.record(db, actor_id=actor.user_id, action="USER_CREATED", entity_type="user", entity_id=u.id,
                 details={"role": body.role, "unit_id": unit.id if unit else None,
                          "department_id": unit.department_id if unit else None, "areas": body.area_jurisdiction_ids})
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
        if body.unit_id or body.department_id or officer is None or officer.unit_id is None:
            unit = _resolve_unit(db, body.unit_id or (officer.unit_id if officer and not body.department_id else None), body.department_id)
        else:
            unit = officer.unit
        if officer is None:
            officer = Officer(user_id=u.id, department_id=unit.department_id, unit_id=unit.id, designation=body.designation or "Officer")
            db.add(officer)
            db.flush()
        if officer.unit_id != unit.id:
            officer.areas = []
        officer.department_id, officer.unit_id = unit.department_id, unit.id
        if body.designation:
            officer.designation = body.designation
        if body.officer_active is not None:
            officer.active = body.officer_active
        if body.area_jurisdiction_ids is not None:
            _set_areas(db, officer, unit, body.area_jurisdiction_ids if u.role == Role.OFFICER else [])
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


# ---------------- escalation policy ----------------
class PolicyIn(BaseModel):
    priority_level: str = Field(pattern="^(CRITICAL|HIGH|MEDIUM|LOW|UNSCORED)$")
    resolve_within_hours: int = Field(ge=1, le=24 * 365)
    department_id: uuid.UUID | None = None


@router.get("/escalation-policies")
def get_policies(db: Session = Depends(get_db)):
    return {"policies": esc_service.effective_policies(db), "defaults": esc_service.DEFAULT_HOURS,
            "note": "Prototype defaults, not an official service-level standard. Configure the authority's actual deadlines."}


@router.put("/escalation-policies")
def set_policy(body: PolicyIn, actor: Actor = Depends(require_system_admin), db: Session = Depends(get_db)):
    if body.department_id and db.get(Department, body.department_id) is None:
        raise err("VALIDATION_ERROR", message="Unknown department.", details={"field": "department_id"})
    row = db.scalar(select(EscalationPolicy).where(EscalationPolicy.priority_level == body.priority_level,
                                                   EscalationPolicy.department_id.is_(None) if body.department_id is None
                                                   else EscalationPolicy.department_id == body.department_id))
    if row is None:
        row = EscalationPolicy(priority_level=body.priority_level, department_id=body.department_id,
                               resolve_within_hours=body.resolve_within_hours)
        db.add(row)
    row.resolve_within_hours = body.resolve_within_hours
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="ESCALATION_POLICY_SAVED", entity_type="escalation_policy", entity_id=row.id,
                 details=body.model_dump())
    db.commit()
    return esc_service.effective_policies(db)


# ---------------- source references ----------------
@router.get("/source-references")
def source_references(db: Session = Depends(get_db), status: str | None = Query(default=None, pattern="^(VERIFIED|PENDING_VERIFICATION|PROTOTYPE)$")):
    items = []
    for d in db.scalars(select(Department)):
        items.append({"type": "Department", "id": d.id, "name": d.name, "verification_status": d.verification_status,
                      "source_reference": d.source_reference, "active": d.active})
    for j in db.scalars(select(Jurisdiction)):
        items.append({"type": "Jurisdiction", "id": j.id, "name": j.name, "verification_status": j.verification_status,
                      "source_reference": j.source_reference, "active": j.active})
    for r in db.scalars(select(ResponsibilityRule)):
        items.append({"type": "Responsibility", "id": r.id, "name": f"{r.department.name}: {r.name or r.category.value}",
                      "verification_status": r.verification_status, "source_reference": r.source_reference, "active": r.active})
    if status:
        items = [i for i in items if i["verification_status"].value == status]
    counts = {}
    for i in items:
        counts[i["verification_status"].value] = counts.get(i["verification_status"].value, 0) + 1
    return {"counts": counts, "items": sorted(items, key=lambda i: (i["type"], i["name"].lower())),
            "note": "VERIFIED means a source reference has been recorded. It is not independent government certification."}
