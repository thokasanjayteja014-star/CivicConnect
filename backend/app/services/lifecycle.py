"""Complaint state machine (spec L9). Pure functions, no I/O."""
from app.models.enums import ComplaintStatus as S

PERMITTED_TRANSITIONS: dict[S, set[S]] = {
    S.SUBMITTED: {S.UNDER_REVIEW},
    S.UNDER_REVIEW: {S.ASSIGNED, S.REJECTED},
    S.ASSIGNED: {S.IN_PROGRESS, S.ON_HOLD, S.REJECTED},
    S.IN_PROGRESS: {S.ON_HOLD, S.RESOLVED_AWAITING_VERIFICATION},
    S.ON_HOLD: {S.IN_PROGRESS, S.REJECTED},
    S.RESOLVED_AWAITING_VERIFICATION: {S.VERIFIED_RESOLVED, S.REOPENED},
    S.VERIFIED_RESOLVED: {S.REOPENED},
    S.REJECTED: set(),
    S.REOPENED: {S.UNDER_REVIEW, S.ASSIGNED},
}

# Targets that require a reason (L9.4). Reassignment is handled by the
# assignment workflow and also requires a reason.
REASON_REQUIRED = {S.REJECTED, S.ON_HOLD}

# Targets that may only be reached through a dedicated workflow, never the
# generic status endpoint.
WORKFLOW_ONLY = {
    S.ASSIGNED: "assignment",           # needs an eligible officer
    S.VERIFIED_RESOLVED: "verification",  # needs VERIFY_RESOLUTION + evidence
    S.REOPENED: "reopening review",     # needs accepted reopening review or verifier rejection
}

# Statuses in which an officer assignment can be changed without a status change.
REASSIGNABLE = {S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD}


def validate_status_transition(current: S, target: S) -> bool:
    return target in PERMITTED_TRANSITIONS.get(current, set())


def allowed_targets(current: S) -> list[S]:
    return sorted(PERMITTED_TRANSITIONS.get(current, set()), key=lambda s: s.value)
