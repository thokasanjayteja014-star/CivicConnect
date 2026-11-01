"""Authority workflow, verification and reopening policy (spec L9-L11)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.core.environment import storage_prefix
from app.core.errors import err
from app.models import (
    Assignment,
    CitizenFeedback,
    Complaint,
    ComplaintRelationship,
    ComplaintRemark,
    Media,
    Officer,
    ResolutionEvidence,
    StatusHistory,
    VerificationDecision,
)
from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus as S,
    FeedbackType,
    MediaPurpose,
    Permission,
    RelationshipStatus,
    RemarkVisibility,
    ReviewStatus,
    Role,
    VerificationDecisionType,
)
from app.notifications import notify, notify_status_change
from app.security.permissions import Actor, has_permission, in_department_scope, require_permission
from app.services.lifecycle import REASON_REQUIRED, REASSIGNABLE, WORKFLOW_ONLY, validate_status_transition
from app.services.media import validate_upload
from app.services.storage import StorageError, get_storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lock_for_staff(db: Session, actor: Actor, complaint_id: uuid.UUID, expected_version: int | None) -> Complaint:
    complaint = db.scalar(select(Complaint).where(Complaint.id == complaint_id).with_for_update())
    if complaint is None:
        raise err("COMPLAINT_NOT_FOUND")
    if not in_department_scope(actor, complaint, db):
        # Department users never learn about complaints outside their scope.
        raise err("COMPLAINT_NOT_FOUND")
    if expected_version is not None and expected_version != complaint.version:
        raise err("CONCURRENT_UPDATE", details={"current_version": complaint.version})
    return complaint


def _record_transition(db: Session, complaint: Complaint, actor: Actor, target: S, remarks: str | None) -> StatusHistory:
    if complaint.status == target:
        raise err("ALREADY_UPDATED", details={"current_status": complaint.status.value})
    if not validate_status_transition(complaint.status, target):
        raise err("INVALID_STATUS_TRANSITION", details={"current_status": complaint.status.value, "requested": target.value})
    hist = StatusHistory(
        complaint_id=complaint.id,
        previous_status=complaint.status,
        new_status=target,
        actor_id=actor.user_id,
        actor_role=actor.role,
        remarks=remarks,
    )
    db.add(hist)
    previous = complaint.status
    complaint.status = target
    complaint.version += 1
    complaint.updated_at = _now()
    db.flush()
    audit.record(
        db, actor_id=actor.user_id, action="STATUS_CHANGED", entity_type="complaint", entity_id=complaint.id,
        details={"from": previous, "to": target, "remarks": remarks},
    )
    notify_status_change(db, complaint, target, hist.id)
    return hist


def change_status(
    db: Session, actor: Actor, complaint_id: uuid.UUID, target: S, *, remarks: str | None,
    internal_note: str | None, reason: str | None, expected_version: int | None,
) -> Complaint:
    complaint = lock_for_staff(db, actor, complaint_id, expected_version)
    if target in WORKFLOW_ONLY:
        raise err("INVALID_STATUS_TRANSITION",
                  message=f"Use the {WORKFLOW_ONLY[target]} workflow to move a complaint to {target.value}.",
                  details={"current_status": complaint.status.value})
    if complaint.status == target:
        raise err("ALREADY_UPDATED", details={"current_status": complaint.status.value})
    if not validate_status_transition(complaint.status, target):
        raise err("INVALID_STATUS_TRANSITION", details={"current_status": complaint.status.value, "requested": target.value})
    reason = (reason or "").strip() or None
    if target in REASON_REQUIRED and not reason:
        raise err("REASON_REQUIRED", details={"field": "reason"})
    if target == S.RESOLVED_AWAITING_VERIFICATION:
        has_evidence = db.scalar(select(ResolutionEvidence.id).where(ResolutionEvidence.complaint_id == complaint.id).limit(1))
        if not has_evidence:
            raise err("EVIDENCE_REQUIRED")
    visible = " ".join(x for x in [f"Reason: {reason}" if reason else None, (remarks or "").strip() or None] if x) or None
    _record_transition(db, complaint, actor, target, visible)
    if internal_note and internal_note.strip():
        _add_remark(db, complaint, actor, internal_note.strip(), RemarkVisibility.INTERNAL)
    if target in (S.REJECTED,):
        _close_active_assignment(db, complaint)
    if target == S.IN_PROGRESS and actor.officer_id:
        # Starting work on an assignment counts as accepting it.
        active = db.scalar(select(Assignment).where(Assignment.complaint_id == complaint.id,
                                                    Assignment.assignment_status == AssignmentStatus.ACTIVE))
        if active and active.officer_id == actor.officer_id and active.accepted_at is None:
            active.accepted_at = _now()
    if target in (S.REJECTED, S.RESOLVED_AWAITING_VERIFICATION):
        from app.services.escalation import close_escalations_for
        close_escalations_for(db, complaint.id, actor.user_id, f"Complaint moved to {target.value}.")
    if target == S.REJECTED:
        # A rejected report no longer counts towards the priority of the complaints linked to it.
        _refresh_linked_priority(db, complaint.id)
    db.commit()
    return complaint


def _refresh_linked_priority(db: Session, *complaint_ids: uuid.UUID) -> None:
    from app.services.complaints import refresh_community_priority
    ids = set(complaint_ids)
    for a, b in db.execute(select(ComplaintRelationship.source_complaint_id, ComplaintRelationship.related_complaint_id).where(
            ComplaintRelationship.source_complaint_id.in_(ids) | ComplaintRelationship.related_complaint_id.in_(ids))).all():
        ids.update((a, b))
    refresh_community_priority(db, ids)


def _close_active_assignment(db: Session, complaint: Complaint) -> None:
    for a in db.scalars(select(Assignment).where(Assignment.complaint_id == complaint.id, Assignment.assignment_status == AssignmentStatus.ACTIVE)):
        a.assignment_status = AssignmentStatus.CLOSED


def assign_officer(
    db: Session, actor: Actor, complaint_id: uuid.UUID, officer_id: uuid.UUID, reason: str | None, expected_version: int | None
) -> Complaint:
    complaint = lock_for_staff(db, actor, complaint_id, expected_version)
    officer = db.get(Officer, officer_id)
    if (
        officer is None
        or not officer.active
        or officer.unit_id is None
        or officer.unit_id != complaint.department_unit_id
        or officer.user.role != Role.OFFICER
        or officer.user.account_status.value != "ACTIVE"
    ):
        raise err("INVALID_ASSIGNMENT")
    if actor.role == Role.OFFICER:
        raise err("FORBIDDEN", message="Only department administrators can assign complaints.")
    current = db.scalar(
        select(Assignment).where(Assignment.complaint_id == complaint.id, Assignment.assignment_status == AssignmentStatus.ACTIVE)
    )
    reason = (reason or "").strip() or None
    is_reassignment = complaint.status in REASSIGNABLE
    if is_reassignment:
        if not reason:
            raise err("REASON_REQUIRED", details={"field": "reason"})
        if current and current.officer_id == officer.id:
            raise err("ALREADY_UPDATED", message="The complaint is already assigned to this officer.")
    elif complaint.status not in (S.SUBMITTED, S.UNDER_REVIEW, S.REOPENED):
        raise err("INVALID_STATUS_TRANSITION", details={"current_status": complaint.status.value, "requested": "ASSIGNED"})
    if complaint.status == S.SUBMITTED:
        _record_transition(db, complaint, actor, S.UNDER_REVIEW, "Reviewed by the department.")

    if current:
        current.assignment_status = AssignmentStatus.SUPERSEDED
    assignment = Assignment(
        complaint_id=complaint.id,
        department_id=complaint.department_id,
        department_unit_id=complaint.department_unit_id,
        officer_id=officer.id,
        assigned_by=actor.user_id,
        reason=reason,
    )
    db.add(assignment)
    db.flush()
    if is_reassignment:
        complaint.version += 1
        complaint.updated_at = _now()
        audit.record(db, actor_id=actor.user_id, action="COMPLAINT_REASSIGNED", entity_type="complaint",
                     entity_id=complaint.id, details={"officer_id": officer.id, "reason": reason,
                                                      "previous_officer_id": current.officer_id if current else None})
        _add_remark(db, complaint, actor, f"Complaint reassigned to another officer. Reason: {reason}", RemarkVisibility.CITIZEN)
    else:
        _record_transition(db, complaint, actor, S.ASSIGNED, "Assigned to a department officer.")
        audit.record(db, actor_id=actor.user_id, action="COMPLAINT_ASSIGNED", entity_type="complaint",
                     entity_id=complaint.id, details={"officer_id": officer.id})
    notify(
        db, recipient_id=officer.user_id, complaint_id=complaint.id, notification_type="ASSIGNED_TO_YOU",
        message=f"Complaint {complaint.reference_id} has been assigned to you.", event_key=f"assignment:{assignment.id}",
    )
    db.commit()
    return complaint


def _add_remark(db: Session, complaint: Complaint, actor: Actor, text: str, visibility: RemarkVisibility, kind: str = "REMARK") -> ComplaintRemark:
    remark = ComplaintRemark(
        complaint_id=complaint.id, author_id=actor.user_id, author_role=actor.role,
        visibility=visibility, text=text, kind=kind,
    )
    db.add(remark)
    db.flush()
    return remark


def add_staff_remark(db: Session, actor: Actor, complaint_id: uuid.UUID, text: str, visibility: RemarkVisibility, clarification: bool = False) -> ComplaintRemark:
    complaint = lock_for_staff(db, actor, complaint_id, None)
    kind = "CLARIFICATION_REQUEST" if clarification else "REMARK"
    if clarification:
        visibility = RemarkVisibility.CITIZEN
    remark = _add_remark(db, complaint, actor, text.strip(), visibility, kind)
    audit.record(db, actor_id=actor.user_id, action="REMARK_ADDED", entity_type="complaint", entity_id=complaint.id,
                 details={"visibility": visibility, "kind": kind, "remark_id": remark.id})
    if visibility == RemarkVisibility.CITIZEN:
        notify(db, recipient_id=complaint.citizen_id, complaint_id=complaint.id,
               notification_type="CLARIFICATION_REQUESTED" if clarification else "AUTHORITY_UPDATE",
               message=(f"The department requested more information on {complaint.reference_id}." if clarification
                        else f"New update from the department on {complaint.reference_id}."),
               event_key=f"remark:{remark.id}")
    db.commit()
    return remark


def add_citizen_reply(db: Session, actor: Actor, complaint: Complaint, text: str) -> ComplaintRemark:
    if complaint.status in (S.REJECTED,):
        raise err("CONFLICT", message="This complaint is closed and cannot receive new replies.")
    remark = _add_remark(db, complaint, actor, text.strip(), RemarkVisibility.CITIZEN, "CITIZEN_REPLY")
    audit.record(db, actor_id=actor.user_id, action="CITIZEN_REPLY_ADDED", entity_type="complaint", entity_id=complaint.id)
    db.commit()
    return remark


def upload_evidence(db: Session, actor: Actor, complaint_id: uuid.UUID, data: bytes, filename: str | None, description: str | None) -> ResolutionEvidence:
    complaint = lock_for_staff(db, actor, complaint_id, None)
    if complaint.status not in (S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.RESOLVED_AWAITING_VERIFICATION, S.REOPENED):
        raise err("INVALID_STATUS_TRANSITION", message="Resolution evidence can only be added while work is assigned or in progress.",
                  details={"current_status": complaint.status.value})
    v = validate_upload(data)
    key = f"{storage_prefix()}evidence/{complaint.id}/{uuid.uuid4()}.{v.extension}"
    try:
        get_storage().put(key, v.data, v.mime_type)
    except StorageError:
        raise err("MEDIA_STORAGE_FAILURE")
    media = Media(
        complaint_id=complaint.id, uploaded_by=actor.user_id, purpose=MediaPurpose.RESOLUTION_EVIDENCE,
        media_type=v.media_type, storage_key=key, original_filename=(filename or "")[:255] or None,
        mime_type=v.mime_type, file_size_bytes=v.size, duration_seconds=v.duration_seconds, sha256=v.sha256,
    )
    db.add(media)
    db.flush()
    ev = ResolutionEvidence(complaint_id=complaint.id, uploaded_by=actor.user_id, media_id=media.id,
                            description=(description or "").strip() or None)
    db.add(ev)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="EVIDENCE_UPLOADED", entity_type="complaint", entity_id=complaint.id,
                 details={"evidence_id": ev.id, "media_id": media.id, "sha256": v.sha256})
    db.commit()
    return ev


def verify_resolution(
    db: Session, actor: Actor, complaint_id: uuid.UUID, decision: VerificationDecisionType, reason: str,
    evidence_reviewed: list[uuid.UUID], expected_version: int | None,
) -> Complaint:
    complaint = lock_for_staff(db, actor, complaint_id, expected_version)
    require_permission(actor, Permission.VERIFY_RESOLUTION, complaint, db)
    if complaint.status != S.RESOLVED_AWAITING_VERIFICATION:
        raise err("INVALID_STATUS_TRANSITION", details={"current_status": complaint.status.value})
    evidence = db.scalars(select(ResolutionEvidence).where(ResolutionEvidence.complaint_id == complaint.id)).all()
    ids = {e.id for e in evidence}
    if not evidence:
        raise err("EVIDENCE_REQUIRED")
    if not set(evidence_reviewed) <= ids:
        raise err("VALIDATION_ERROR", message="Reviewed evidence must belong to this complaint.", details={"field": "evidence_reviewed"})
    feedback = db.scalars(select(CitizenFeedback).where(CitizenFeedback.complaint_id == complaint.id)).all()
    pending = [f for f in feedback if f.review_status == ReviewStatus.PENDING]
    if decision == VerificationDecisionType.APPROVED and pending:
        raise err("CONFLICT", message="A pending reopening request must be decided before verification can be approved.")
    snapshot = {
        "citizen_responded": bool(feedback),
        "feedback": [{"id": str(f.id), "type": f.feedback_type.value, "review_status": f.review_status.value} for f in feedback],
    }
    vd = VerificationDecision(
        complaint_id=complaint.id, verifier_id=actor.user_id, decision=decision, reason=reason.strip(),
        evidence_reviewed=[str(e) for e in evidence_reviewed], citizen_feedback_snapshot=snapshot,
    )
    db.add(vd)
    db.flush()
    target = S.VERIFIED_RESOLVED if decision == VerificationDecisionType.APPROVED else S.REOPENED
    _record_transition(db, complaint, actor, target, f"Verification {decision.value.lower()}: {reason.strip()}")
    audit.record(db, actor_id=actor.user_id, action="RESOLUTION_VERIFICATION", entity_type="complaint", entity_id=complaint.id,
                 details={"decision": decision, "reason": reason, "evidence_reviewed": evidence_reviewed,
                          "citizen_responded": snapshot["citizen_responded"]})
    db.commit()
    return complaint


def submit_feedback(db: Session, actor: Actor, complaint: Complaint, feedback_type: FeedbackType, remarks: str | None) -> CitizenFeedback:
    if complaint.citizen_id != actor.user_id:
        raise err("REOPEN_NOT_ALLOWED", status_code=403)
    eligible = {S.RESOLVED_AWAITING_VERIFICATION, S.VERIFIED_RESOLVED}
    if feedback_type == FeedbackType.CONFIRMED_RESOLVED:
        eligible = {S.RESOLVED_AWAITING_VERIFICATION, S.VERIFIED_RESOLVED}
    if complaint.status not in eligible:
        raise err("REOPEN_NOT_ALLOWED", details={"current_status": complaint.status.value})
    needs_review = feedback_type in (FeedbackType.NOT_RESOLVED, FeedbackType.REOPEN_REQUEST)
    if needs_review:
        pending = db.scalar(select(CitizenFeedback.id).where(
            CitizenFeedback.complaint_id == complaint.id, CitizenFeedback.review_status == ReviewStatus.PENDING))
        if pending:
            raise err("CONFLICT", message="A reopening request for this complaint is already awaiting review.")
        if not (remarks or "").strip():
            raise err("REASON_REQUIRED", message="Please describe why the issue is not resolved.", details={"field": "remarks"})
    fb = CitizenFeedback(
        complaint_id=complaint.id, citizen_id=actor.user_id, feedback_type=feedback_type,
        remarks=(remarks or "").strip() or None, status_at_submission=complaint.status,
        review_status=ReviewStatus.PENDING if needs_review else ReviewStatus.NOT_REQUIRED,
    )
    db.add(fb)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="CITIZEN_FEEDBACK", entity_type="complaint", entity_id=complaint.id,
                 details={"feedback_id": fb.id, "type": feedback_type, "review_status": fb.review_status})
    if needs_review and complaint.department_id:
        from app.notifications import unit_staff_ids
        for uid in unit_staff_ids(db, complaint.department_unit_id, {Role.DEPARTMENT_ADMIN}):
            notify(db, recipient_id=uid, complaint_id=complaint.id, notification_type="REOPEN_REVIEW_PENDING",
                   message=f"Citizen requested reopening of {complaint.reference_id}; review required.",
                   event_key=f"feedback:{fb.id}")
    db.commit()
    return fb


def review_feedback(db: Session, actor: Actor, feedback_id: uuid.UUID, decision: ReviewStatus, reason: str) -> CitizenFeedback:
    if decision not in (ReviewStatus.ACCEPTED, ReviewStatus.REJECTED):
        raise err("VALIDATION_ERROR", message="Decision must be ACCEPTED or REJECTED.", details={"field": "decision"})
    fb = db.scalar(select(CitizenFeedback).where(CitizenFeedback.id == feedback_id).with_for_update())
    if fb is None:
        raise err("NOT_FOUND")
    complaint = lock_for_staff(db, actor, fb.complaint_id, None)
    require_permission(actor, Permission.DECIDE_REOPENING, complaint, db)
    if fb.review_status != ReviewStatus.PENDING:
        raise err("ALREADY_UPDATED", message="This reopening request has already been decided.")
    if decision == ReviewStatus.ACCEPTED:
        if complaint.status not in (S.RESOLVED_AWAITING_VERIFICATION, S.VERIFIED_RESOLVED):
            raise err("REOPEN_NOT_ALLOWED", details={"current_status": complaint.status.value})
        _record_transition(db, complaint, actor, S.REOPENED, f"Reopening request accepted: {reason.strip()}")
    fb.review_status = decision
    fb.reviewed_by = actor.user_id
    fb.reviewed_at = _now()
    fb.decision_reason = reason.strip()
    audit.record(db, actor_id=actor.user_id, action="REOPEN_REVIEW_DECISION", entity_type="complaint", entity_id=complaint.id,
                 details={"feedback_id": fb.id, "decision": decision, "reason": reason})
    if decision == ReviewStatus.REJECTED:
        notify(db, recipient_id=complaint.citizen_id, complaint_id=complaint.id, notification_type="REOPEN_REJECTED",
               message=f"Your reopening request for {complaint.reference_id} was not accepted. Reason: {reason.strip()}",
               event_key=f"feedback-decision:{fb.id}")
    db.commit()
    return fb


def decide_relationship(db: Session, actor: Actor, complaint_id: uuid.UUID, related_id: uuid.UUID, status: RelationshipStatus) -> ComplaintRelationship:
    if status == RelationshipStatus.SUGGESTED:
        raise err("VALIDATION_ERROR", message="Choose CONFIRMED_RELATED or NOT_RELATED.")
    complaint = lock_for_staff(db, actor, complaint_id, None)
    rel = db.scalar(select(ComplaintRelationship).where(
        ((ComplaintRelationship.source_complaint_id == complaint.id) & (ComplaintRelationship.related_complaint_id == related_id))
        | ((ComplaintRelationship.source_complaint_id == related_id) & (ComplaintRelationship.related_complaint_id == complaint.id))
    ))
    if rel is None:
        other = db.get(Complaint, related_id)
        if other is None or not in_department_scope(actor, other, db):
            raise err("NOT_FOUND")
        rel = ComplaintRelationship(source_complaint_id=complaint.id, related_complaint_id=related_id, similarity_score=0.0,
                                    match_reasons=["Manually linked by reviewer"])
        db.add(rel)
    rel.relationship_status = status
    rel.reviewed_by = actor.user_id
    rel.reviewed_at = _now()
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="RELATIONSHIP_DECISION", entity_type="complaint", entity_id=complaint.id,
                 details={"related_complaint_id": related_id, "status": status})
    _refresh_linked_priority(db, complaint.id, related_id)
    db.commit()
    return rel


def set_publication(db: Session, actor: Actor, complaint_id: uuid.UUID, approve: bool, public_summary: str | None) -> Complaint:
    from app.models.enums import PublicationStatus
    complaint = lock_for_staff(db, actor, complaint_id, None)
    if approve:
        if not complaint.allow_public_display:
            raise err("CONFLICT", message="The citizen did not allow public display of this complaint.")
        if not public_summary:
            raise err("VALIDATION_ERROR", message="A privacy-reviewed public summary is required.", details={"field": "public_summary"})
        complaint.public_summary = public_summary.strip()
        complaint.publication_status = PublicationStatus.APPROVED
    else:
        complaint.publication_status = PublicationStatus.DENIED
    audit.record(db, actor_id=actor.user_id, action="PUBLICATION_DECISION", entity_type="complaint", entity_id=complaint.id,
                 details={"approve": approve})
    db.commit()
    return complaint


def can_verify(actor: Actor, complaint: Complaint) -> bool:
    return has_permission(actor, Permission.VERIFY_RESOLUTION, complaint)


def can_decide_reopening(actor: Actor, complaint: Complaint) -> bool:
    return has_permission(actor, Permission.DECIDE_REOPENING, complaint)


# ---------------- automatic assignment (routing engine) ----------------
def _system_transition(db: Session, complaint: Complaint, target: S, remarks: str) -> StatusHistory:
    if not validate_status_transition(complaint.status, target):
        raise err("INVALID_STATUS_TRANSITION", details={"current_status": complaint.status.value, "requested": target.value})
    hist = StatusHistory(complaint_id=complaint.id, previous_status=complaint.status, new_status=target,
                         actor_id=None, actor_role=None, remarks=remarks)
    db.add(hist)
    previous = complaint.status
    complaint.status = target
    complaint.version += 1
    complaint.updated_at = _now()
    db.flush()
    audit.record(db, actor_id=None, actor_label="system:routing-engine", action="STATUS_CHANGED", entity_type="complaint",
                 entity_id=complaint.id, details={"from": previous, "to": target, "remarks": remarks})
    notify_status_change(db, complaint, target, hist.id)
    return hist


def auto_assign(db: Session, complaint: Complaint, officer_id: uuid.UUID, reason: str | None) -> bool:
    """Assign a freshly routed complaint to the officer chosen by the routing engine. No commit."""
    officer = db.get(Officer, officer_id)
    if officer is None or officer.unit_id != complaint.department_unit_id or complaint.status not in (S.SUBMITTED, S.REOPENED, S.UNDER_REVIEW):
        return False
    if complaint.status == S.SUBMITTED:
        _system_transition(db, complaint, S.UNDER_REVIEW, "Routed to the responsible department.")
    assignment = Assignment(complaint_id=complaint.id, department_id=complaint.department_id,
                            department_unit_id=complaint.department_unit_id, officer_id=officer.id,
                            assigned_by=None, automatic=True, reason=reason)
    db.add(assignment)
    db.flush()
    _system_transition(db, complaint, S.ASSIGNED, "Automatically assigned to the officer responsible for this area.")
    audit.record(db, actor_id=None, actor_label="system:routing-engine", action="COMPLAINT_ASSIGNED", entity_type="complaint",
                 entity_id=complaint.id, details={"officer_id": officer.id, "automatic": True, "reason": reason})
    notify(db, recipient_id=officer.user_id, complaint_id=complaint.id, notification_type="ASSIGNED_TO_YOU",
           message=f"Complaint {complaint.reference_id} has been assigned to you.", event_key=f"assignment:{assignment.id}")
    return True


def accept_assignment(db: Session, actor: Actor, complaint_id: uuid.UUID) -> Assignment:
    complaint = lock_for_staff(db, actor, complaint_id, None)
    a = db.scalar(select(Assignment).where(Assignment.complaint_id == complaint.id,
                                           Assignment.assignment_status == AssignmentStatus.ACTIVE))
    if a is None or actor.officer_id is None or a.officer_id != actor.officer_id:
        raise err("FORBIDDEN", message="Only the assigned officer can accept this complaint.")
    if a.accepted_at:
        raise err("ALREADY_UPDATED", message="You have already accepted this assignment.")
    a.accepted_at = _now()
    audit.record(db, actor_id=actor.user_id, action="ASSIGNMENT_ACCEPTED", entity_type="complaint", entity_id=complaint.id,
                 details={"assignment_id": a.id})
    _add_remark(db, complaint, actor, "The assigned officer has accepted the complaint.", RemarkVisibility.CITIZEN)
    db.commit()
    return a
