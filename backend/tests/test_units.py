"""Unit tests required by spec 10.D (pure functions, no I/O)."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ai.ai_service import AIUnavailable, validate_ai_output
from app.core.errors import ApiError
from app.duplicate_detection import CandidateInput, detect_duplicate_candidates, lexical_similarity
from app.models.enums import (
    AssessmentStatus,
    ComplaintStatus as S,
    Permission,
    PriorityLevel,
    PublicationStatus,
    Role,
    RoutingStatus,
)
from app.priority.engine import (
    DEFAULT_PRIORITY_CONFIG,
    FactorValue,
    PriorityConfigError,
    assess_priority,
    calculate_priority,
    duration_score,
    level_for_score,
    validate_priority_config,
)
from app.routing.engine import (
    DepartmentFact,
    LeafFact,
    OfficerFact,
    RoutingInput,
    UnitFact,
    choose_officer,
    determine_routing,
)
from app.schemas import LocationIn
from app.security.permissions import Actor, can_view_complaint, check_role_permissions, has_permission, in_department_scope
from app.services.complaints import generate_complaint_reference, validate_complaint_input, validate_location
from app.services.lifecycle import PERMITTED_TRANSITIONS, validate_status_transition


# 1. validate_complaint_input
def test_valid_input():
    assert validate_complaint_input("  Streetlight not working for a week  ", False) == "Streetlight not working for a week"


@pytest.mark.parametrize("text,media,code", [
    (None, False, "EMPTY_COMPLAINT"),
    ("   ", False, "EMPTY_COMPLAINT"),
    ("short", False, "DESCRIPTION_TOO_SHORT"),
    ("x" * 3001, False, "DESCRIPTION_TOO_LONG"),
])
def test_invalid_input(text, media, code):
    with pytest.raises(ApiError) as e:
        validate_complaint_input(text, media)
    assert e.value.error_code == code and e.value.status_code == 422


def test_media_only_input_allowed_for_analysis():
    assert validate_complaint_input(None, True) is None


# 2. validate_location
def test_valid_location():
    loc = LocationIn(latitude=12.97, longitude=77.59, location_source="GPS")
    assert validate_location(loc) is loc


@pytest.mark.parametrize("lat,lng", [(91, 0), (-90.1, 0), (0, 180.5), (0, -181), (None, 10)])
def test_invalid_location(lat, lng):
    with pytest.raises(ApiError) as e:
        validate_location(LocationIn(latitude=lat, longitude=lng, location_source="MAP_SELECTION"))
    assert e.value.error_code == "INVALID_COORDINATES"


# 3. calculate_priority
def test_priority_ac9():
    score, level = calculate_priority({"severity": 80, "safety_risk": 90, "location_sensitivity": 70,
                                       "public_exposure": 60, "duration": 50})
    assert score == Decimal("74.50") and level == PriorityLevel.HIGH


@pytest.mark.parametrize("score,level", [
    (100, PriorityLevel.CRITICAL), (80, PriorityLevel.CRITICAL), (79.99, PriorityLevel.HIGH), (60, PriorityLevel.HIGH),
    (59.99, PriorityLevel.MEDIUM), (40, PriorityLevel.MEDIUM), (39.99, PriorityLevel.LOW), (0, PriorityLevel.LOW),
])
def test_priority_boundaries(score, level):
    assert level_for_score(score) == level


def test_missing_factor_not_invented():
    score, level = calculate_priority({"severity": 80, "safety_risk": 90, "location_sensitivity": None,
                                       "public_exposure": 60, "duration": 50})
    assert score is None and level is None


def test_assess_priority_provisional_when_factor_missing():
    now = datetime.now(timezone.utc)
    r = assess_priority(citizen_severity="SEVERE", citizen_safety_risk="LOW", citizen_exposure="STREET",
                        occurred_at=None, reference_time=now, location_sensitivity=None)
    assert r.assessment_status == AssessmentStatus.PROVISIONAL
    assert r.priority_score is None and r.priority_level is None
    assert r.factors["duration"].value is None and r.factors["location_sensitivity"].value is None


def test_assess_priority_unavailable_when_nothing_known():
    r = assess_priority(citizen_severity=None, citizen_safety_risk=None, citizen_exposure=None, occurred_at=None,
                        reference_time=datetime.now(timezone.utc), location_sensitivity=None)
    assert r.assessment_status == AssessmentStatus.UNAVAILABLE and r.priority_score is None


def test_assess_priority_final_and_immediate_safety_flag():
    now = datetime.now(timezone.utc)
    r = assess_priority(citizen_severity="MINOR", citizen_safety_risk="IMMEDIATE", citizen_exposure="INDIVIDUAL",
                        occurred_at=now - timedelta(hours=2), reference_time=now,
                        location_sensitivity=FactorValue(15, "ADMIN_CONFIGURED_DATA", "x", "y"))
    assert r.assessment_status == AssessmentStatus.FINAL
    assert r.priority_score is not None
    assert r.needs_prompt_review is True  # flagged even though the aggregate score is lower


def test_human_override_completes_assessment():
    now = datetime.now(timezone.utc)
    r = assess_priority(citizen_severity="SEVERE", citizen_safety_risk="SIGNIFICANT", citizen_exposure="STREET",
                        occurred_at=now - timedelta(days=3), reference_time=now, location_sensitivity=None,
                        overrides={"location_sensitivity": FactorValue(60, "HUMAN_CONFIRMED", "school nearby", "officer")})
    assert r.assessment_status == AssessmentStatus.FINAL
    assert r.factors["location_sensitivity"].source == "HUMAN_CONFIRMED"


def test_duration_bands():
    bands = DEFAULT_PRIORITY_CONFIG["duration_bands"]
    assert duration_score(0.5, bands) == 0
    assert 1 <= duration_score(1.5, bands) <= 20
    assert 21 <= duration_score(5, bands) <= 40
    assert 61 <= duration_score(20, bands) <= 80
    assert duration_score(400, bands) == 100


def test_priority_config_validation():
    with pytest.raises(PriorityConfigError):
        validate_priority_config({"weights": {"severity": 0.5, "safety_risk": 0.5, "location_sensitivity": 0.5,
                                              "public_exposure": 0, "duration": 0}})
    ok = validate_priority_config({"weights": {"severity": 0.2, "safety_risk": 0.2, "location_sensitivity": 0.2,
                                               "public_exposure": 0.2, "duration": 0.2}})
    assert ok["weights"]["severity"] == 0.2


# 4. detect_duplicate_candidates
def _cand(dist, days_ago, cat="ROAD_INFRASTRUCTURE", text="deep pothole near the bus stop on main road"):
    now = datetime.now(timezone.utc)
    return CandidateInput(str(uuid.uuid4()), cat, now - timedelta(days=days_ago), dist, text)


def test_duplicate_candidates_returned_with_reasons():
    now = datetime.now(timezone.utc)
    near = _cand(40, 2)
    out = detect_duplicate_candidates(category="ROAD_INFRASTRUCTURE", created_at=now,
                                      text="pothole near bus stop on the main road", candidates=[near])
    assert len(out) == 1 and out[0].complaint_id == near.complaint_id
    assert any("Within" in r for r in out[0].match_reasons)
    assert any("Similar description" in r for r in out[0].match_reasons)


def test_unrelated_not_candidates():
    now = datetime.now(timezone.utc)
    out = detect_duplicate_candidates(category="ROAD_INFRASTRUCTURE", created_at=now, text="pothole",
                                      candidates=[_cand(500, 1), _cand(20, 45), _cand(20, 1, cat="STREETLIGHT")])
    assert out == []


def test_lexical_similarity_bounds():
    assert lexical_similarity("water leak", "water leak") == 1.0
    assert lexical_similarity("water leak", "broken streetlight") == 0.0


# 5. determine_routing (hierarchy + units + officers)
D1, D2 = uuid.uuid4(), uuid.uuid4()
J, PARENT = uuid.uuid4(), uuid.uuid4()
U1, U2 = uuid.uuid4(), uuid.uuid4()
ROADS, WORKS = DepartmentFact(D1, "Roads", True), DepartmentFact(D2, "Works", True)


def _inp(responsible, units=None, containing=True, configured=True, uncertain=False, officers=None):
    units = units if units is not None else {D1: UnitFact(U1, D1, PARENT, "District", True),
                                             D2: UnitFact(U2, D2, J, "Ward 1", True)}
    leaf = LeafFact(J, "Ward 1", "District › Ward 1", {d.id: units.get(d.id) for d in responsible})
    return RoutingInput(category="ROAD_INFRASTRUCTURE", any_jurisdiction_configured=configured, location_uncertain=uncertain,
                        accuracy_meters=None, leaves=[leaf] if containing else [], responsible=responsible,
                        officers=officers or {})


def test_routing_single_match_uses_parent_unit():
    r = determine_routing(_inp([ROADS]))
    assert r.routing_status == RoutingStatus.ROUTED and r.department_id == D1 and r.unit_id == U1 and r.jurisdiction_id == J
    assert "Roads" in r.explanation and r.officer_id is None


def test_routing_multiple_matches_review():
    r = determine_routing(_inp([ROADS, WORKS]))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.department_id is None
    assert r.reason_code == "MULTIPLE_DEPARTMENTS"


def test_routing_outside_jurisdiction_review():
    r = determine_routing(_inp([ROADS], containing=False))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.reason_code == "OUTSIDE_JURISDICTION"


def test_routing_department_not_mapped_here():
    r = determine_routing(_inp([ROADS], units={}))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.reason_code == "DEPARTMENT_NOT_ACTIVE_HERE"


def test_routing_inactive_unit_blocks():
    r = determine_routing(_inp([ROADS], units={D1: UnitFact(U1, D1, PARENT, "District", False)}))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.reason_code == "DEPARTMENT_NOT_ACTIVE_HERE"


def test_routing_no_responsibility_review():
    r = determine_routing(_inp([]))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.reason_code == "NO_RESPONSIBILITY"


def test_routing_nothing_configured_review():
    r = determine_routing(_inp([], containing=False, configured=False))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.reason_code == "NO_JURISDICTION_CONFIGURED"


def test_routing_uncertain_location_review():
    r = determine_routing(_inp([ROADS], uncertain=True))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.reason_code == "LOCATION_UNCERTAIN"


def test_routing_inactive_department_not_routed():
    r = determine_routing(_inp([DepartmentFact(D1, "Roads", False)]))
    assert r.routing_status == RoutingStatus.PENDING_REVIEW and r.department_id is None


def test_routing_picks_officer_by_area_then_workload():
    o_area, o_wide, o_busy = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    officers = {U1: [OfficerFact(o_wide, "Wide", 0, -1), OfficerFact(o_area, "Area", 3, 1), OfficerFact(o_busy, "Other area", 0, None)]}
    r = determine_routing(_inp([ROADS], officers=officers))
    assert r.officer_id == o_area and "operational area" in r.officer_reason


def test_choose_officer_workload_tiebreak_and_none():
    a, b = uuid.uuid4(), uuid.uuid4()
    best, _ = choose_officer([OfficerFact(a, "A", 2, -1), OfficerFact(b, "B", 1, -1)])
    assert best.id == b
    none, reason = choose_officer([OfficerFact(a, "A", 0, None)])
    assert none is None and "unassigned queue" in reason


# 6. validate_status_transition
@pytest.mark.parametrize("a,b", [(a, b) for a, bs in PERMITTED_TRANSITIONS.items() for b in bs])
def test_permitted_transitions(a, b):
    assert validate_status_transition(a, b)


@pytest.mark.parametrize("a,b", [
    (S.SUBMITTED, S.VERIFIED_RESOLVED), (S.SUBMITTED, S.ASSIGNED), (S.REJECTED, S.UNDER_REVIEW),
    (S.IN_PROGRESS, S.VERIFIED_RESOLVED), (S.VERIFIED_RESOLVED, S.IN_PROGRESS), (S.ON_HOLD, S.RESOLVED_AWAITING_VERIFICATION),
])
def test_forbidden_transitions(a, b):
    assert not validate_status_transition(a, b)


# 7. check_role_permissions
class _C:
    def __init__(self, citizen_id, unit_id, jurisdiction_id=None):
        self.id = uuid.uuid4()
        self.citizen_id, self.department_unit_id, self.jurisdiction_id = citizen_id, unit_id, jurisdiction_id


def test_role_permissions():
    unit_a, unit_b = uuid.uuid4(), uuid.uuid4()
    citizen = Actor(uuid.uuid4(), Role.CITIZEN, "c")
    officer = Actor(uuid.uuid4(), Role.OFFICER, "o", department_id=uuid.uuid4(), officer_active=True, unit_id=unit_a)
    dadmin = Actor(uuid.uuid4(), Role.DEPARTMENT_ADMIN, "d", department_id=officer.department_id, officer_active=True, unit_id=unit_a)
    sysadmin = Actor(uuid.uuid4(), Role.SYSTEM_ADMIN, "s")
    a, b = _C(uuid.uuid4(), unit_a), _C(uuid.uuid4(), unit_b)

    with pytest.raises(ApiError):
        check_role_permissions(citizen, {Role.OFFICER, Role.DEPARTMENT_ADMIN})
    assert can_view_complaint(citizen, _C(citizen.user_id, unit_a))
    assert not can_view_complaint(citizen, a)
    assert in_department_scope(officer, a) and not in_department_scope(officer, b)
    assert not can_view_complaint(officer, b)
    assert not has_permission(officer, Permission.VERIFY_RESOLUTION, a)
    officer.explicit_permissions.add(Permission.VERIFY_RESOLUTION)
    assert has_permission(officer, Permission.VERIFY_RESOLUTION, a)
    assert has_permission(dadmin, Permission.VERIFY_RESOLUTION, a)
    assert not has_permission(dadmin, Permission.VERIFY_RESOLUTION, b)
    assert has_permission(sysadmin, Permission.DECIDE_REOPENING, b)
    # operational areas narrow an officer's view inside the unit
    ward1, ward2 = uuid.uuid4(), uuid.uuid4()
    area_officer = Actor(uuid.uuid4(), Role.OFFICER, "w", officer_active=True, unit_id=unit_a, area_ids=frozenset({ward1}))
    assert in_department_scope(area_officer, _C(uuid.uuid4(), unit_a, ward1))
    assert not in_department_scope(area_officer, _C(uuid.uuid4(), unit_a, ward2))
    with pytest.raises(ApiError):
        check_role_permissions(dadmin, {Role.SYSTEM_ADMIN})


# 8. filter_public_complaint
def test_filter_public_complaint_removes_private_fields():
    from types import SimpleNamespace
    from app.services.views import filter_public_complaint
    from app.models.enums import Category

    c = SimpleNamespace(reference_id="CVC-1", category=Category.DRAINAGE, public_summary="Blocked drain on 5th street",
                        status=S.RESOLVED_AWAITING_VERIFICATION, latitude=12.345678, longitude=77.987654,
                        jurisdiction=None, department=None, created_at=datetime.now(timezone.utc),
                        citizen=SimpleNamespace(full_name="Secret Name", email="s@x", phone="123"),
                        citizen_id=uuid.uuid4(), original_description="private text", media=["m"])
    out = filter_public_complaint(c)
    flat = str(out)
    for leaked in ("Secret Name", "s@x", "123", "private text", str(c.citizen_id), "storage", "media"):
        assert leaked not in flat
    assert out["generalized_location"]["latitude"] == 12.346
    assert out["resolution_type"] == "AUTHORITY_REPORTED"


# 9. validate_ai_output
VALID_AI = {
    "suggested_title": "Pothole on main road", "suggested_summary": "Deep pothole near bus stop.",
    "suggested_category": "ROAD_INFRASTRUCTURE", "extracted_issue": "pothole", "visible_evidence": [],
    "potential_safety_concerns": [], "missing_information": [], "classification_confidence": None,
    "confidence_band": "HIGH", "confidence_method": "model self-assessment band (not calibrated)",
    "media_analysis": [], "transcription": None, "requires_human_review": False, "review_reasons": [],
}


def test_valid_ai_output_accepted():
    a = validate_ai_output(VALID_AI, set())
    assert a.suggested_category.value == "ROAD_INFRASTRUCTURE" and a.requires_human_review is False


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("suggested_category"),
    lambda d: d.update(suggested_category="POTHOLES"),
    lambda d: d.update(classification_confidence=1.7),
    lambda d: d.update(confidence_band="UNAVAILABLE", classification_confidence=0.9),
    lambda d: d.update(extra_field="x"),
    lambda d: d.update(media_analysis=[{"media_id": "unknown", "media_type": "IMAGE", "extracted_description": "x",
                                        "confidence_band": "LOW"}]),
])
def test_invalid_ai_output_rejected(mutate):
    d = dict(VALID_AI)
    mutate(d)
    with pytest.raises(AIUnavailable) as e:
        validate_ai_output(d, set())
    assert e.value.code == "AI_INVALID_OUTPUT"


def test_ai_review_policy_enforced():
    d = dict(VALID_AI, confidence_band="LOW")
    assert validate_ai_output(d, set()).requires_human_review is True
    d = dict(VALID_AI, potential_safety_concerns=["exposed wires"])
    assert validate_ai_output(d, set()).requires_human_review is True
    with pytest.raises(AIUnavailable):
        validate_ai_output("not json", set())


# 10. generate_complaint_reference
def test_references_unique():
    refs = {generate_complaint_reference() for _ in range(2000)}
    assert len(refs) == 2000 and all(r.startswith("CVC-") for r in refs)


# AI provider adapter (OpenAI-compatible: xAI Grok / Groq / OpenAI), HTTP mocked
def _grok_env(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("AI_PROVIDER", "grok")
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL_NAME", "grok-test")
    monkeypatch.setenv("AI_MAX_RETRIES", "0")
    get_settings.cache_clear()
    return get_settings


def test_grok_adapter_analysis(monkeypatch):
    import json as _json
    import httpx
    from app.ai import ai_service
    gs = _grok_env(monkeypatch)
    seen = {}

    def fake_post(url, headers, timeout, json):
        seen.update(url=url, auth=headers["Authorization"], body=json)
        return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(VALID_AI)}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        assert ai_service.ai_status().mode == "configured"
        a = ai_service.analyze_complaint("Big pothole near the bus stop", [], {})
        assert a.suggested_category.value == "ROAD_INFRASTRUCTURE"
        assert seen["url"] == "https://api.x.ai/v1/chat/completions"
        assert seen["auth"] == "Bearer test-key" and seen["body"]["model"] == "grok-test"
        assert "<citizen_input>" in seen["body"]["messages"][1]["content"]
    finally:
        monkeypatch.undo()
        gs.cache_clear()


@pytest.mark.parametrize("status,code", [(401, "AI_PROVIDER_FAILURE"), (500, "AI_PROVIDER_FAILURE")])
def test_grok_adapter_http_errors(monkeypatch, status, code):
    import httpx
    from app.ai import ai_service
    gs = _grok_env(monkeypatch)
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: None)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(status, json={"error": "x"}))
    try:
        with pytest.raises(AIUnavailable) as e:
            ai_service.analyze_complaint("Big pothole near the bus stop", [], {})
        assert e.value.code == code
    finally:
        monkeypatch.undo()
        gs.cache_clear()


def test_grok_adapter_invalid_json_rejected(monkeypatch):
    import httpx
    from app.ai import ai_service
    gs = _grok_env(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={"choices": [{"message": {"content": "sure! here"}}]}))
    try:
        with pytest.raises(AIUnavailable) as e:
            ai_service.analyze_complaint("Big pothole near the bus stop", [], {})
        assert e.value.code == "AI_INVALID_OUTPUT"
    finally:
        monkeypatch.undo()
        gs.cache_clear()


def test_groq_qwen_image_cap_reasoning_and_think_stripping(monkeypatch):
    import json as _json
    import httpx
    from app.ai import ai_service
    from app.ai.ai_service import MediaInput
    gs = _grok_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_MODEL_NAME", "qwen/qwen3.8-27b")
    monkeypatch.setenv("AI_MAX_IMAGES", "3")
    monkeypatch.setenv("AI_REASONING_EFFORT", "none")
    gs.cache_clear()
    seen = {}

    def fake_post(url, headers, timeout, json):
        seen.update(url=url, body=json)
        content = "<think>looking at it</think>\n```json\n" + _json.dumps(VALID_AI) + "\n```"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        from app.core.config import get_settings
        from app.ai.providers import PROVIDERS
        prov = PROVIDERS["groq"](get_settings())
        imgs = [MediaInput(f"m{i}", "IMAGE", "image/jpeg", b"x") for i in range(5)]
        raw = prov.complete_structured("sys", "user", imgs)
        body = seen["body"]
        assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
        assert body["reasoning_effort"] == "none"
        assert sum(1 for c in body["messages"][1]["content"] if c["type"] == "image_url") == 3
        a = ai_service.validate_ai_output(raw)
        assert a.suggested_category.value == "ROAD_INFRASTRUCTURE"
    finally:
        monkeypatch.undo()
        gs.cache_clear()
