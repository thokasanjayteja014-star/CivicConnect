"""Deterministic geospatial department routing (spec L8, E19-E21).

`determine_department` is a pure function over facts gathered from PostGIS
and the configured responsibility rules. It never guesses: a department is
returned only when exactly one valid candidate exists. No AI is involved.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.models.enums import RoutingStatus

MESSAGES = {
    "ROUTED": "Routed to the configured responsible department.",
    "PENDING_REVIEW": "We could not identify a responsible department automatically. The complaint requires administrative review.",
    "UNROUTED": "No eligible department is configured for this complaint category and location. The complaint remains unassigned.",
    "MULTIPLE_DEPARTMENTS": "Multiple departments may be responsible for this issue. Administrative review is required.",
    "OUTSIDE_JURISDICTION": "The selected location could not be matched to a verified jurisdiction.",
}


@dataclass(frozen=True)
class DepartmentFact:
    id: uuid.UUID
    name: str
    active: bool


@dataclass(frozen=True)
class RuleFact:
    department_id: uuid.UUID
    active: bool
    verified: bool


@dataclass
class JurisdictionFact:
    id: uuid.UUID
    name: str
    is_prototype: bool
    departments: list[DepartmentFact] = field(default_factory=list)


@dataclass
class RoutingInput:
    category: str
    any_jurisdiction_configured: bool
    location_uncertain: bool
    accuracy_meters: float | None
    containing: list[JurisdictionFact]
    rules: list[RuleFact]  # rules for this category (any state)


@dataclass
class RoutingResult:
    routing_status: RoutingStatus
    reason_code: str
    explanation: str
    department_id: uuid.UUID | None = None
    jurisdiction_id: uuid.UUID | None = None
    candidates: dict = field(default_factory=dict)

    @property
    def message(self) -> str:
        return MESSAGES.get(self.reason_code, MESSAGES[self.routing_status.value])


def determine_department(inp: RoutingInput) -> RoutingResult:
    if inp.location_uncertain:
        return RoutingResult(
            RoutingStatus.PENDING_REVIEW,
            "LOCATION_UNCERTAIN",
            f"Reported location accuracy ({inp.accuracy_meters} m) exceeds the configured limit; "
            "an administrator should confirm the location before routing.",
        )

    if not inp.any_jurisdiction_configured:
        return RoutingResult(
            RoutingStatus.UNROUTED,
            "NO_JURISDICTION_CONFIGURED",
            "No jurisdiction boundaries are configured, so no department can be determined.",
        )

    if not inp.containing:
        return RoutingResult(
            RoutingStatus.PENDING_REVIEW,
            "OUTSIDE_JURISDICTION",
            "The location does not fall inside any configured jurisdiction; location clarification or "
            "administrative review is required.",
        )

    rules_by_dept = {r.department_id: r for r in inp.rules}
    jurisdictions_by_dept: dict[uuid.UUID, list[JurisdictionFact]] = {}
    depts: dict[uuid.UUID, DepartmentFact] = {}
    for j in inp.containing:
        for d in j.departments:
            depts[d.id] = d
            jurisdictions_by_dept.setdefault(d.id, []).append(j)

    eligible = [
        d for d in depts.values()
        if d.active and (r := rules_by_dept.get(d.id)) is not None and r.active and r.verified
    ]
    eligible.sort(key=lambda d: d.name)
    jnames = ", ".join(sorted(f"{j.name}{' (prototype configuration)' if j.is_prototype else ''}" for j in inp.containing))
    candidates = {
        "jurisdictions": [{"id": str(j.id), "name": j.name, "is_prototype": j.is_prototype} for j in inp.containing],
        "eligible_departments": [{"id": str(d.id), "name": d.name} for d in eligible],
    }

    if len(eligible) == 1:
        dept = eligible[0]
        juris = sorted(jurisdictions_by_dept[dept.id], key=lambda j: j.name)[0]
        return RoutingResult(
            RoutingStatus.ROUTED,
            "ROUTED",
            f"Location is within {jnames}. '{dept.name}' is the only active department with a verified "
            f"responsibility rule for {inp.category} in this jurisdiction.",
            department_id=dept.id,
            jurisdiction_id=juris.id,
            candidates=candidates,
        )

    if len(eligible) > 1:
        names = ", ".join(d.name for d in eligible)
        return RoutingResult(
            RoutingStatus.PENDING_REVIEW,
            "MULTIPLE_DEPARTMENTS",
            f"Location is within {jnames}. Multiple departments have verified responsibility for "
            f"{inp.category}: {names}. No department was selected automatically.",
            candidates=candidates,
        )

    # No eligible department: is there something an administrator can fix?
    actionable = []
    for d in depts.values():
        r = rules_by_dept.get(d.id)
        if r is None:
            continue
        if not r.verified:
            actionable.append(f"'{d.name}' has an unverified rule for {inp.category}")
        elif not r.active:
            actionable.append(f"'{d.name}' has an inactive rule for {inp.category}")
        elif not d.active:
            actionable.append(f"'{d.name}' has a verified rule but the department is inactive")
    if actionable:
        candidates["actionable"] = actionable
        return RoutingResult(
            RoutingStatus.PENDING_REVIEW,
            "INCOMPLETE_CONFIGURATION",
            f"Location is within {jnames}, but the responsibility configuration is incomplete: "
            + "; ".join(sorted(actionable)) + ".",
            candidates=candidates,
        )

    return RoutingResult(
        RoutingStatus.UNROUTED,
        "NO_ELIGIBLE_DEPARTMENT",
        f"Location is within {jnames}, but no department in this jurisdiction has any responsibility rule "
        f"for {inp.category}.",
        candidates=candidates,
    )
