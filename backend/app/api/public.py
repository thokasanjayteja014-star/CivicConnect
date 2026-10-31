"""Public accountability endpoints (spec F12, L12). No authentication; privacy-filtered."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Complaint, Jurisdiction, StatusHistory
from app.models.enums import Category, ComplaintStatus, PublicationStatus
from app.services.views import PUBLIC_STATUS_LABEL, PUBLIC_STATUSES, approximate, filter_public_complaint

router = APIRouter(prefix="/api/public", tags=["public"])

MIN_RECORDS_FOR_TRENDS = 5


def public_base():
    return select(Complaint).where(
        Complaint.publication_status == PublicationStatus.APPROVED,
        Complaint.allow_public_display.is_(True),
        Complaint.flagged_misuse.is_(False),
        Complaint.public_summary.is_not(None),
        Complaint.status.in_(PUBLIC_STATUSES),
    )


def _filtered(category, status, area_id, reference=None):
    stmt = public_base()
    if category:
        stmt = stmt.where(Complaint.category == category)
    if status:
        stmt = stmt.where(Complaint.status == status)
    if area_id:
        stmt = stmt.where(Complaint.jurisdiction_id == area_id)
    if reference:
        stmt = stmt.where(Complaint.reference_id == reference.strip().upper())
    return stmt


def latest_update(db: Session, complaint_id) -> dict | None:
    h = db.scalar(select(StatusHistory).where(StatusHistory.complaint_id == complaint_id).order_by(StatusHistory.created_at.desc()))
    return {"status": PUBLIC_STATUS_LABEL.get(h.new_status, h.new_status.value), "date": h.created_at.date().isoformat()} if h else None


@router.get("/complaints")
def public_complaints(db: Session = Depends(get_db), category: Category | None = None, status: ComplaintStatus | None = None,
                      area_id: uuid.UUID | None = None, reference: str | None = Query(default=None, max_length=32),
                      limit: int = Query(default=50, le=200), offset: int = 0):
    stmt = _filtered(category, status, area_id, reference)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Complaint.created_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [filter_public_complaint(c, latest_update(db, c.id)) for c in rows]}


@router.get("/map")
def public_map(db: Session = Depends(get_db), category: Category | None = None, status: ComplaintStatus | None = None,
               area_id: uuid.UUID | None = None):
    rows = db.scalars(_filtered(category, status, area_id).limit(2000)).all()
    return {
        "approximation": "Locations are rounded to protect privacy and are not exact.",
        "features": [
            {"public_reference": c.reference_id, "category": c.category.value, "status": c.status.value,
             "public_status": PUBLIC_STATUS_LABEL[c.status], "latitude": approximate(c.latitude),
             "longitude": approximate(c.longitude), "public_summary": c.public_summary}
            for c in rows
        ],
    }


@router.get("/areas")
def areas(db: Session = Depends(get_db)):
    rows = db.scalars(select(Jurisdiction).where(Jurisdiction.active.is_(True)).order_by(Jurisdiction.name)).all()
    return [{"id": j.id, "name": j.name, "is_prototype": j.is_prototype} for j in rows]


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), category: Category | None = None, area_id: uuid.UUID | None = None):
    base = _filtered(category, None, area_id).subquery()
    total = db.scalar(select(func.count()).select_from(base))
    by_cat = db.execute(select(base.c.category, func.count()).group_by(base.c.category)).all()
    by_status = db.execute(select(base.c.status, func.count()).group_by(base.c.status)).all()
    by_area = db.execute(
        select(Jurisdiction.name, func.count()).select_from(base)
        .join(Jurisdiction, Jurisdiction.id == base.c.jurisdiction_id, isouter=True)
        .group_by(Jurisdiction.name)
    ).all()
    trend = None
    if total >= MIN_RECORDS_FOR_TRENDS:
        since = datetime.now(timezone.utc) - timedelta(weeks=12)
        week = func.date_trunc("week", base.c.created_at)
        trend = [
            {"week_start": w.date().isoformat(), "count": n}
            for w, n in db.execute(select(week, func.count()).where(base.c.created_at >= since).group_by(week).order_by(week)).all()
        ]
    return {
        "total_public": total,
        "by_category": {c.value if hasattr(c, "value") else c: n for c, n in by_cat},
        "by_status": {
            (s.value if hasattr(s, "value") else s): {"count": n, "label": PUBLIC_STATUS_LABEL.get(ComplaintStatus(s), s)}
            for s, n in by_status
        },
        "by_area": {(a or "Outside configured areas"): n for a, n in by_area},
        "trend_weekly": trend,
        "trend_note": None if trend is not None else f"Trends are shown once at least {MIN_RECORDS_FOR_TRENDS} public records exist.",
        "computed_at": datetime.now(timezone.utc),
        "source": "Computed live from privacy-reviewed CivicConnect records.",
    }
