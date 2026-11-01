"""Role-aware response builders. Citizen and public views never include
internal remarks, other citizens' data, storage keys or staff identities."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AIAnalysis,
    Assignment,
    CitizenFeedback,
    Complaint,
    ComplaintRelationship,
    ComplaintRemark,
    Department,
    Escalation,
    Media,
    Officer,
    ResolutionEvidence,
    RoutingDecision,
    StatusHistory,
    User,
    VerificationDecision,
)
from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus as S,
    MediaPurpose,
    PublicationStatus,
    RelationshipStatus,
    RemarkVisibility,
    Role,
)
from app.security.permissions import Actor
from app.services.complaints import latest_priority, latest_routing_decision
from app.services.lifecycle import allowed_targets
from app.services.workflow import can_decide_reopening, can_verify
from app.services.escalation import escalation_dict
from app.services.hierarchy import jurisdiction_path

ROLE_LABEL = {
    Role.CITIZEN: "Citizen",
    Role.OFFICER: "Department officer",
    Role.DEPARTMENT_ADMIN: "Department administrator",
    Role.SYSTEM_ADMIN: "System administrator",
}

PUBLIC_STATUS_LABEL = {
    S.SUBMITTED: "Reported",
    S.UNDER_REVIEW: "Under review",
    S.ASSIGNED: "Assigned",
    S.IN_PROGRESS: "In progress",
    S.ON_HOLD: "On hold",
    S.RESOLVED_AWAITING_VERIFICATION: "Resolved (authority-reported, awaiting verification)",
    S.VERIFIED_RESOLVED: "Verified resolved",
}
PUBLIC_STATUSES = set(PUBLIC_STATUS_LABEL)


def media_out(m: Media) -> dict:
    return {
        "media_id": m.id,
        "media_type": m.media_type,
        "mime_type": m.mime_type,
        "file_size_bytes": m.file_size_bytes,
        "duration_seconds": m.duration_seconds,
        "original_filename": m.original_filename,
        "uploaded_at": m.uploaded_at,
    }


def dept_out(d: Department | None) -> dict | None:
    return {"id": d.id, "name": d.name, "is_prototype": d.is_prototype} if d else None


def active_assignment(db: Session, complaint_id: uuid.UUID) -> Assignment | None:
    return db.scalar(select(Assignment).where(Assignment.complaint_id == complaint_id,
                                              Assignment.assignment_status == AssignmentStatus.ACTIVE))


def officer_out(db: Session, officer: Officer | None, include_name: bool) -> dict | None:
    if officer is None:
        return None
    out = {"officer_id": officer.id, "designation": officer.designation}
    if include_name:
        out["full_name"] = officer.user.full_name
    return out


def _overdue(c: Complaint) -> bool:
    from datetime import datetime, timezone
    from app.services.escalation import OPEN_STATUSES
    return bool(c.due_at and c.status in OPEN_STATUSES and c.due_at < datetime.now(timezone.utc))


def _escalated(db: Session, c: Complaint) -> int:
    from app.models import Escalation
    from app.models.enums import EscalationStatus
    return db.scalar(select(func.max(Escalation.level)).where(Escalation.complaint_id == c.id,
                                                               Escalation.status == EscalationStatus.OPEN)) or 0


def list_item(db: Session, c: Complaint, staff: bool) -> dict:
    a = active_assignment(db, c.id)
    return {
        "complaint_id": c.id,
        "reference_id": c.reference_id,
        "title": c.title,
        "category": c.category,
        "status": c.status,
        "priority_score": float(c.priority_score) if c.priority_score is not None else None,
        "priority_level": c.priority_level,
        "priority_assessment_status": c.priority_assessment_status,
        "needs_prompt_review": c.needs_prompt_review,
        "routing_status": c.routing_status,
        "department": dept_out(c.department),
        "jurisdiction": ({"id": c.jurisdiction.id, "name": c.jurisdiction.name} if c.jurisdiction else None),
        "location": {"latitude": c.latitude, "longitude": c.longitude, "landmark": c.landmark, "address_text": c.address_text},
        "assigned_officer": officer_out(db, a.officer if a else None, include_name=staff) if a else None,
        "assignment_accepted": bool(a and a.accepted_at),
        **({"due_at": c.due_at, "overdue": _overdue(c), "escalated": _escalated(db, c)} if staff else {}),
        "version": c.version,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def priority_view(db: Session, c: Complaint) -> dict:
    pa = latest_priority(db, c.id)
    return {
        "priority_score": float(c.priority_score) if c.priority_score is not None else None,
        "priority_level": c.priority_level,
        "priority_assessment_status": c.priority_assessment_status,
        "needs_prompt_review": c.needs_prompt_review,
        "factors": (pa.factor_evidence.get("factors") if pa else None),
        "weights": (pa.factor_evidence.get("weights") if pa else None),
        "review_reasons": (pa.factor_evidence.get("review_reasons") if pa else []),
        "rubric_version": pa.rubric_version if pa else None,
        "assessed_by": ("Authorized staff" if pa and pa.assessed_by.startswith("user:") else "Priority engine") if pa else None,
        "assessed_at": pa.created_at if pa else None,
        "disclaimer": "Internal prototype prioritization heuristic, not an official government urgency standard.",
    }


def routing_view(db: Session, c: Complaint, staff: bool) -> dict:
    from app.routing.engine import MESSAGES
    rd = latest_routing_decision(db, c.id)
    out = {
        "routing_status": c.routing_status,
        "department": dept_out(c.department),
        "message": MESSAGES.get(rd.reason_code, MESSAGES[c.routing_status.value]) if rd else None,
        "explanation": rd.explanation if rd else None,
        "requires_admin_review": c.routing_status.value == "PENDING_REVIEW",
        "decided_at": rd.decided_at if rd else None,
    }
    if staff and rd:
        out.update({"reason_code": rd.reason_code, "rule_version": rd.rule_version, "candidates": rd.candidates,
                    "jurisdiction": ({"id": c.jurisdiction.id, "name": c.jurisdiction.name, "is_prototype": c.jurisdiction.is_prototype}
                                     if c.jurisdiction else None),
                    "manually_reviewed": rd.reviewed_by is not None})
    return out


def ai_view(db: Session, c: Complaint) -> dict | None:
    if not c.ai_analysis_id:
        return None
    a = db.get(AIAnalysis, c.ai_analysis_id)
    return {
        "analysis_id": a.id,
        "model_identifier": a.model_identifier,
        "model_version": a.model_version,
        "summary": a.summary,
        "suggested_category": a.suggested_category,
        "classification_confidence": a.confidence,
        "confidence_band": a.confidence_band,
        "confidence_method": a.confidence_method,
        "requires_human_review": a.review_required,
        "structured_output": a.structured_output,
        "created_at": a.created_at,
        "notice": "AI output is a suggestion and was reviewed by the citizen before submission.",
    }


def complaint_detail(db: Session, actor: Actor, c: Complaint) -> dict:
    staff = actor.is_staff
    history = db.scalars(select(StatusHistory).where(StatusHistory.complaint_id == c.id).order_by(StatusHistory.created_at)).all()
    remark_q = select(ComplaintRemark).where(ComplaintRemark.complaint_id == c.id)
    if not staff:
        remark_q = remark_q.where(ComplaintRemark.visibility == RemarkVisibility.CITIZEN)
    remarks = db.scalars(remark_q.order_by(ComplaintRemark.created_at)).all()
    evidence_q = select(ResolutionEvidence).where(ResolutionEvidence.complaint_id == c.id)
    if not staff:
        evidence_q = evidence_q.where(ResolutionEvidence.citizen_visible.is_(True))
    evidence = db.scalars(evidence_q.order_by(ResolutionEvidence.created_at)).all()
    feedback = db.scalars(select(CitizenFeedback).where(CitizenFeedback.complaint_id == c.id).order_by(CitizenFeedback.created_at)).all()
    verifications = db.scalars(select(VerificationDecision).where(VerificationDecision.complaint_id == c.id)
                               .order_by(VerificationDecision.created_at)).all()
    a = active_assignment(db, c.id)

    timeline = [
        {"type": "STATUS", "previous_status": h.previous_status, "new_status": h.new_status,
         "actor_role": ROLE_LABEL[h.actor_role] if h.actor_role else "CivicConnect (automatic)", "remarks": h.remarks,
         "created_at": h.created_at}
        for h in history
    ] + [
        {"type": r.kind, "visibility": r.visibility, "actor_role": ROLE_LABEL[r.author_role], "remarks": r.text,
         "created_at": r.created_at, **({"author_name": db.get(User, r.author_id).full_name} if staff and r.author_role != Role.CITIZEN else {})}
        for r in remarks
    ]
    timeline.sort(key=lambda e: e["created_at"])

    complaint_media = [m for m in c.media if m.purpose == MediaPurpose.COMPLAINT]
    out = {
        **list_item(db, c, staff),
        "original_description": c.original_description,
        "description": c.citizen_confirmed_description,
        "occurred_at": c.occurred_at,
        "additional_details": c.additional_details,
        "location": {"latitude": c.latitude, "longitude": c.longitude, "accuracy_meters": c.accuracy_meters,
                     "landmark": c.landmark, "address_text": c.address_text, "location_source": c.location_source},
        "citizen_observations": {"observed_severity": c.citizen_severity, "safety_risk": c.citizen_safety_risk,
                                 "public_exposure": c.citizen_exposure},
        "media": [media_out(m) for m in complaint_media],
        "priority": priority_view(db, c),
        "routing": routing_view(db, c, staff),
        "timeline": timeline,
        "resolution_evidence": [
            {"evidence_id": e.id, "description": e.description, "created_at": e.created_at, "media": media_out(e.media)}
            for e in evidence
        ],
        "verification_decisions": [
            {"decision": v.decision, "reason": v.reason, "created_at": v.created_at,
             "citizen_responded": v.citizen_feedback_snapshot.get("citizen_responded"),
             **({"verifier_id": v.verifier_id, "evidence_reviewed": v.evidence_reviewed} if staff else {})}
            for v in verifications
        ],
        "feedback": [
            {"feedback_id": f.id, "complaint_id": f.complaint_id, "feedback_type": f.feedback_type, "remarks": f.remarks,
             "review_status": f.review_status, "reviewed_by": f.reviewed_by if staff else None,
             "reviewed_at": f.reviewed_at, "decision_reason": f.decision_reason, "created_at": f.created_at}
            for f in feedback
        ],
        "ai_analysis": ai_view(db, c),
        "ai_review_required": c.ai_review_required,
        "allow_public_display": c.allow_public_display,
        "publication_status": c.publication_status,
        "public_summary": c.public_summary,
        "related": related_view(db, actor, c),
        "external_reference": None,  # no authorized government integration exists (spec 9.E)
        "workflow_notice": "This is an internal CivicConnect workflow. It has not been submitted to any government portal.",
    }
    if staff:
        out["permitted_actions"] = permitted_actions(db, actor, c, a)
        out["escalations"] = [escalation_dict(e) for e in db.scalars(
            select(Escalation).where(Escalation.complaint_id == c.id).order_by(Escalation.created_at))]
        out["jurisdiction_path"] = jurisdiction_path(db, c.jurisdiction_id)
        out["due_at"] = c.due_at
        out["overdue"] = _overdue(c)
        out["unit"] = ({"id": c.department_unit.id, "department": c.department_unit.department.name,
                        "jurisdiction": c.department_unit.jurisdiction.name} if c.department_unit else None)
        out["assignments"] = [
            {"officer": officer_out(db, x.officer, True), "assigned_by": x.assigned_by,
             "assigned_by_name": (db.get(User, x.assigned_by).full_name if x.assigned_by else "Routing engine (automatic)"),
             "automatic": x.automatic, "reason": x.reason, "accepted_at": x.accepted_at,
             "assigned_at": x.assigned_at, "assignment_status": x.assignment_status}
            for x in db.scalars(select(Assignment).where(Assignment.complaint_id == c.id).order_by(Assignment.assigned_at))
        ]
        out["routing_history"] = [
            {"routing_status": r.routing_status, "reason_code": r.reason_code, "explanation": r.explanation,
             "department_id": r.department_id, "unit_id": r.department_unit_id, "officer_id": r.officer_id,
             "rule_version": r.rule_version, "decided_at": r.decided_at,
             "reviewed_by": r.reviewed_by}
            for r in db.scalars(select(RoutingDecision).where(RoutingDecision.complaint_id == c.id).order_by(RoutingDecision.decided_at))
        ]
    else:
        out["citizen_actions"] = {
            "can_edit": c.status == S.SUBMITTED,
            "can_confirm_resolution": c.status in (S.RESOLVED_AWAITING_VERIFICATION, S.VERIFIED_RESOLVED),
            "can_request_reopen": c.status in (S.RESOLVED_AWAITING_VERIFICATION, S.VERIFIED_RESOLVED)
            and not any(f.review_status.value == "PENDING" for f in feedback),
        }
    return out


def permitted_actions(db: Session, actor: Actor, c: Complaint, a: Assignment | None) -> dict:
    targets = [t for t in allowed_targets(c.status) if t not in (S.ASSIGNED, S.VERIFIED_RESOLVED, S.REOPENED)]
    has_evidence = db.scalar(select(ResolutionEvidence.id).where(ResolutionEvidence.complaint_id == c.id).limit(1)) is not None
    return {
        "status_targets": [t.value for t in targets],
        "can_assign": actor.role != Role.OFFICER and c.department_unit_id is not None
        and c.status in (S.SUBMITTED, S.UNDER_REVIEW, S.REOPENED) and a is None,
        "can_reassign": actor.role != Role.OFFICER and c.status in (S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD),
        "can_accept": a is not None and a.officer_id == actor.officer_id and a.accepted_at is None,
        "can_escalate": c.status in (S.SUBMITTED, S.UNDER_REVIEW, S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.REOPENED)
        and actor.role != Role.SYSTEM_ADMIN,
        "can_upload_evidence": c.status in (S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.RESOLVED_AWAITING_VERIFICATION, S.REOPENED),
        "has_evidence": has_evidence,
        "can_verify": c.status == S.RESOLVED_AWAITING_VERIFICATION and can_verify(actor, c),
        "can_decide_reopening": can_decide_reopening(actor, c),
        "requires_reason": ["REJECTED", "ON_HOLD", "REASSIGN"],
    }


def related_view(db: Session, actor: Actor, c: Complaint) -> list[dict]:
    rels = db.scalars(select(ComplaintRelationship).where(
        or_(ComplaintRelationship.source_complaint_id == c.id, ComplaintRelationship.related_complaint_id == c.id)
    )).all()
    out = []
    for r in rels:
        other_id = r.related_complaint_id if r.source_complaint_id == c.id else r.source_complaint_id
        other = db.get(Complaint, other_id)
        if actor.is_staff:
            out.append({
                "complaint_id": other.id, "reference_id": other.reference_id, "title": other.title,
                "category": other.category, "status": other.status, "similarity_score": r.similarity_score,
                "distance_m": r.distance_m, "text_similarity": r.text_similarity,
                "text_similarity_method": r.text_similarity_method, "match_reasons": r.match_reasons,
                "relationship_status": r.relationship_status, "reviewed_at": r.reviewed_at,
                "in_scope": other.department_unit_id == c.department_unit_id,
            })
        elif r.relationship_status == RelationshipStatus.CONFIRMED_RELATED and is_public(other):
            # Citizens see reviewed relationships, and only privacy-filtered public data.
            out.append({"public_reference": other.reference_id, "category": other.category,
                        "public_summary": other.public_summary, "public_status": PUBLIC_STATUS_LABEL[other.status]})
    return out


# ---------------- public ----------------
def is_public(c: Complaint) -> bool:
    return (
        c.publication_status == PublicationStatus.APPROVED
        and c.allow_public_display
        and not c.flagged_misuse
        and c.status in PUBLIC_STATUSES
        and bool(c.public_summary)
    )


def approximate(value: float) -> float:
    return round(value, get_settings().PUBLIC_LOCATION_DECIMALS)


def filter_public_complaint(c: Complaint, latest_update: dict | None = None) -> dict:
    """Privacy filter (spec L12, 9.B). Only whitelisted, non-personal fields leave this function."""
    return {
        "public_reference": c.reference_id,
        "category": c.category.value,
        "public_summary": c.public_summary,
        "status": c.status.value,
        "public_status": PUBLIC_STATUS_LABEL.get(c.status, "Not public"),
        "resolution_type": (
            "VERIFIED" if c.status == S.VERIFIED_RESOLVED
            else "AUTHORITY_REPORTED" if c.status == S.RESOLVED_AWAITING_VERIFICATION
            else None
        ),
        "generalized_location": {
            "latitude": approximate(c.latitude),
            "longitude": approximate(c.longitude),
            "area": c.jurisdiction.name if c.jurisdiction else None,
            "approximation": f"rounded to {get_settings().PUBLIC_LOCATION_DECIMALS} decimal places",
        },
        "department": c.department.name if c.department else None,
        "reported_on": c.created_at.date().isoformat(),
        "latest_public_update": latest_update,
    }
