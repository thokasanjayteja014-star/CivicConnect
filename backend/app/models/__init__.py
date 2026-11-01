"""SQLAlchemy ORM models (spec section 5.D plus supporting tables)."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from geoalchemy2 import Geography, Geometry
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import (
    AccountStatus,
    AssessmentStatus,
    AssignmentStatus,
    Category,
    CitizenExposure,
    CitizenSafetyRisk,
    CitizenSeverity,
    ComplaintStatus,
    ConfidenceBand,
    DeliveryStatus,
    FeedbackType,
    LocationSource,
    MediaPurpose,
    MediaType,
    Permission,
    PriorityLevel,
    PublicationStatus,
    RelationshipStatus,
    RemarkVisibility,
    ReviewStatus,
    Role,
    RoutingStatus,
    EscalationStatus,
    PublicIssueProgress,
    PublicIssueStatus,
    VerificationDecisionType,
    VerificationStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(e):
    return SAEnum(e, native_enum=False, length=40, validate_strings=True)


def _pk():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


TS = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.CITIZEN)
    account_status: Mapped[AccountStatus] = mapped_column(_enum(AccountStatus), default=AccountStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    # Notification channel preferences (in-app is always on) and UI language.
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notify_push: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", server_default="en")

    permissions: Mapped[list["UserPermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="UserPermission.user_id"
    )
    officer: Mapped["Officer | None"] = relationship(back_populates="user", uselist=False)


class UserPermission(Base):
    """Explicit permission grants beyond role defaults (e.g. VERIFY_RESOLUTION for an officer)."""
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "permission"),)
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission: Mapped[Permission] = mapped_column(_enum(Permission))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    user: Mapped[User] = relationship(back_populates="permissions", foreign_keys=[user_id])


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(TS)


class Department(Base):
    """Central department registry entry. Created once, then activated per jurisdiction via DepartmentUnit."""
    __tablename__ = "departments"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus), default=VerificationStatus.PENDING_VERIFICATION)
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=False)  # mirrors verification_status == PROTOTYPE
    source_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    rules: Mapped[list["ResponsibilityRule"]] = relationship(back_populates="department")
    units: Mapped[list["DepartmentUnit"]] = relationship(back_populates="department")

    @property
    def supported_categories(self) -> list[Category]:
        return sorted({r.category for r in self.rules if r.active}, key=lambda c: c.value)


class Jurisdiction(Base):
    """Node in the administrative hierarchy (state, district, municipality, ward, ...). Levels are not fixed."""
    __tablename__ = "jurisdictions"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(160))
    jurisdiction_type: Mapped[str] = mapped_column(String(40), default="OTHER", server_default="OTHER")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jurisdictions.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    boundary = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus), default=VerificationStatus.PENDING_VERIFICATION)
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=False)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    last_verified_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    parent: Mapped["Jurisdiction | None"] = relationship(remote_side="Jurisdiction.id")
    units: Mapped[list["DepartmentUnit"]] = relationship(back_populates="jurisdiction")


class DepartmentUnit(Base):
    """A registry department operating in one jurisdiction (department-jurisdiction mapping).

    The unit covers its jurisdiction and every descendant, unless a deeper unit of the
    same department exists. Personnel belong to a unit, so District A and District B
    instances of the same department never share complaints.
    """
    __tablename__ = "department_units"
    __table_args__ = (UniqueConstraint("department_id", "jurisdiction_id", name="uq_department_unit"),)
    id: Mapped[uuid.UUID] = _pk()
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jurisdictions.id", ondelete="RESTRICT"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    department: Mapped[Department] = relationship(back_populates="units")
    jurisdiction: Mapped[Jurisdiction] = relationship(back_populates="units")


class Officer(Base):
    """Department personnel record (department administrators and officers)."""
    __tablename__ = "officers"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id"))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department_units.id", ondelete="RESTRICT"), index=True)
    designation: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped[User] = relationship(back_populates="officer")
    department: Mapped[Department] = relationship()
    unit: Mapped[DepartmentUnit | None] = relationship()
    areas: Mapped[list["OfficerArea"]] = relationship(back_populates="officer", cascade="all, delete-orphan")


class OfficerArea(Base):
    """Operational area of an officer: a jurisdiction (and its descendants) inside the officer's unit."""
    __tablename__ = "officer_areas"
    __table_args__ = (UniqueConstraint("officer_id", "jurisdiction_id", name="uq_officer_area"),)
    id: Mapped[uuid.UUID] = _pk()
    officer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("officers.id", ondelete="CASCADE"), index=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jurisdictions.id", ondelete="RESTRICT"))
    officer: Mapped[Officer] = relationship(back_populates="areas")
    jurisdiction: Mapped[Jurisdiction] = relationship()


class ResponsibilityRule(Base):
    """Category-to-department responsibility (e.g. Roads: 'Pothole repair' for ROAD_INFRASTRUCTURE)."""
    __tablename__ = "responsibility_rules"
    __table_args__ = (UniqueConstraint("department_id", "category"),)
    id: Mapped[uuid.UUID] = _pk()
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id"))
    category: Mapped[Category] = mapped_column(_enum(Category))
    name: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # legacy flag, mirrors status == VERIFIED
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus), default=VerificationStatus.PENDING_VERIFICATION)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    department: Mapped[Department] = relationship(back_populates="rules")


class SensitiveLocation(Base):
    """Administrator-configured sensitive places used for the L (location sensitivity) factor."""
    __tablename__ = "sensitive_locations"
    id: Mapped[uuid.UUID] = _pk()
    label: Mapped[str] = mapped_column(String(200))
    location_type: Mapped[str] = mapped_column(String(80))
    point = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, default=100.0)
    sensitivity_score: Mapped[float] = mapped_column(Float)
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=True)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class PriorityConfig(Base):
    """Versioned priority weights / thresholds / rubric mappings. Exactly one active."""
    __tablename__ = "priority_configs"
    id: Mapped[uuid.UUID] = _pk()
    version: Mapped[int] = mapped_column(Integer, unique=True)
    config: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        UniqueConstraint("citizen_id", "idempotency_key", name="uq_complaint_idempotency"),
        Index("ix_complaints_status", "status"),
        Index("ix_complaints_department", "department_id"),
    )
    id: Mapped[uuid.UUID] = _pk()
    reference_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    citizen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    original_description: Mapped[str | None] = mapped_column(Text)
    citizen_confirmed_description: Mapped[str] = mapped_column(Text)
    category: Mapped[Category] = mapped_column(_enum(Category))
    location = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_meters: Mapped[float | None] = mapped_column(Float)
    location_source: Mapped[LocationSource] = mapped_column(_enum(LocationSource))
    landmark: Mapped[str | None] = mapped_column(String(200))
    address_text: Mapped[str | None] = mapped_column(String(300))
    occurred_at: Mapped[datetime | None] = mapped_column(TS)
    additional_details: Mapped[str | None] = mapped_column(Text)
    citizen_severity: Mapped[CitizenSeverity | None] = mapped_column(_enum(CitizenSeverity))
    citizen_safety_risk: Mapped[CitizenSafetyRisk | None] = mapped_column(_enum(CitizenSafetyRisk))
    citizen_exposure: Mapped[CitizenExposure | None] = mapped_column(_enum(CitizenExposure))

    priority_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    priority_level: Mapped[PriorityLevel | None] = mapped_column(_enum(PriorityLevel))
    priority_assessment_status: Mapped[AssessmentStatus] = mapped_column(
        _enum(AssessmentStatus), default=AssessmentStatus.UNAVAILABLE
    )
    needs_prompt_review: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[ComplaintStatus] = mapped_column(_enum(ComplaintStatus), default=ComplaintStatus.SUBMITTED)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    department_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department_units.id"), index=True)
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jurisdictions.id"))
    routing_status: Mapped[RoutingStatus] = mapped_column(_enum(RoutingStatus))
    # Resolution deadline from the escalation policy for the complaint's priority.
    due_at: Mapped[datetime | None] = mapped_column(TS, index=True)

    ai_analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_analyses.id"))
    ai_review_required: Mapped[bool] = mapped_column(Boolean, default=False)

    allow_public_display: Mapped[bool] = mapped_column(Boolean, default=True)
    publication_status: Mapped[PublicationStatus] = mapped_column(
        _enum(PublicationStatus), default=PublicationStatus.NOT_REVIEWED
    )
    public_summary: Mapped[str | None] = mapped_column(String(500))
    flagged_misuse: Mapped[bool] = mapped_column(Boolean, default=False)

    version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    citizen: Mapped[User] = relationship(foreign_keys=[citizen_id])
    department: Mapped[Department | None] = relationship()
    department_unit: Mapped[DepartmentUnit | None] = relationship()
    jurisdiction: Mapped[Jurisdiction | None] = relationship()
    media: Mapped[list["Media"]] = relationship(back_populates="complaint", order_by="Media.uploaded_at")


class PriorityAssessment(Base):
    __tablename__ = "priority_assessments"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    assessment_status: Mapped[AssessmentStatus] = mapped_column(_enum(AssessmentStatus))
    priority_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    priority_level: Mapped[PriorityLevel | None] = mapped_column(_enum(PriorityLevel))
    severity_score: Mapped[float | None] = mapped_column(Float)
    safety_risk_score: Mapped[float | None] = mapped_column(Float)
    location_sensitivity_score: Mapped[float | None] = mapped_column(Float)
    public_exposure_score: Mapped[float | None] = mapped_column(Float)
    duration_score: Mapped[float | None] = mapped_column(Float)
    factor_evidence: Mapped[dict] = mapped_column(JSON)
    needs_prompt_review: Mapped[bool] = mapped_column(Boolean, default=False)
    rubric_version: Mapped[str] = mapped_column(String(40))
    assessed_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    department_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department_units.id"))
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jurisdictions.id"))
    officer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("officers.id"))
    routing_status: Mapped[RoutingStatus] = mapped_column(_enum(RoutingStatus))
    reason_code: Mapped[str] = mapped_column(String(60))
    rule_version: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(Text)
    candidates: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    department: Mapped[Department | None] = relationship()


class Media(Base):
    __tablename__ = "media"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("complaints.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[MediaPurpose] = mapped_column(_enum(MediaPurpose), default=MediaPurpose.COMPLAINT)
    media_type: Mapped[MediaType] = mapped_column(_enum(MediaType))
    storage_key: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    sha256: Mapped[str] = mapped_column(String(64))
    # 64-bit difference hash (hex) of images, for visual duplicate matching. Not an AI output.
    perceptual_hash: Mapped[str | None] = mapped_column(String(16))
    public_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    complaint: Mapped[Complaint | None] = relationship(back_populates="media")


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("complaints.id", use_alter=True))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    model_identifier: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str | None] = mapped_column(String(120))
    suggested_category: Mapped[Category] = mapped_column(_enum(Category))
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    confidence_band: Mapped[ConfidenceBand] = mapped_column(_enum(ConfidenceBand))
    confidence_method: Mapped[str | None] = mapped_column(Text)
    structured_output: Mapped[dict] = mapped_column(JSON)
    input_media_ids: Mapped[list] = mapped_column(JSON, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ComplaintRelationship(Base):
    __tablename__ = "complaint_relationships"
    __table_args__ = (UniqueConstraint("source_complaint_id", "related_complaint_id"),)
    id: Mapped[uuid.UUID] = _pk()
    source_complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    related_complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    text_similarity: Mapped[float | None] = mapped_column(Float)
    text_similarity_method: Mapped[str | None] = mapped_column(String(80))
    match_reasons: Mapped[list] = mapped_column(JSON, default=list)
    relationship_status: Mapped[RelationshipStatus] = mapped_column(
        _enum(RelationshipStatus), default=RelationshipStatus.SUGGESTED
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id"))
    department_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department_units.id"))
    officer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("officers.id"))
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL = routing engine
    automatic: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reason: Mapped[str | None] = mapped_column(Text)
    assigned_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(TS)
    assignment_status: Mapped[AssignmentStatus] = mapped_column(_enum(AssignmentStatus), default=AssignmentStatus.ACTIVE)
    officer: Mapped[Officer | None] = relationship()


class StatusHistory(Base):
    """Immutable: rows are only ever inserted."""
    __tablename__ = "status_history"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    previous_status: Mapped[ComplaintStatus | None] = mapped_column(_enum(ComplaintStatus))
    new_status: Mapped[ComplaintStatus] = mapped_column(_enum(ComplaintStatus))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL = system (routing engine)
    actor_role: Mapped[Role | None] = mapped_column(_enum(Role))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ComplaintRemark(Base):
    __tablename__ = "complaint_remarks"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    author_role: Mapped[Role] = mapped_column(_enum(Role))
    visibility: Mapped[RemarkVisibility] = mapped_column(_enum(RemarkVisibility))
    kind: Mapped[str] = mapped_column(String(30), default="REMARK")  # REMARK | CLARIFICATION_REQUEST | CITIZEN_REPLY
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ResolutionEvidence(Base):
    __tablename__ = "resolution_evidence"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    media_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media.id"))
    description: Mapped[str | None] = mapped_column(Text)
    citizen_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    media: Mapped[Media] = relationship()


class VerificationDecision(Base):
    __tablename__ = "verification_decisions"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    verifier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[VerificationDecisionType] = mapped_column(_enum(VerificationDecisionType))
    reason: Mapped[str] = mapped_column(Text)
    evidence_reviewed: Mapped[list] = mapped_column(JSON, default=list)
    citizen_feedback_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class CitizenFeedback(Base):
    __tablename__ = "citizen_feedback"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    citizen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    feedback_type: Mapped[FeedbackType] = mapped_column(_enum(FeedbackType))
    remarks: Mapped[str | None] = mapped_column(Text)
    status_at_submission: Mapped[ComplaintStatus] = mapped_column(_enum(ComplaintStatus))
    review_status: Mapped[ReviewStatus] = mapped_column(_enum(ReviewStatus))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = _pk()
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("complaints.id"))
    notification_type: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="IN_APP")
    delivery_status: Mapped[DeliveryStatus] = mapped_column(_enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    read_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class NotificationDelivery(Base):
    """One attempt to deliver a notification over an external channel (EMAIL / SMS / PUSH)."""
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "channel"),)
    id: Mapped[uuid.UUID] = _pk()
    notification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    delivery_status: Mapped[DeliveryStatus] = mapped_column(_enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(TS)


class PushSubscription(Base):
    """A browser Web Push subscription (VAPID)."""
    __tablename__ = "push_subscriptions"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = _pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)


class EscalationPolicy(Base):
    """Resolution deadline per priority (optionally per department). Missing rows fall back to code defaults."""
    __tablename__ = "escalation_policies"
    __table_args__ = (UniqueConstraint("department_id", "priority_level", name="uq_escalation_policy"),)
    id: Mapped[uuid.UUID] = _pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"))
    priority_level: Mapped[str] = mapped_column(String(20))  # LOW | MEDIUM | HIGH | CRITICAL | UNSCORED
    resolve_within_hours: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Escalation(Base):
    __tablename__ = "escalations"
    id: Mapped[uuid.UUID] = _pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"), index=True)
    department_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department_units.id"))
    level: Mapped[int] = mapped_column(Integer, default=1)
    reason_code: Mapped[str] = mapped_column(String(40))  # OVERDUE | MANUAL
    reason: Mapped[str] = mapped_column(Text)
    raised_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL = automatic
    status: Mapped[EscalationStatus] = mapped_column(_enum(EscalationStatus), default=EscalationStatus.OPEN)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    complaint: Mapped[Complaint] = relationship()


class PublicIssue(Base):
    """A verified issue of wider public impact, published for community transparency.

    Holds only public information; linked complaints keep their private details.
    """
    __tablename__ = "public_issues"
    id: Mapped[uuid.UUID] = _pk()
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    general_location: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float)   # rounded, approximate
    longitude: Mapped[float | None] = mapped_column(Float)
    category: Mapped[Category] = mapped_column(_enum(Category))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    department_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department_units.id"))
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jurisdictions.id"))
    status: Mapped[PublicIssueStatus] = mapped_column(_enum(PublicIssueStatus), default=PublicIssueStatus.DRAFT)
    progress: Mapped[PublicIssueProgress] = mapped_column(_enum(PublicIssueProgress), default=PublicIssueProgress.REPORTED)
    impact_level: Mapped[str | None] = mapped_column(String(20))  # LOW / MODERATE / HIGH (staff assessment)
    impact_assessment: Mapped[str | None] = mapped_column(Text)
    resolution_info: Mapped[str | None] = mapped_column(Text)
    # None when CivicConnect created the issue automatically from a cluster of complaints.
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    auto_publish_at: Mapped[datetime | None] = mapped_column(TS)
    published_automatically: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(TS)
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(TS)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)
    department: Mapped[Department | None] = relationship()
    jurisdiction: Mapped[Jurisdiction | None] = relationship()


class PublicIssueComplaint(Base):
    __tablename__ = "public_issue_complaints"
    __table_args__ = (UniqueConstraint("complaint_id", name="uq_public_issue_complaint"),)
    id: Mapped[uuid.UUID] = _pk()
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("public_issues.id", ondelete="CASCADE"), index=True)
    complaint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complaints.id"))
    linked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None = automatic
    linked_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class PublicIssueUpdate(Base):
    """Public update history (immutable)."""
    __tablename__ = "public_issue_updates"
    id: Mapped[uuid.UUID] = _pk()
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("public_issues.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text)
    progress: Mapped[PublicIssueProgress | None] = mapped_column(_enum(PublicIssueProgress))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None = automatic
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
