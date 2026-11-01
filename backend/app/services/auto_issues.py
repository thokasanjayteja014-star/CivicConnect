"""Automatic public issues built from clusters of similar complaints.

When several residents report the same kind of problem close together, CivicConnect opens a
public issue on its own, without waiting for staff. The department gets REVIEW_DAYS to review
it; after that it is published automatically whether or not anyone acted. A department cannot
stop or withdraw an automatic issue; only the main administration can unpublish it.

Only public, PII-free information is used: category, area name and a rounded centre point.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit
from app.models import AuditLog, Complaint, Jurisdiction, PublicIssue, PublicIssueComplaint, PublicIssueUpdate
from app.models.enums import (
    ComplaintStatus,
    PublicIssueProgress,
    PublicIssueStatus,
    RoutingStatus,
)

MIN_REPORTS = 3            # reports needed before an issue is opened
RADIUS_METERS = 200        # reports within this distance count as the same place
WINDOW_DAYS = 30           # only recent reports are grouped
REVIEW_DAYS = 7            # department review window before automatic publication
_LOCK_KEY = 74_203_311     # advisory lock so concurrent page loads don't double-create

CATEGORY_WORDS = {
    "ROAD_INFRASTRUCTURE": "road",
    "WATER_SUPPLY": "water supply",
    "SANITATION": "sanitation",
    "DRAINAGE": "drainage",
    "STREETLIGHT": "streetlight",
    "PUBLIC_INFRASTRUCTURE": "public infrastructure",
    "OTHER": "civic",
}

AUTO_PUBLISH_MESSAGE = (f"Published automatically because the department did not complete its review within "
                        f"{REVIEW_DAYS} days.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _meters(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _centre(complaints: list[Complaint]) -> tuple[float, float]:
    # ~110 m precision: enough to show the area, not a doorstep.
    n = len(complaints)
    return (round(sum(c.latitude for c in complaints) / n, 3), round(sum(c.longitude for c in complaints) / n, 3))


def _label(category) -> str:
    return CATEGORY_WORDS.get(getattr(category, "value", category), "civic")


def _excluded_ids(db: Session) -> set[str]:
    """Complaints that staff deliberately removed from an issue are never grouped again."""
    rows = db.scalars(select(AuditLog.details).where(AuditLog.entity_type == "public_issue",
                                                     AuditLog.action == "PUBLIC_ISSUE_UNLINKED")).all()
    return {str(d.get("complaint_id")) for d in rows if isinstance(d, dict) and d.get("complaint_id")}


def _candidates(db: Session, now: datetime) -> list[Complaint]:
    linked = select(PublicIssueComplaint.complaint_id)
    rows = db.scalars(select(Complaint).where(
        Complaint.routing_status == RoutingStatus.ROUTED, Complaint.department_unit_id.is_not(None),
        Complaint.status != ComplaintStatus.REJECTED, Complaint.created_at >= now - timedelta(days=WINDOW_DAYS),
        Complaint.latitude.is_not(None), Complaint.id.not_in(linked)).order_by(Complaint.created_at)).all()
    excluded = _excluded_ids(db)
    return [c for c in rows if str(c.id) not in excluded]


def _link(db: Session, issue: PublicIssue, complaints: list[Complaint]) -> None:
    for c in complaints:
        db.add(PublicIssueComplaint(issue_id=issue.id, complaint_id=c.id, linked_by=None))


def _create(db: Session, group: list[Complaint], now: datetime) -> PublicIssue:
    first = group[0]
    area = db.get(Jurisdiction, first.jurisdiction_id).name if first.jurisdiction_id else None
    word = _label(first.category)
    where = f" in {area}" if area else ""
    lat, lng = _centre(group)
    issue = PublicIssue(
        title=f"Several residents reported {word} problems{where}"[:160],
        description=(f"Several residents independently reported {word} problems within about {RADIUS_METERS} metres of "
                     f"each other{where}. CivicConnect grouped these reports automatically so the wider problem is "
                     f"visible to everyone. The personal details of the people who reported it are never shown."),
        general_location=area, latitude=lat, longitude=lng, category=first.category,
        department_id=first.department_id, department_unit_id=first.department_unit_id,
        jurisdiction_id=first.jurisdiction_id, created_by=None, auto_generated=True,
        auto_publish_at=now + timedelta(days=REVIEW_DAYS))
    db.add(issue)
    db.flush()
    _link(db, issue, group)
    audit.record(db, actor_id=None, actor_label="system", action="PUBLIC_ISSUE_AUTO_CREATED", entity_type="public_issue",
                 entity_id=issue.id, details={"complaints": [c.reference_id for c in group]})
    return issue


def _group_new(db: Session, now: datetime) -> int:
    """Attach new reports to open automatic issues nearby, and open new issues for fresh clusters."""
    changed = 0
    open_issues = db.scalars(select(PublicIssue).where(
        PublicIssue.auto_generated.is_(True), PublicIssue.status != PublicIssueStatus.UNPUBLISHED,
        PublicIssue.progress != PublicIssueProgress.RESOLVED, PublicIssue.latitude.is_not(None))).all()
    pool: list[Complaint] = []
    for c in _candidates(db, now):
        home = next((i for i in open_issues if i.department_unit_id == c.department_unit_id and i.category == c.category
                     and _meters(i.latitude, i.longitude, c.latitude, c.longitude) <= RADIUS_METERS), None)
        if home is not None:
            _link(db, home, [c])
            home.updated_at = now
            audit.record(db, actor_id=None, actor_label="system", action="PUBLIC_ISSUE_AUTO_LINKED",
                         entity_type="public_issue", entity_id=home.id, details={"complaints": [c.reference_id]})
            changed += 1
        else:
            pool.append(c)

    used: set[uuid.UUID] = set()
    for seed in pool:
        if seed.id in used:
            continue
        group = [c for c in pool if c.id not in used and c.department_unit_id == seed.department_unit_id
                 and c.category == seed.category
                 and _meters(seed.latitude, seed.longitude, c.latitude, c.longitude) <= RADIUS_METERS]
        if len(group) < MIN_REPORTS:
            continue
        # Nothing to warn the public about if every report is already fixed.
        if all(c.status == ComplaintStatus.VERIFIED_RESOLVED for c in group):
            continue
        _create(db, group, now)
        used.update(c.id for c in group)
        changed += 1
    return changed


def _publish_due(db: Session, now: datetime) -> int:
    due = db.scalars(select(PublicIssue).where(
        PublicIssue.auto_generated.is_(True),
        PublicIssue.status.in_((PublicIssueStatus.DRAFT, PublicIssueStatus.VERIFIED)),
        PublicIssue.auto_publish_at.is_not(None), PublicIssue.auto_publish_at <= now)).all()
    for issue in due:
        issue.status, issue.published_at, issue.published_by = PublicIssueStatus.PUBLISHED, now, None
        issue.published_automatically = True
        db.add(PublicIssueUpdate(issue_id=issue.id, message=AUTO_PUBLISH_MESSAGE, progress=None, author_id=None))
        audit.record(db, actor_id=None, actor_label="system", action="PUBLIC_ISSUE_AUTO_PUBLISHED",
                     entity_type="public_issue", entity_id=issue.id, details={"reviewed": issue.verified_at is not None})
    return len(due)


def run_auto_public_issues(db: Session, now: datetime | None = None) -> int:
    """Idempotent; safe to call on every page load. Returns the number of changes made."""
    now = now or _now()
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        if not db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _LOCK_KEY}).scalar():
            return 0
    try:
        changed = _group_new(db, now) + _publish_due(db, now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return changed
