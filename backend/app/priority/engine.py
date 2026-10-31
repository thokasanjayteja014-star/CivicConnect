"""Deterministic priority engine (spec L6).

P = wS*S + wR*R + wL*L + wE*E + wD*D, all factors normalized 0-100.

This is an internal prototype prioritization heuristic, not an official
government urgency standard. An LLM never computes or overrides the score:
AI may only contribute evidence, which this module does not consume as a
factor value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.models.enums import AssessmentStatus, PriorityLevel

FACTORS = ("severity", "safety_risk", "location_sensitivity", "public_exposure", "duration")

# Default prototype configuration (version 0 = built-in). Admins create new
# versions through /api/admin/priority-config; every change is audited.
DEFAULT_PRIORITY_CONFIG: dict[str, Any] = {
    "rubric_version": "prototype-rubric-v1",
    "weights": {
        "severity": 0.30,
        "safety_risk": 0.25,
        "location_sensitivity": 0.20,
        "public_exposure": 0.15,
        "duration": 0.10,
    },
    # Lower bounds (inclusive) for each level.
    "thresholds": {"CRITICAL": 80.0, "HIGH": 60.0, "MEDIUM": 40.0},
    # Citizen-provided observations mapped to a value inside each rubric band.
    "citizen_severity_scores": {"MINOR": 20, "MODERATE": 45, "SUBSTANTIAL": 70, "SEVERE": 90},
    "citizen_safety_scores": {"NONE": 0, "LOW": 20, "MODERATE": 45, "SIGNIFICANT": 70, "IMMEDIATE": 90},
    "citizen_exposure_scores": {
        "INDIVIDUAL": 10,
        "FEW_HOUSEHOLDS": 25,
        "STREET": 45,
        "NEIGHBOURHOOD": 70,
        "WIDE_AREA": 90,
    },
    # Duration bands: [max_days_inclusive, low_score, high_score]; linear within band.
    "duration_bands": [[0.999, 0, 0], [2, 1, 20], [7, 21, 40], [14, 41, 60], [30, 61, 80], [90, 81, 100]],
    # Score applied when configured sensitive locations exist but none contains the point.
    "ordinary_location_score": 15,
    # Safety risk at or above this value is treated as potentially immediate danger.
    "immediate_safety_threshold": 76,
}


class PriorityConfigError(ValueError):
    pass


def validate_priority_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = {**DEFAULT_PRIORITY_CONFIG, **config}
    weights = merged["weights"]
    if set(weights) != set(FACTORS):
        raise PriorityConfigError(f"weights must contain exactly: {', '.join(FACTORS)}")
    if any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()):
        raise PriorityConfigError("weights must be non-negative numbers")
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise PriorityConfigError("weights must sum to 1.0")
    t = merged["thresholds"]
    if not (100 >= t["CRITICAL"] > t["HIGH"] > t["MEDIUM"] > 0):
        raise PriorityConfigError("thresholds must satisfy 100 >= CRITICAL > HIGH > MEDIUM > 0")
    for key in ("citizen_severity_scores", "citizen_safety_scores", "citizen_exposure_scores"):
        if any(not (0 <= float(v) <= 100) for v in merged[key].values()):
            raise PriorityConfigError(f"{key} values must be within 0-100")
    prev = -1.0
    for band in merged["duration_bands"]:
        if len(band) != 3 or band[0] <= prev or not (0 <= band[1] <= band[2] <= 100):
            raise PriorityConfigError("duration_bands must be increasing [max_days, low, high] within 0-100")
        prev = band[0]
    return merged


@dataclass
class FactorValue:
    value: float | None
    source: str  # CITIZEN_PROVIDED | ADMIN_CONFIGURED_DATA | HUMAN_CONFIRMED | DERIVED_FROM_CITIZEN_DATE | UNAVAILABLE
    explanation: str
    method: str

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source, "explanation": self.explanation, "method": self.method}


@dataclass
class PriorityResult:
    assessment_status: AssessmentStatus
    priority_score: Decimal | None
    priority_level: PriorityLevel | None
    factors: dict[str, FactorValue]
    needs_prompt_review: bool
    review_reasons: list[str] = field(default_factory=list)
    rubric_version: str = DEFAULT_PRIORITY_CONFIG["rubric_version"]


def level_for_score(score: float, thresholds: dict[str, float] | None = None) -> PriorityLevel:
    t = thresholds or DEFAULT_PRIORITY_CONFIG["thresholds"]
    if score >= t["CRITICAL"]:
        return PriorityLevel.CRITICAL
    if score >= t["HIGH"]:
        return PriorityLevel.HIGH
    if score >= t["MEDIUM"]:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


def round2(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_priority(
    factors: dict[str, float | None], config: dict[str, Any] | None = None
) -> tuple[Decimal | None, PriorityLevel | None]:
    """Pure formula. Returns (None, None) if any factor is missing: never invents values."""
    cfg = config or DEFAULT_PRIORITY_CONFIG
    if any(factors.get(f) is None for f in FACTORS):
        return None, None
    for f in FACTORS:
        v = float(factors[f])  # type: ignore[arg-type]
        if not 0 <= v <= 100:
            raise ValueError(f"factor {f} must be within 0-100")
    score = sum(cfg["weights"][f] * float(factors[f]) for f in FACTORS)  # type: ignore[arg-type]
    rounded = round2(score)
    return rounded, level_for_score(float(rounded), cfg["thresholds"])


def duration_score(days: float, bands: list[list[float]]) -> float:
    """Normalize a known duration (days) to 0-100 using the configured bands."""
    if days < 0:
        raise ValueError("duration cannot be negative")
    lower_days = 0.0
    for max_days, low, high in bands:
        if days <= max_days:
            span = max_days - lower_days
            if span <= 0 or high == low:
                return float(low)
            fraction = (days - lower_days) / span
            return round(low + fraction * (high - low), 2)
        lower_days = max_days
    return float(bands[-1][2])


def assess_priority(
    *,
    citizen_severity: str | None,
    citizen_safety_risk: str | None,
    citizen_exposure: str | None,
    occurred_at: datetime | None,
    reference_time: datetime,
    location_sensitivity: FactorValue | None,
    config: dict[str, Any] | None = None,
    overrides: dict[str, FactorValue] | None = None,
) -> PriorityResult:
    """Build factor values from available evidence and compute the result.

    `overrides` are human-confirmed factor values supplied by authorized staff.
    """
    cfg = config or DEFAULT_PRIORITY_CONFIG
    factors: dict[str, FactorValue] = {}

    def mapped(name: str, raw: str | None, table_key: str, label: str) -> FactorValue:
        if raw is None:
            return FactorValue(None, "UNAVAILABLE", f"No {label} information was provided.", "none")
        value = float(cfg[table_key][raw])
        return FactorValue(
            value,
            "CITIZEN_PROVIDED",
            f"Citizen reported {label} as {raw.replace('_', ' ').lower()}.",
            f"citizen selection mapped via {table_key} ({cfg['rubric_version']})",
        )

    factors["severity"] = mapped("severity", citizen_severity, "citizen_severity_scores", "physical severity")
    factors["safety_risk"] = mapped("safety_risk", citizen_safety_risk, "citizen_safety_scores", "safety risk")
    factors["public_exposure"] = mapped(
        "public_exposure", citizen_exposure, "citizen_exposure_scores", "extent of people affected"
    )
    factors["location_sensitivity"] = location_sensitivity or FactorValue(
        None,
        "UNAVAILABLE",
        "No verified or administrator-configured sensitive-location data is available.",
        "none",
    )
    if occurred_at is not None:
        ref = reference_time if reference_time.tzinfo else reference_time.replace(tzinfo=timezone.utc)
        occ = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=timezone.utc)
        days = max((ref - occ).total_seconds() / 86400.0, 0.0)
        factors["duration"] = FactorValue(
            duration_score(days, cfg["duration_bands"]),
            "DERIVED_FROM_CITIZEN_DATE",
            f"Issue reported as present for about {days:.1f} day(s) (citizen-provided occurrence date).",
            "configured duration bands",
        )
    else:
        factors["duration"] = FactorValue(None, "UNAVAILABLE", "Occurrence date unknown; duration not assessed.", "none")

    for name, fv in (overrides or {}).items():
        if name in FACTORS:
            factors[name] = fv

    values = {k: v.value for k, v in factors.items()}
    reasons: list[str] = []
    safety = values.get("safety_risk")
    needs_prompt_review = safety is not None and safety >= cfg["immediate_safety_threshold"]
    if needs_prompt_review:
        reasons.append("Potentially immediate safety concern reported; prompt human review required.")

    missing = [f for f in FACTORS if values[f] is None]
    score, level = calculate_priority(values, cfg)
    if not missing:
        status = AssessmentStatus.FINAL
    elif len(missing) == len(FACTORS):
        status = AssessmentStatus.UNAVAILABLE
        reasons.append("No priority factors could be assessed; human review required.")
    else:
        status = AssessmentStatus.PROVISIONAL
        reasons.append("Missing factors: " + ", ".join(missing) + ". Score withheld pending human review.")

    return PriorityResult(
        assessment_status=status,
        priority_score=score,
        priority_level=level,
        factors=factors,
        needs_prompt_review=needs_prompt_review,
        review_reasons=reasons,
        rubric_version=cfg["rubric_version"],
    )
