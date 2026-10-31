import enum


class Role(str, enum.Enum):
    CITIZEN = "CITIZEN"
    OFFICER = "OFFICER"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    PENDING = "PENDING"


class Category(str, enum.Enum):
    ROAD_INFRASTRUCTURE = "ROAD_INFRASTRUCTURE"
    WATER_SUPPLY = "WATER_SUPPLY"
    SANITATION = "SANITATION"
    DRAINAGE = "DRAINAGE"
    STREETLIGHT = "STREETLIGHT"
    PUBLIC_INFRASTRUCTURE = "PUBLIC_INFRASTRUCTURE"
    OTHER = "OTHER"


class ComplaintStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    RESOLVED_AWAITING_VERIFICATION = "RESOLVED_AWAITING_VERIFICATION"
    VERIFIED_RESOLVED = "VERIFIED_RESOLVED"
    REJECTED = "REJECTED"
    REOPENED = "REOPENED"


class PriorityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssessmentStatus(str, enum.Enum):
    FINAL = "FINAL"
    PROVISIONAL = "PROVISIONAL"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class RoutingStatus(str, enum.Enum):
    ROUTED = "ROUTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    UNROUTED = "UNROUTED"


class LocationSource(str, enum.Enum):
    GPS = "GPS"
    MAP_SELECTION = "MAP_SELECTION"
    MANUAL_ENTRY = "MANUAL_ENTRY"


class MediaType(str, enum.Enum):
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"


class MediaPurpose(str, enum.Enum):
    COMPLAINT = "COMPLAINT"
    RESOLUTION_EVIDENCE = "RESOLUTION_EVIDENCE"


class ConfidenceBand(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNAVAILABLE = "UNAVAILABLE"


class RelationshipStatus(str, enum.Enum):
    SUGGESTED = "SUGGESTED"
    CONFIRMED_RELATED = "CONFIRMED_RELATED"
    NOT_RELATED = "NOT_RELATED"


class AssignmentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CLOSED = "CLOSED"


class FeedbackType(str, enum.Enum):
    CONFIRMED_RESOLVED = "CONFIRMED_RESOLVED"
    NOT_RESOLVED = "NOT_RESOLVED"
    REOPEN_REQUEST = "REOPEN_REQUEST"


class ReviewStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class RemarkVisibility(str, enum.Enum):
    INTERNAL = "INTERNAL"
    CITIZEN = "CITIZEN"


class PublicationStatus(str, enum.Enum):
    NOT_REVIEWED = "NOT_REVIEWED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class VerificationDecisionType(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Permission(str, enum.Enum):
    VERIFY_RESOLUTION = "VERIFY_RESOLUTION"
    DECIDE_REOPENING = "DECIDE_REOPENING"


class CitizenSeverity(str, enum.Enum):
    """Citizen-observed physical severity (maps to rubric S bands)."""
    MINOR = "MINOR"
    MODERATE = "MODERATE"
    SUBSTANTIAL = "SUBSTANTIAL"
    SEVERE = "SEVERE"


class CitizenSafetyRisk(str, enum.Enum):
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    SIGNIFICANT = "SIGNIFICANT"
    IMMEDIATE = "IMMEDIATE"


class CitizenExposure(str, enum.Enum):
    """Citizen-described extent of who is affected (maps to rubric E bands)."""
    INDIVIDUAL = "INDIVIDUAL"
    FEW_HOUSEHOLDS = "FEW_HOUSEHOLDS"
    STREET = "STREET"
    NEIGHBOURHOOD = "NEIGHBOURHOOD"
    WIDE_AREA = "WIDE_AREA"
