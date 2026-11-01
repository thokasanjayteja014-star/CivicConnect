"""Request/response schemas. Field-level contracts follow spec sections 5 and 7."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import (
    AccountStatus,
    AssessmentStatus,
    Category,
    CitizenExposure,
    CitizenSafetyRisk,
    CitizenSeverity,
    ComplaintStatus,
    ConfidenceBand,
    FeedbackType,
    LocationSource,
    MediaType,
    Permission,
    PriorityLevel,
    PublicationStatus,
    RelationshipStatus,
    RemarkVisibility,
    ReviewStatus,
    Role,
    RoutingStatus,
    VerificationDecisionType,
)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32, pattern=r"^[+0-9 ()-]{6,32}$")


LANGUAGES = ("en", "hi", "kn", "te")


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notify_email: bool | None = None
    notify_sms: bool | None = None
    notify_push: bool | None = None
    preferred_language: Literal["en", "hi", "kn", "te"] | None = None
    # E.164 format so SMS providers accept it, e.g. +919876543210. Empty string clears it.
    phone: str | None = Field(default=None, max_length=16, pattern=r"^(\+[1-9][0-9]{7,14})?$")


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://")
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    role: Role
    account_status: AccountStatus
    created_at: datetime


class MeOut(UserOut):
    notify_email: bool = True
    notify_sms: bool = False
    notify_push: bool = True
    preferred_language: str = "en"
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    officer_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    jurisdiction_name: str | None = None
    environment: str = "production"
    permissions: list[Permission] = []


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: MeOut


# ---------- complaint input ----------
class LocationIn(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    accuracy_meters: float | None = Field(default=None, ge=0)
    landmark: str | None = Field(default=None, max_length=200)
    address_text: str | None = Field(default=None, max_length=300)
    location_source: LocationSource


class AnalyzeRequest(BaseModel):
    description: str | None = None
    media_ids: list[uuid.UUID] = []
    category: Category | None = None
    location: LocationIn | None = None
    language_hint: str | None = Field(default=None, max_length=20)


class ComplaintCreate(BaseModel):
    title: str = Field(min_length=5, max_length=150)
    original_description: str | None = None
    description: str | None = Field(default=None, description="Citizen-confirmed description")
    category: Category
    location: LocationIn
    occurred_at: datetime | None = None
    additional_details: str | None = Field(default=None, max_length=2000)
    media_ids: list[uuid.UUID] = []
    analysis_id: uuid.UUID | None = None
    observed_severity: CitizenSeverity | None = None
    safety_risk: CitizenSafetyRisk | None = None
    public_exposure: CitizenExposure | None = None
    allow_public_display: bool = True
    confirmed: bool = Field(description="Citizen explicitly confirmed the reviewed details")


class ComplaintPatch(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=150)
    description: str | None = None
    landmark: str | None = Field(default=None, max_length=200)
    address_text: str | None = Field(default=None, max_length=300)
    additional_details: str | None = Field(default=None, max_length=2000)


# ---------- complaint output ----------
class ComplaintCreated(BaseModel):
    complaint_id: uuid.UUID
    reference_id: str
    status: ComplaintStatus
    priority_score: float | None
    priority_level: PriorityLevel | None
    priority_assessment_status: AssessmentStatus
    routing_status: RoutingStatus
    routing_message: str
    department: dict | None = None
    related_candidates: int = 0
    created_at: datetime


class MediaOut(BaseModel):
    media_id: uuid.UUID
    media_type: MediaType
    mime_type: str
    file_size_bytes: int
    duration_seconds: float | None
    original_filename: str | None
    uploaded_at: datetime


class ComplaintListItem(BaseModel):
    complaint_id: uuid.UUID
    reference_id: str
    title: str
    category: Category
    status: ComplaintStatus
    priority_score: float | None
    priority_level: PriorityLevel | None
    priority_assessment_status: AssessmentStatus
    needs_prompt_review: bool
    routing_status: RoutingStatus
    department: dict | None
    location: dict
    assigned_officer: dict | None = None
    created_at: datetime
    updated_at: datetime


class StatusChange(BaseModel):
    status: ComplaintStatus
    remarks: str | None = Field(default=None, max_length=2000, description="Citizen-visible remark")
    internal_note: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = None


class AssignRequest(BaseModel):
    officer_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = None


class RemarkRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    visibility: RemarkVisibility


class FeedbackRequest(BaseModel):
    feedback_type: FeedbackType
    remarks: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    feedback_id: uuid.UUID
    complaint_id: uuid.UUID
    feedback_type: FeedbackType
    remarks: str | None
    review_status: ReviewStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    decision_reason: str | None
    created_at: datetime


class ReviewDecision(BaseModel):
    decision: ReviewStatus  # ACCEPTED | REJECTED
    reason: str = Field(min_length=3, max_length=2000)


class VerifyRequest(BaseModel):
    decision: VerificationDecisionType
    reason: str = Field(min_length=3, max_length=2000)
    evidence_reviewed: list[uuid.UUID] = Field(min_length=1)
    expected_version: int | None = None


class RelationshipDecision(BaseModel):
    related_complaint_id: uuid.UUID
    relationship_status: RelationshipStatus  # CONFIRMED_RELATED | NOT_RELATED


class PriorityFactorsIn(BaseModel):
    """Human-confirmed factor values (0-100) from authorized staff. Omitted factors keep current evidence."""
    severity: float | None = Field(default=None, ge=0, le=100)
    safety_risk: float | None = Field(default=None, ge=0, le=100)
    location_sensitivity: float | None = Field(default=None, ge=0, le=100)
    public_exposure: float | None = Field(default=None, ge=0, le=100)
    duration: float | None = Field(default=None, ge=0, le=100)
    explanation: str = Field(min_length=3, max_length=1000)


class PublicationRequest(BaseModel):
    approve: bool
    public_summary: str | None = Field(default=None, min_length=10, max_length=500)


class RoutingOverride(BaseModel):
    department_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=2000)


# ---------- admin ----------
class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    active: bool = True
    is_prototype: bool = False
    source_reference: str | None = Field(default=None, max_length=500)


class DepartmentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    is_prototype: bool | None = None
    source_reference: str | None = Field(default=None, max_length=500)


class JurisdictionIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    jurisdiction_type: str = Field(default="OTHER", min_length=2, max_length=40)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    boundary: dict[str, Any] | None = None
    department_ids: list[uuid.UUID] = Field(default=[], description="Convenience: also activate these departments here")
    active: bool = True
    is_prototype: bool = False
    source_reference: str | None = Field(default=None, max_length=500)


class JurisdictionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    jurisdiction_type: str | None = Field(default=None, min_length=2, max_length=40)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    boundary: dict[str, Any] | None = None
    active: bool | None = None
    is_prototype: bool | None = None
    source_reference: str | None = Field(default=None, max_length=500)


class UnitIn(BaseModel):
    department_id: uuid.UUID
    jurisdiction_id: uuid.UUID
    active: bool = True


class UnitPatch(BaseModel):
    active: bool


class ResponsibilityIn(BaseModel):
    department_id: uuid.UUID
    category: Category
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    active: bool = True
    is_prototype: bool = False
    source_reference: str | None = Field(default=None, max_length=500)
    verified: bool | None = Field(default=None, description="Deprecated; status follows the source reference")


class SensitiveLocationIn(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    location_type: str = Field(min_length=2, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=100, gt=0, le=5000)
    sensitivity_score: float = Field(ge=0, le=100)
    is_prototype: bool = True
    source_reference: str | None = Field(default=None, max_length=500)


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    role: Role
    unit_id: uuid.UUID | None = Field(default=None, description="Department unit (department in a jurisdiction)")
    department_id: uuid.UUID | None = Field(default=None, description="Used when the department has exactly one unit")
    designation: str | None = Field(default=None, max_length=120)
    area_jurisdiction_ids: list[uuid.UUID] = []


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    account_status: AccountStatus | None = None
    unit_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    designation: str | None = Field(default=None, max_length=120)
    officer_active: bool | None = None
    area_jurisdiction_ids: list[uuid.UUID] | None = None
    grant_permissions: list[Permission] = []
    revoke_permissions: list[Permission] = []


class PriorityConfigIn(BaseModel):
    config: dict[str, Any]


class ConfidenceInfo(BaseModel):
    classification_confidence: float | None
    confidence_band: ConfidenceBand
    confidence_method: str | None
