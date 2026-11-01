"""API integration tests against real PostgreSQL + PostGIS (spec 10.A, 10.C, 10.E)."""
import uuid

from sqlalchemy import func, select

from app.models import AuditLog, Complaint, Notification, StatusHistory
from tests.conftest import (
    INSIDE,
    OUTSIDE,
    auth,
    complaint_payload,
    create_complaint,
    make_user,
    png_bytes,
    register_citizen,
    wav_bytes,
)


# ---------- AC1 / AC2 / AC22 / AC24 / AC25 ----------
def test_auth_login_me_logout(client):
    token, user = register_citizen(client, email="ac1@example.com")
    r = client.post("/api/auth/login", json={"email": "ac1@example.com", "password": "password-123"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "CITIZEN"
    t = r.json()["access_token"]
    assert client.get("/api/auth/me", headers=auth(t)).json()["email"] == "ac1@example.com"
    assert client.post("/api/auth/logout", headers=auth(t)).status_code == 204
    r = client.get("/api/auth/me", headers=auth(t))
    assert r.status_code == 401 and r.json()["error_code"] == "UNAUTHENTICATED"
    bad = client.post("/api/auth/login", json={"email": "ac1@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401 and "password_hash" not in bad.text


def test_citizen_cannot_access_admin(client):
    token, _ = register_citizen(client)
    for path in ("/api/admin/departments", "/api/admin/audit-logs", "/api/admin/users", "/api/authority/dashboard"):
        r = client.get(path, headers=auth(token))
        assert r.status_code == 403, path
        assert r.json()["error_code"] == "FORBIDDEN" and "items" not in r.json()


def test_unauthenticated(client):
    r = client.get("/api/complaints")
    assert r.status_code == 401 and r.json()["error_code"] == "UNAUTHENTICATED"


def test_health_and_ready(client):
    assert client.get("/api/health").status_code == 200
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"


def test_ai_stub_never_fabricates(client):
    token, _ = register_citizen(client)
    status = client.get("/api/ai/status").json()
    assert status["mode"] == "stub"
    assert all(c["configured"] is False for c in status["capabilities"])
    r = client.post("/api/complaints/analyze", json={"description": "Streetlight broken near the park gate"}, headers=auth(token))
    assert r.status_code == 503
    body = r.json()
    assert body["error_code"] == "AI_NOT_CONFIGURED"
    for k in ("suggested_title", "suggested_category", "classification_confidence", "suggested_summary"):
        assert k not in body and k not in str(body.get("details"))
    assert "Traceback" not in r.text


# ---------- AC3 / AC4 / AC5 ----------
def test_empty_complaint_rejected(client, db):
    token, _ = register_citizen(client)
    r = client.post("/api/complaints", json=complaint_payload(description=None), headers=auth(token))
    assert r.status_code == 422 and r.json()["error_code"] == "EMPTY_COMPLAINT"
    r = client.post("/api/complaints/analyze", json={}, headers=auth(token))
    assert r.status_code == 422 and r.json()["error_code"] == "EMPTY_COMPLAINT"
    assert db.scalar(select(func.count()).select_from(Complaint)) == 0


def test_short_and_long_description(client):
    token, _ = register_citizen(client)
    assert client.post("/api/complaints", json=complaint_payload(description="tiny"), headers=auth(token)).json()["error_code"] == "DESCRIPTION_TOO_SHORT"
    assert client.post("/api/complaints", json=complaint_payload(description="x" * 3001), headers=auth(token)).json()["error_code"] == "DESCRIPTION_TOO_LONG"


def test_invalid_coordinates_rejected(client, db):
    token, _ = register_citizen(client)
    for loc in ({"latitude": 95, "longitude": 10, "location_source": "GPS"},
                {"latitude": 10, "longitude": -190, "location_source": "GPS"},
                {"latitude": None, "longitude": 10, "location_source": "GPS"}):
        r = client.post("/api/complaints", json=complaint_payload(location=loc), headers=auth(token))
        assert r.status_code == 422 and r.json()["error_code"] == "INVALID_COORDINATES", r.text
    assert db.scalar(select(func.count()).select_from(Complaint)) == 0


def test_media_validation(client):
    token, _ = register_citizen(client)
    r = client.post("/api/media/upload", files={"file": ("evil.png", b"MZ\x90\x00 not an image", "image/png")}, headers=auth(token))
    assert r.status_code == 415 and r.json()["error_code"] == "UNSUPPORTED_MEDIA_TYPE"
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 10)
    r = client.post("/api/media/upload", files={"file": ("big.png", big, "image/png")}, headers=auth(token))
    assert r.status_code == 413 and r.json()["error_code"] == "FILE_TOO_LARGE"
    corrupt = b"\x89PNG\r\n\x1a\n" + b"garbage" * 10
    r = client.post("/api/media/upload", files={"file": ("c.png", corrupt, "image/png")}, headers=auth(token))
    assert r.status_code == 422 and r.json()["error_code"] == "CORRUPT_MEDIA"
    r = client.post("/api/media/upload", files={"file": ("long.wav", wav_bytes(121), "audio/wav")}, headers=auth(token))
    assert r.status_code == 422 and r.json()["error_code"] == "MEDIA_DURATION_EXCEEDED"
    r = client.post("/api/media/upload", files={"file": ("ok.wav", wav_bytes(3), "audio/wav")}, headers=auth(token))
    assert r.status_code == 201 and r.json()["media_type"] == "AUDIO"


def test_too_many_images(client):
    token, _ = register_citizen(client)
    ids = [client.post("/api/media/upload", files={"file": (f"{i}.png", png_bytes(), "image/png")}, headers=auth(token)).json()["media_id"]
           for i in range(6)]
    r = client.post("/api/complaints", json=complaint_payload(media_ids=ids), headers={**auth(token), "Idempotency-Key": "k6"})
    assert r.status_code == 422 and r.json()["error_code"] == "TOO_MANY_IMAGES"


# ---------- AC6 / AC7 / AC8 / AC23 / S1 / S2 ----------
def test_create_complaint_with_photo_manual_mode(client, configured, db):
    token, _ = register_citizen(client)
    up = client.post("/api/media/upload", files={"file": ("p.png", png_bytes(), "image/png")}, headers=auth(token))
    assert up.status_code == 201
    mid = up.json()["media_id"]
    created = create_complaint(client, token, media_ids=[mid], original_description="pothole near bus stop, very deep!!")
    assert created["status"] == "ASSIGNED" and created["reference_id"].startswith("CVC-")  # auto-assigned to area officer
    assert created["routing_status"] == "ROUTED" and created["department"]["name"] == "Test Roads Dept"
    assert created["priority_assessment_status"] in ("PROVISIONAL", "UNAVAILABLE") and created["priority_score"] is None

    # persisted and visible after "re-login"
    t2 = client.post("/api/auth/login", json={"email": client.get("/api/auth/me", headers=auth(token)).json()["email"],
                                              "password": "password-123"}).json()["access_token"]
    lst = client.get("/api/complaints", headers=auth(t2)).json()
    assert lst["total"] == 1 and lst["items"][0]["reference_id"] == created["reference_id"]
    d = client.get(f"/api/complaints/{created['complaint_id']}", headers=auth(t2)).json()
    assert d["original_description"] == "pothole near bus stop, very deep!!"
    assert d["media"][0]["media_id"] == mid and "storage_key" not in str(d)
    assert d["timeline"][0]["new_status"] == "SUBMITTED"
    assert db.scalar(select(func.count()).select_from(StatusHistory)) == 3  # SUBMITTED, UNDER_REVIEW, ASSIGNED (automatic)

    # media retrievable by owner, not by another citizen
    assert client.get(f"/api/media/{mid}", headers=auth(t2)).status_code == 200
    other, _ = register_citizen(client)
    r = client.get(f"/api/media/{mid}", headers=auth(other))
    assert r.status_code == 404 and r.json()["error_code"] == "MEDIA_NOT_AVAILABLE"

    # AC8 ownership
    r = client.get(f"/api/complaints/{created['complaint_id']}", headers=auth(other))
    assert r.status_code == 404 and r.json()["error_code"] == "COMPLAINT_NOT_FOUND"
    assert client.get("/api/complaints", headers=auth(other)).json()["total"] == 0


def test_idempotent_creation(client, configured, db):
    token, _ = register_citizen(client)
    a = create_complaint(client, token, key="same-key")
    b = create_complaint(client, token, key="same-key")
    assert a["complaint_id"] == b["complaint_id"]
    assert db.scalar(select(func.count()).select_from(Complaint)) == 1
    r = client.post("/api/complaints", json=complaint_payload(title="A different complaint title"),
                    headers={**auth(token), "Idempotency-Key": "same-key"})
    assert r.status_code == 409 and r.json()["error_code"] == "DUPLICATE_SUBMISSION"


def test_complaint_requires_confirmation(client, configured):
    token, _ = register_citizen(client)
    r = client.post("/api/complaints", json=complaint_payload(confirmed=False), headers=auth(token))
    assert r.status_code == 422


# ---------- AC9 via API (FINAL priority with configured data) ----------
def test_priority_final_with_configured_sensitive_location(client, configured):
    at = configured["admin_token"]
    r = client.post("/api/admin/sensitive-locations", json={"label": "Test school gate", "location_type": "SCHOOL",
                                                            "latitude": 15.1, "longitude": 77.1, "radius_m": 200,
                                                            "sensitivity_score": 80}, headers=auth(at))
    assert r.status_code == 201
    token, _ = register_citizen(client)
    from datetime import datetime, timedelta, timezone
    c = create_complaint(client, token, observed_severity="SUBSTANTIAL", safety_risk="SIGNIFICANT", public_exposure="STREET",
                         occurred_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat())
    assert c["priority_assessment_status"] == "FINAL"
    # S=70 R=70 L=80 E=45 D(10 days)=41+ (3/7)*19 = 49.14
    expected = round(0.3 * 70 + 0.25 * 70 + 0.2 * 80 + 0.15 * 45 + 0.1 * 49.14, 2)
    assert abs(c["priority_score"] - expected) < 0.02 and c["priority_level"] == "HIGH"
    d = client.get(f"/api/complaints/{c['complaint_id']}", headers=auth(token)).json()
    assert d["priority"]["factors"]["location_sensitivity"]["source"] == "ADMIN_CONFIGURED_DATA"


def test_officer_confirms_missing_factor(client, configured):
    token, _ = register_citizen(client)
    c = create_complaint(client, token, observed_severity="SEVERE", safety_risk="LOW", public_exposure="STREET")
    assert c["priority_score"] is None
    r = client.post(f"/api/authority/complaints/{c['complaint_id']}/priority",
                    json={"location_sensitivity": 30, "duration": 10, "explanation": "Checked on site"},
                    headers=auth(configured["officer_token"]))
    assert r.status_code == 200, r.text
    p = r.json()["priority"]
    assert p["priority_assessment_status"] == "FINAL" and p["priority_score"] is not None
    assert p["factors"]["duration"]["source"] == "HUMAN_CONFIRMED"


# ---------- AC11 / AC12 / AC13 / S4 ----------
def test_routing_outcomes(client, configured, db):
    token, _ = register_citizen(client)
    at = configured["admin_token"]
    routed = create_complaint(client, token)
    c = db.get(Complaint, uuid.UUID(routed["complaint_id"]))
    assert c.routing_status.value == "ROUTED" and c.status.value == "ASSIGNED"
    assert str(c.department_unit_id) == configured["dept"]["units"][0]["id"] if configured["dept"].get("units") else True
    from app.models import Assignment
    a = db.scalar(select(Assignment))
    assert a.officer_id == configured["officer"].id and a.automatic and a.assigned_by is None and c.due_at is not None
    hist = client.get(f"/api/complaints/{c.id}/history", headers=auth(token)).json()
    assert [h["new_status"] for h in hist] == ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED"]

    outside = create_complaint(client, token, location=OUTSIDE)
    assert outside["routing_status"] == "PENDING_REVIEW" and outside["department"] is None
    assert "configured jurisdiction" in outside["routing_message"]

    unrouted = create_complaint(client, token, category="STREETLIGHT")
    assert unrouted["routing_status"] == "PENDING_REVIEW" and unrouted["department"] is None

    # second department becomes responsible for roads -> ambiguous
    client.post("/api/admin/responsibilities", json={"department_id": configured["other"]["id"], "category": "ROAD_INFRASTRUCTURE",
                                                     "source_reference": "Test"}, headers=auth(at))
    amb = create_complaint(client, token)
    assert amb["routing_status"] == "PENDING_REVIEW" and "Multiple departments" in amb["routing_message"]
    queue = client.get("/api/admin/routing-queue", headers=auth(at)).json()
    refs = {q["reference_id"]: q for q in queue}
    assert {amb["reference_id"], outside["reference_id"], unrouted["reference_id"]} <= set(refs)
    assert refs[unrouted["reference_id"]]["reason_code"] == "NO_RESPONSIBILITY"

    # admin resolves ambiguity; routing then assigns the area officer automatically
    r = client.post(f"/api/admin/complaints/{amb['complaint_id']}/routing",
                    json={"department_id": configured["dept"]["id"], "reason": "Road is municipal"}, headers=auth(at))
    assert r.status_code == 200 and r.json()["routing_status"] == "ROUTED", r.text
    assert db.get(Complaint, uuid.UUID(amb["complaint_id"])).status.value == "ASSIGNED"
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "ROUTING_DECISION")) >= 5


def test_no_officer_goes_to_unassigned_queue(client, configured, db):
    from app.models import Officer
    db.get(Officer, configured["officer"].id).active = False
    db.commit()
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    assert c["routing_status"] == "ROUTED" and c["status"] == "SUBMITTED"
    dt = configured["dadmin_token"]
    q = client.get("/api/authority/complaints?assignment=unassigned", headers=auth(dt)).json()
    assert q["total"] == 1
    n = client.get("/api/notifications", headers=auth(dt)).json()
    assert any(i["notification_type"] == "AWAITING_ASSIGNMENT" for i in n["items"])
    assert client.get("/api/authority/dashboard", headers=auth(dt)).json()["awaiting_assignment"] == 1


def test_uncertain_gps_goes_to_review(client, configured):
    token, _ = register_citizen(client)
    c = create_complaint(client, token, location={**INSIDE, "location_source": "GPS", "accuracy_meters": 2000})
    assert c["routing_status"] == "PENDING_REVIEW"


# ---------- AC14 / S3 ----------
def test_duplicate_detection(client, configured, db):
    t1, _ = register_citizen(client)
    t2, _ = register_citizen(client)
    a = create_complaint(client, t1)
    b = create_complaint(client, t2, location={**INSIDE, "latitude": 15.1003},
                         description="Deep pothole near the bus stop, two-wheelers are swerving to avoid it.")
    assert b["related_candidates"] == 1
    assert db.scalar(select(func.count()).select_from(Complaint)) == 2  # nothing merged/deleted
    rel = client.get(f"/api/complaints/{b['complaint_id']}/related", headers=auth(configured["officer_token"])).json()
    assert len(rel) == 1 and rel[0]["reference_id"] == a["reference_id"] and rel[0]["match_reasons"]
    assert rel[0]["relationship_status"] == "SUGGESTED"
    # citizen 2 does not see citizen 1's complaint via related
    d = client.get(f"/api/complaints/{b['complaint_id']}", headers=auth(t2)).json()
    assert a["reference_id"] not in str(d["related"])
    r = client.post(f"/api/complaints/{b['complaint_id']}/relationships",
                    json={"related_complaint_id": a["complaint_id"], "relationship_status": "CONFIRMED_RELATED"},
                    headers=auth(configured["officer_token"]))
    assert r.status_code == 200 and r.json()["relationship_status"] == "CONFIRMED_RELATED"
    far = create_complaint(client, t2, location={**INSIDE, "latitude": 15.15})
    assert far["related_candidates"] == 0


# ---------- AC15-AC18, AC26, S5 ----------
def _to_in_progress(client, cfg, cid):
    ot = cfg["officer_token"]
    r = client.post(f"/api/authority/complaints/{cid}/accept", headers=auth(ot))
    assert r.status_code == 200 and r.json()["status"] == "ASSIGNED", r.text
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "IN_PROGRESS", "remarks": "Crew dispatched"}, headers=auth(ot))
    assert r.status_code == 200, r.text


def test_full_department_workflow(client, configured, db):
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    cid = c["complaint_id"]
    ot, dt = configured["officer_token"], configured["dadmin_token"]
    assert c["status"] == "ASSIGNED"

    # AC16 invalid transitions
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "VERIFIED_RESOLVED"}, headers=auth(ot))
    assert r.status_code == 409 and r.json()["error_code"] == "INVALID_STATUS_TRANSITION"
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "UNDER_REVIEW"}, headers=auth(ot))
    assert r.status_code == 409
    assert db.get(Complaint, uuid.UUID(cid)).status.value == "ASSIGNED"

    # AC17 isolation: other department cannot see or act
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "IN_PROGRESS"}, headers=auth(configured["other_officer_token"]))
    assert r.status_code == 404
    assert client.get("/api/authority/complaints", headers=auth(configured["other_officer_token"])).json()["total"] == 0
    assert client.get("/api/authority/complaints", headers=auth(ot)).json()["total"] == 1

    # citizen cannot use authority endpoints
    assert client.post(f"/api/authority/complaints/{cid}/status", json={"status": "IN_PROGRESS"}, headers=auth(token)).status_code == 403

    # officers accept but cannot (re)assign; only the department administrator assigns
    assert client.post(f"/api/authority/complaints/{cid}/accept", headers=auth(ot)).status_code == 200
    assert client.post(f"/api/authority/complaints/{cid}/accept", headers=auth(ot)).json()["error_code"] == "ALREADY_UPDATED"
    from app.models.enums import Role
    _, _, second = make_user(db, Role.OFFICER, uuid.UUID(configured["dept"]["id"]), "Senior engineer")
    r = client.post(f"/api/authority/complaints/{cid}/assign", json={"officer_id": str(second.id), "reason": "x" * 6}, headers=auth(ot))
    assert r.status_code == 403

    # E26 ineligible officer (other department)
    _, _, foreign_officer = make_user(db, Role.OFFICER, uuid.UUID(configured["other"]["id"]))
    r = client.post(f"/api/authority/complaints/{cid}/assign", json={"officer_id": str(foreign_officer.id), "reason": "wrong"}, headers=auth(dt))
    assert r.status_code == 422 and r.json()["error_code"] == "INVALID_ASSIGNMENT"
    # reassignment needs reason (E28)
    r = client.post(f"/api/authority/complaints/{cid}/assign", json={"officer_id": str(second.id)}, headers=auth(dt))
    assert r.status_code == 422 and r.json()["error_code"] == "REASON_REQUIRED"
    r = client.post(f"/api/authority/complaints/{cid}/assign", json={"officer_id": str(second.id),
                                                                     "reason": "Senior engineer needed"}, headers=auth(dt))
    assert r.status_code == 200
    r = client.post(f"/api/authority/complaints/{cid}/assign", json={"officer_id": str(configured["officer"].id),
                                                                     "reason": "Back to the area officer"}, headers=auth(dt))
    assert r.status_code == 200
    hist = client.get(f"/api/authority/complaints/{cid}", headers=auth(dt)).json()["assignments"]
    assert len(hist) == 3

    # ON_HOLD requires reason
    client.post(f"/api/authority/complaints/{cid}/status", json={"status": "IN_PROGRESS"}, headers=auth(ot))
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "ON_HOLD"}, headers=auth(ot))
    assert r.status_code == 422 and r.json()["error_code"] == "REASON_REQUIRED"
    assert client.post(f"/api/authority/complaints/{cid}/status", json={"status": "ON_HOLD", "reason": "Awaiting materials"},
                       headers=auth(ot)).status_code == 200
    client.post(f"/api/authority/complaints/{cid}/status", json={"status": "IN_PROGRESS"}, headers=auth(ot))

    # cannot mark resolved without evidence
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "RESOLVED_AWAITING_VERIFICATION"}, headers=auth(ot))
    assert r.status_code == 409 and r.json()["error_code"] == "EVIDENCE_REQUIRED"

    # remarks: internal vs citizen-visible
    client.post(f"/api/authority/complaints/{cid}/remarks", json={"text": "INTERNAL-ONLY note", "visibility": "INTERNAL"}, headers=auth(ot))
    client.post(f"/api/authority/complaints/{cid}/remarks", json={"text": "Work scheduled tomorrow", "visibility": "CITIZEN"}, headers=auth(ot))

    # AC18 evidence
    r = client.post(f"/api/authority/complaints/{cid}/evidence", files={"file": ("after.png", png_bytes(), "image/png")},
                    data={"description": "Pothole filled"}, headers=auth(ot))
    assert r.status_code == 201, r.text
    ev_media = r.json()["media_id"]
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "RESOLVED_AWAITING_VERIFICATION",
                                                                     "remarks": "Repaired"}, headers=auth(ot))
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED_AWAITING_VERIFICATION"

    citizen_view = client.get(f"/api/complaints/{cid}", headers=auth(token)).json()
    assert "INTERNAL-ONLY" not in str(citizen_view)
    assert "Work scheduled tomorrow" in str(citizen_view)
    assert citizen_view["resolution_evidence"][0]["description"] == "Pothole filled"
    assert client.get(f"/api/media/{ev_media}", headers=auth(token)).status_code == 200
    link = client.get(f"/api/media/{ev_media}/link", headers=auth(token)).json()["url"]
    assert client.get(link.replace("http://localhost:8000", "")).status_code == 200
    staff_view = client.get(f"/api/authority/complaints/{cid}", headers=auth(ot)).json()
    assert "INTERNAL-ONLY" in str(staff_view)

    statuses = [h["new_status"] for h in client.get(f"/api/complaints/{cid}/history", headers=auth(token)).json()]
    assert statuses == ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "ON_HOLD", "IN_PROGRESS", "RESOLVED_AWAITING_VERIFICATION"]
    # never auto-verified
    assert db.get(Complaint, uuid.UUID(cid)).status.value == "RESOLVED_AWAITING_VERIFICATION"
    # AC26 audit
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == cid)))
    assert {"STATUS_CHANGED", "COMPLAINT_ASSIGNED", "COMPLAINT_REASSIGNED", "EVIDENCE_UPLOADED"} <= actions
    # citizen notifications without duplicates
    types = list(db.scalars(select(Notification.notification_type).join(Complaint, Complaint.id == Notification.complaint_id)
                            .where(Notification.recipient_id == Complaint.citizen_id)))
    assert "STATUS_RESOLVED_AWAITING_VERIFICATION" in types and types.count("STATUS_UNDER_REVIEW") == 1


def test_optimistic_concurrency(client, configured):
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    r = client.post(f"/api/authority/complaints/{c['complaint_id']}/status", json={"status": "IN_PROGRESS", "expected_version": 99},
                    headers=auth(configured["officer_token"]))
    assert r.status_code == 409 and r.json()["error_code"] == "CONCURRENT_UPDATE"


# ---------- AC19, AC35-AC39, S6, S9 ----------
def _resolved(client, cfg):
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    cid = c["complaint_id"]
    _to_in_progress(client, cfg, cid)
    ev = client.post(f"/api/authority/complaints/{cid}/evidence", files={"file": ("a.png", png_bytes(), "image/png")},
                     headers=auth(cfg["officer_token"])).json()
    client.post(f"/api/authority/complaints/{cid}/status", json={"status": "RESOLVED_AWAITING_VERIFICATION"}, headers=auth(cfg["officer_token"]))
    return token, cid, ev["evidence_id"]


def test_verification_policy(client, configured, db):
    token, cid, ev = _resolved(client, configured)
    # officer lacks VERIFY_RESOLUTION
    r = client.post(f"/api/authority/complaints/{cid}/verify", json={"decision": "APPROVED", "reason": "Looks fixed",
                                                                     "evidence_reviewed": [ev]}, headers=auth(configured["officer_token"]))
    assert r.status_code == 403
    # status endpoint can't bypass
    r = client.post(f"/api/authority/complaints/{cid}/status", json={"status": "VERIFIED_RESOLVED"}, headers=auth(configured["dadmin_token"]))
    assert r.status_code == 409
    # citizen confirmation is only a signal (AC19)
    r = client.post(f"/api/complaints/{cid}/feedback", json={"feedback_type": "CONFIRMED_RESOLVED"}, headers=auth(token))
    assert r.status_code == 201 and r.json()["review_status"] == "NOT_REQUIRED"
    assert db.get(Complaint, uuid.UUID(cid)).status.value == "RESOLVED_AWAITING_VERIFICATION"
    # dept admin verifies (AC38)
    r = client.post(f"/api/authority/complaints/{cid}/verify", json={"decision": "APPROVED", "reason": "Site photo reviewed",
                                                                     "evidence_reviewed": [ev]}, headers=auth(configured["dadmin_token"]))
    assert r.status_code == 200 and r.json()["status"] == "VERIFIED_RESOLVED"
    vd = r.json()["verification_decisions"][0]
    assert vd["reason"] == "Site photo reviewed" and vd["citizen_responded"] is True


def test_reopen_accept_and_reject(client, configured, db):
    token, cid, ev = _resolved(client, configured)
    # E31: ineligible before resolution handled; here eligible
    r = client.post(f"/api/complaints/{cid}/feedback", json={"feedback_type": "NOT_RESOLVED", "remarks": "Still a hole"}, headers=auth(token))
    assert r.status_code == 201 and r.json()["review_status"] == "PENDING"
    assert db.get(Complaint, uuid.UUID(cid)).status.value == "RESOLVED_AWAITING_VERIFICATION"  # AC35 unchanged
    fid = r.json()["feedback_id"]
    # duplicate pending request rejected
    assert client.post(f"/api/complaints/{cid}/feedback", json={"feedback_type": "REOPEN_REQUEST", "remarks": "again"},
                       headers=auth(token)).status_code == 409
    # officer cannot decide
    assert client.post(f"/api/authority/feedback/{fid}/review", json={"decision": "ACCEPTED", "reason": "okay"},
                       headers=auth(configured["officer_token"])).status_code == 403
    # verification blocked while reopen pending
    assert client.post(f"/api/authority/complaints/{cid}/verify", json={"decision": "APPROVED", "reason": "x" * 5,
                       "evidence_reviewed": [ev]}, headers=auth(configured["dadmin_token"])).status_code == 409
    # reject (AC37)
    r = client.post(f"/api/authority/feedback/{fid}/review", json={"decision": "REJECTED", "reason": "Photo shows repair"},
                    headers=auth(configured["dadmin_token"]))
    assert r.status_code == 200 and r.json()["review_status"] == "REJECTED" and r.json()["reviewed_by"]
    assert db.get(Complaint, uuid.UUID(cid)).status.value == "RESOLVED_AWAITING_VERIFICATION"
    citizen = client.get(f"/api/complaints/{cid}", headers=auth(token)).json()
    assert citizen["feedback"][0]["decision_reason"] == "Photo shows repair"
    # second request, accepted (AC36)
    fid2 = client.post(f"/api/complaints/{cid}/feedback", json={"feedback_type": "REOPEN_REQUEST", "remarks": "It is back"},
                       headers=auth(token)).json()["feedback_id"]
    r = client.post(f"/api/authority/feedback/{fid2}/review", json={"decision": "ACCEPTED", "reason": "Confirmed on site"},
                    headers=auth(configured["dadmin_token"]))
    assert r.status_code == 200
    assert db.get(Complaint, uuid.UUID(cid)).status.value == "REOPENED"
    # decided item cannot be decided again
    assert client.post(f"/api/authority/feedback/{fid2}/review", json={"decision": "REJECTED", "reason": "x" * 5},
                       headers=auth(configured["dadmin_token"])).status_code == 409
    # back into review workflow
    r = client.post(f"/api/authority/complaints/{cid}/assign", json={"officer_id": str(configured["officer"].id)},
                    headers=auth(configured["dadmin_token"]))
    assert r.status_code == 200 and r.json()["status"] == "ASSIGNED", r.text
    assert {"REOPEN_REVIEW_DECISION"} <= set(db.scalars(select(AuditLog.action).where(AuditLog.entity_id == cid)))


def test_reopen_ineligible(client, configured):
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    r = client.post(f"/api/complaints/{c['complaint_id']}/feedback", json={"feedback_type": "REOPEN_REQUEST", "remarks": "x"}, headers=auth(token))
    assert r.status_code == 409 and r.json()["error_code"] == "REOPEN_NOT_ALLOWED"


# ---------- AC20 / AC21 / S7 ----------
def test_public_privacy_and_real_statistics(client, configured, db):
    assert client.get("/api/public/analytics").json()["total_public"] == 0  # empty state, not invented
    assert client.get("/api/public/complaints").json()["items"] == []
    token, user = register_citizen(client, name="Private Person")
    ids = []
    for i in range(3):
        ids.append(create_complaint(client, token, title=f"Pothole number {i} here")["complaint_id"])
    ot = configured["officer_token"]
    client.post(f"/api/authority/complaints/{ids[0]}/remarks", json={"text": "SECRET internal", "visibility": "INTERNAL"}, headers=auth(ot))
    # not public until privacy review
    assert client.get("/api/public/complaints").json()["total"] == 0
    for cid in ids[:2]:
        r = client.post(f"/api/authority/complaints/{cid}/publication", json={"approve": True, "public_summary": "Pothole reported on a main road"},
                        headers=auth(ot))
        assert r.status_code == 200
    pub = client.get("/api/public/complaints").json()
    assert pub["total"] == 2
    text = str(pub) + str(client.get("/api/public/map").json())
    for leaked in ("Private Person", user["email"], "SECRET internal", "media_id", "storage", user["id"], "citizen"):
        assert leaked not in text
    stats = client.get("/api/public/analytics").json()
    assert stats["total_public"] == 2 and stats["by_category"] == {"ROAD_INFRASTRUCTURE": 2}
    assert stats["trend_weekly"] is None and stats["trend_note"]
    # authority dashboard counts match records
    dash = client.get("/api/authority/dashboard", headers=auth(ot)).json()
    assert dash["total"] == 3 and dash["assigned"] == 3 and dash["assigned_to_me"] == 3
    summary = client.get("/api/complaints/summary", headers=auth(token)).json()
    assert summary["total"] == 3 and summary["in_progress"] == 3
    # rejected complaints are not public
    client.post(f"/api/authority/complaints/{ids[1]}/status", json={"status": "REJECTED", "reason": "Not a civic issue"}, headers=auth(ot))
    assert client.get("/api/public/complaints").json()["total"] == 1


# ---------- admin config & audit ----------
def test_admin_config_audited(client, admin, db):
    at = admin[0]
    r = client.post("/api/admin/priority-config", json={"config": {"weights": {"severity": 1}}}, headers=auth(at))
    assert r.status_code == 422
    r = client.post("/api/admin/priority-config", json={"config": {"weights": {"severity": 0.2, "safety_risk": 0.3,
                    "location_sensitivity": 0.2, "public_exposure": 0.2, "duration": 0.1}}}, headers=auth(at))
    assert r.status_code == 201 and r.json()["version"] == 1
    r = client.post("/api/admin/jurisdictions", json={"name": "Bad", "boundary": {"type": "Point", "coordinates": [0, 0]}}, headers=auth(at))
    assert r.status_code == 422
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    r = client.post("/api/admin/jurisdictions", json={"name": "Bowtie", "boundary": bowtie}, headers=auth(at))
    assert r.status_code == 422
    staff = client.post("/api/admin/users", json={"full_name": "New Officer", "email": "newofficer@example.com",
                                                  "password": "password-123", "role": "OFFICER"}, headers=auth(at))
    assert staff.status_code == 422  # department required
    dept = client.post("/api/admin/departments", json={"name": "Roads Audit Dept"}, headers=auth(at))
    assert dept.status_code == 201
    logs = client.get("/api/admin/audit-logs", headers=auth(at)).json()
    assert any(l["action"] == "PRIORITY_CONFIG_CHANGED" for l in logs["items"])
    created = next(l for l in logs["items"] if l["action"] == "DEPARTMENT_CREATED")
    assert created["entity_name"] == "Roads Audit Dept"
    assert created["actor_name"] and "(System Admin)" in created["actor_name"]


def test_error_shape(client):
    r = client.get(f"/api/complaints/{uuid.uuid4()}")
    body = r.json()
    assert set(body) == {"error_code", "message", "details", "request_id"} and body["request_id"]
