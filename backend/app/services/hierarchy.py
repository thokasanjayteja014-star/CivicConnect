"""Jurisdiction hierarchy, department units and configuration status helpers."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import DepartmentUnit, Jurisdiction
from app.models.enums import VerificationStatus

JURISDICTION_TYPES = [
    "STATE", "DISTRICT", "SUBDIVISION", "TALUK", "MANDAL", "MUNICIPAL_CORPORATION", "MUNICIPALITY",
    "GRAM_PANCHAYAT", "WARD", "VILLAGE", "ZONE", "OTHER",
]


def compute_verification_status(source_reference: str | None, is_prototype: bool) -> VerificationStatus:
    """Prototype wins; otherwise a recorded source reference means VERIFIED, else PENDING_VERIFICATION.

    VERIFIED only means an administrator recorded a source reference. It is not government certification.
    """
    if is_prototype:
        return VerificationStatus.PROTOTYPE
    if source_reference and source_reference.strip():
        return VerificationStatus.VERIFIED
    return VerificationStatus.PENDING_VERIFICATION


def apply_status(obj, changes: dict | None = None) -> None:
    """Set verification_status/is_prototype on create, or on update when the inputs changed."""
    if changes is not None and not ({"source_reference", "is_prototype"} & set(changes)):
        return
    status = compute_verification_status(obj.source_reference, bool(obj.is_prototype))
    obj.verification_status = status
    obj.is_prototype = status == VerificationStatus.PROTOTYPE


def ancestor_ids(db: Session, jurisdiction_id: uuid.UUID) -> list[uuid.UUID]:
    """[self, parent, grandparent, ...] (cycle-safe)."""
    rows = db.execute(text("""
        WITH RECURSIVE up(id, parent_id, depth, path) AS (
            SELECT id, parent_id, 0, ARRAY[id] FROM jurisdictions WHERE id = :jid
            UNION ALL
            SELECT j.id, j.parent_id, up.depth + 1, up.path || j.id
            FROM jurisdictions j JOIN up ON j.id = up.parent_id
            WHERE NOT j.id = ANY(up.path)
        ) SELECT id FROM up ORDER BY depth
    """), {"jid": jurisdiction_id}).all()
    return [r[0] for r in rows]


def descendant_ids(db: Session, jurisdiction_ids: list[uuid.UUID] | set[uuid.UUID]) -> set[uuid.UUID]:
    """The given jurisdictions and all their descendants."""
    ids = list(jurisdiction_ids)
    if not ids:
        return set()
    rows = db.execute(text("""
        WITH RECURSIVE down(id, path) AS (
            SELECT id, ARRAY[id] FROM jurisdictions WHERE id = ANY(:ids)
            UNION ALL
            SELECT j.id, down.path || j.id FROM jurisdictions j JOIN down ON j.parent_id = down.id
            WHERE NOT j.id = ANY(down.path)
        ) SELECT DISTINCT id FROM down
    """), {"ids": ids}).all()
    return {r[0] for r in rows}


def would_create_cycle(db: Session, jurisdiction_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> bool:
    if new_parent_id is None:
        return False
    return jurisdiction_id in ancestor_ids(db, new_parent_id)


def depth_map(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(text("""
        WITH RECURSIVE t(id, depth, path) AS (
            SELECT id, 0, ARRAY[id] FROM jurisdictions WHERE parent_id IS NULL
            UNION ALL
            SELECT j.id, t.depth + 1, t.path || j.id FROM jurisdictions j JOIN t ON j.parent_id = t.id
            WHERE NOT j.id = ANY(t.path)
        ) SELECT id, depth FROM t
    """)).all()
    return {r[0]: r[1] for r in rows}


def jurisdiction_path(db: Session, jurisdiction_id: uuid.UUID | None) -> str | None:
    """'Karnataka › Dharwad › Ward 4' for display."""
    if not jurisdiction_id:
        return None
    ids = ancestor_ids(db, jurisdiction_id)
    names = dict(db.execute(select(Jurisdiction.id, Jurisdiction.name).where(Jurisdiction.id.in_(ids))).all())
    return " › ".join(names[i] for i in reversed(ids) if i in names)


def containing_leaf_jurisdictions(db: Session, lat: float, lng: float) -> list[Jurisdiction]:
    """Active jurisdictions whose boundary contains the point and that have no active containing child.

    Returns the deepest matches (normally one ward/village). Jurisdictions without a boundary
    are reached through their children or not at all.
    """
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    rows = db.scalars(select(Jurisdiction).where(
        Jurisdiction.active.is_(True), Jurisdiction.boundary.is_not(None), func.ST_Covers(Jurisdiction.boundary, point)
    )).all()
    if not rows:
        return []
    depths = depth_map(db)
    best = max(depths.get(j.id, 0) for j in rows)
    return sorted([j for j in rows if depths.get(j.id, 0) == best], key=lambda j: j.name)


def nearest_unit(db: Session, department_id: uuid.UUID, chain: list[uuid.UUID]) -> DepartmentUnit | None:
    """The department's unit closest to the leaf along the ancestor chain (leaf first)."""
    if not chain:
        return None
    units = db.scalars(select(DepartmentUnit).where(
        DepartmentUnit.department_id == department_id, DepartmentUnit.jurisdiction_id.in_(chain))).all()
    by_j = {u.jurisdiction_id: u for u in units}
    for jid in chain:
        if jid in by_j:
            return by_j[jid]
    return None
