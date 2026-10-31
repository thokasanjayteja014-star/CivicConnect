"""Typed AI contracts (spec 5.C). All provider output must validate against these."""
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Category, ConfidenceBand, MediaType


class MediaAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_id: str = Field(min_length=1)
    media_type: MediaType
    extracted_description: str = Field(min_length=1, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_band: ConfidenceBand
    limitations: list[str] = Field(default_factory=list)


class ComplaintAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggested_title: str = Field(min_length=3, max_length=150)
    suggested_summary: str = Field(min_length=10, max_length=2000)
    suggested_category: Category
    extracted_issue: str = Field(min_length=1, max_length=1000)
    visible_evidence: list[str] = Field(default_factory=list)
    potential_safety_concerns: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    classification_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_band: ConfidenceBand
    confidence_method: str = Field(min_length=3, max_length=500)
    media_analysis: list[MediaAnalysis] = Field(default_factory=list)
    transcription: str | None = None
    requires_human_review: bool
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self):
        if self.confidence_band == ConfidenceBand.UNAVAILABLE and self.classification_confidence is not None:
            raise ValueError("classification_confidence must be null when confidence_band is UNAVAILABLE")
        return self


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcription: str
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class EmbeddingResult(BaseModel):
    available: bool
    embedding: list[float] | None = None
    model: str | None = None
    reason: str | None = None


class CapabilityStatus(BaseModel):
    name: str
    configured: bool
    status: str  # AVAILABLE | AI_NOT_CONFIGURED | AI_NOT_IMPLEMENTED
    model: str | None = None
    note: str | None = None


class AIStatus(BaseModel):
    provider: str | None
    mode: str  # "configured" | "stub"
    capabilities: list[CapabilityStatus]
