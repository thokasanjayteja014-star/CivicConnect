"""Deterministic jurisdiction- and responsibility-aware routing (no AI involved).

`determine_routing` is a pure function over facts gathered from PostGIS and the
administrative configuration:

1. resolve the deepest jurisdiction containing the location (ward/village),
2. find departments with an active responsibility for the category,
3. find each department's nearest active unit along the jurisdiction's ancestor chain,
4. route only when exactly one unit qualifies, otherwise send to administrative review,
5. pick an eligible officer of that unit by operational area, then workload.

A complaint is never discarded: anything that cannot be routed is PENDING_REVIEW, and a
routed complaint without an eligible officer waits in the unit's unassigned queue.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.models.enums import RoutingStatus

MESSAGES = {
    "ROUTED": "Routed to the responsible department.",
    "PENDING_REVIEW": "We could not identify a responsible department automatically. The complaint is in administrative review.",
    "UNROUTED": "No eligible department is configured for this complaint category and location. The complaint is in administrative review.",
    "MULTIPLE_DEPARTMENTS": "Multiple departments may be responsible for this issue. Administrative review is required.",
    "OUTSIDE_JURISDICTION": "The selected location could not be matched to a configured jurisdiction. Administrative review is required.",
}


@dataclass(frozen=True)
class DepartmentFact:
    id: uuid.UUID
    name: str
    active: bool


@dataclass(frozen=True)
class UnitFact:
    id: uuid.UUID
    department_id: uuid.UUID
    jurisdiction_id: uuid.UUID
    jurisdiction_name: str
    active: bool


@dataclass(frozen=True)
class OfficerFact:
    id: uuid.UUID
    name: str
    active_assignments: int
    # Depth of the most specific operational area covering the location; -1 = no areas configured
    # (covers the whole unit); None = has areas but none cover the location (not eligible).
    match_depth: int | None


@dataclass
class LeafFact:
    id: uuid.UUID
    name: str
    path: str
    # Nearest unit per responsible department along this leaf's ancestor chain (None if not operating here).
    units: dict[uuid.UUID, UnitFact | None] = field(default_factory=dict)


@dataclass
class RoutingInput:
    category: str
    any_jurisdiction_configured: bool
    location_uncertain: bool
    accuracy_meters: float | None
    leaves: list[LeafFact]
    responsible: list[DepartmentFact]  # departments with an active responsibility for the category
    officers: dict[uuid.UUID, list[OfficerFact]] = field(default_factory=dict)  # per unit id


@dataclass
class RoutingResult:
    routing_status: RoutingStatus
    reason_code: str
    explanation: str
    department_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    jurisdiction_id: uuid.UUID | None = None
    officer_id: uuid.UUID | None = None
    officer_reason: str | None = None
    candidates: dict = field(default_factory=dict)

    @property
    def message(self) -> str:
        return MESSAGES.get(self.reason_code, MESSAGES[self.routing_status.value])


def choose_officer(officers: list[OfficerFact]) -> tuple[OfficerFact | None, str]:
    eligible = [o for o in officers if o.match_depth is not None]
    if not eligible:
        return None, ("No active officer of this unit covers the location; the complaint is waiting in the "
                      "department's unassigned queue." if officers else
                      "This unit has no active officers; the complaint is waiting in the department's unassigned queue.")
    eligible.sort(key=lambda o: (-o.match_depth, o.active_assignments, o.name, str(o.id)))
    best = eligible[0]
    basis = "operational area covering the location" if best.match_depth >= 0 else "unit-wide officer (no operational areas set)"
    return best, f"Assigned to {best.name}: {basis}, {best.active_assignments} active assignment(s)."


def determine_routing(inp: RoutingInput) -> RoutingResult:
    pending = RoutingStatus.PENDING_REVIEW
    if inp.location_uncertain:
        return RoutingResult(pending, "LOCATION_UNCERTAIN",
                             f"Reported location accuracy ({inp.accuracy_meters} m) exceeds the configured limit; "
                             "an administrator should confirm the location before routing.")
    if not inp.any_jurisdiction_configured:
        return RoutingResult(pending, "NO_JURISDICTION_CONFIGURED",
                             "No jurisdiction boundaries are configured yet, so no department can be determined.")
    if not inp.leaves:
        return RoutingResult(pending, "OUTSIDE_JURISDICTION",
                             "The location does not fall inside any configured jurisdiction boundary.")

    places = "; ".join(leaf.path for leaf in inp.leaves)
    candidates: dict = {
        "jurisdictions": [{"id": str(leaf.id), "name": leaf.name, "path": leaf.path} for leaf in inp.leaves],
        "responsible_departments": [{"id": str(d.id), "name": d.name, "active": d.active} for d in inp.responsible],
    }
    if not inp.responsible:
        return RoutingResult(pending, "NO_RESPONSIBILITY",
                             f"Location is within {places}, but no department has an active responsibility for "
                             f"{inp.category}. Configure a responsibility to route these complaints.",
                             jurisdiction_id=inp.leaves[0].id, candidates=candidates)

    inactive = [d.name for d in inp.responsible if not d.active]
    units: dict[uuid.UUID, tuple[UnitFact, DepartmentFact, LeafFact]] = {}
    not_operating, unit_inactive = [], []
    for d in inp.responsible:
        if not d.active:
            continue
        for leaf in inp.leaves:
            u = leaf.units.get(d.id)
            if u is None:
                not_operating.append(f"'{d.name}' is not mapped to {leaf.path}")
            elif not u.active:
                unit_inactive.append(f"'{d.name}' is deactivated in {u.jurisdiction_name}")
            else:
                units[u.id] = (u, d, leaf)
    candidates["units"] = [{"id": str(u.id), "department": d.name, "jurisdiction": u.jurisdiction_name}
                           for u, d, _ in units.values()]

    if len(units) > 1:
        names = ", ".join(sorted(f"{d.name} ({u.jurisdiction_name})" for u, d, _ in units.values()))
        return RoutingResult(pending, "MULTIPLE_DEPARTMENTS",
                             f"Location is within {places}. More than one department unit is responsible for "
                             f"{inp.category}: {names}. No department was selected automatically.",
                             jurisdiction_id=inp.leaves[0].id, candidates=candidates)
    if not units:
        problems = sorted(set(not_operating + unit_inactive + [f"'{n}' is inactive" for n in inactive]))
        candidates["actionable"] = problems
        return RoutingResult(pending, "DEPARTMENT_NOT_ACTIVE_HERE",
                             f"Location is within {places}, but no active department unit handles {inp.category} "
                             f"here: {'; '.join(problems)}.",
                             jurisdiction_id=inp.leaves[0].id, candidates=candidates)

    unit, dept, leaf = next(iter(units.values()))
    officer, officer_reason = choose_officer(inp.officers.get(unit.id, []))
    return RoutingResult(
        RoutingStatus.ROUTED, "ROUTED",
        f"Location is within {leaf.path}. '{dept.name}' has an active responsibility for {inp.category} and "
        f"operates here through its {unit.jurisdiction_name} unit.",
        department_id=dept.id, unit_id=unit.id, jurisdiction_id=leaf.id,
        officer_id=officer.id if officer else None, officer_reason=officer_reason, candidates=candidates,
    )
