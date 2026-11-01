"""Administrative architecture: hierarchy, registry, mapping, verification, safe delete,
district isolation, operational-area routing and escalation."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Complaint, Escalation
from app.models.enums import Role
from tests.conftest import auth, create_complaint, make_user, register_citizen

STATE = {"type": "Polygon", "coordinates": [[[76.0, 14.0], [78.0, 14.0], [78.0, 16.0], [76.0, 16.0], [76.0, 14.0]]]}
DIST_A = {"type": "Polygon", "coordinates": [[[76.0, 14.0], [77.0, 14.0], [77.0, 16.0], [76.0, 16.0], [76.0, 14.0]]]}
DIST_B = {"type": "Polygon", "coordinates": [[[77.0, 14.0], [78.0, 14.0], [78.0, 16.0], [77.0, 16.0], [77.0, 14.0]]]}
WARD_A1 = {"type": "Polygon", "coordinates": [[[76.0, 14.0], [76.5, 14.0], [76.5, 15.0], [76.0, 15.0], [76.0, 14.0]]]}
WARD_A2 = {"type": "Polygon", "coordinates": [[[76.5, 14.0], [77.0, 14.0], [77.0, 15.0], [76.5, 15.0], [76.5, 14.0]]]}
IN_A1 = {"latitude": 14.5, "longitude": 76.25, "location_source": "MAP_SELECTION"}
IN_A2 = {"latitude": 14.5, "longitude": 76.75, "location_source": "MAP_SELECTION"}
IN_B = {"latitude": 15.0, "longitude": 77.5, "location_source": "MAP_SELECTION"}


def _post(client, at, path, body, code=201):
    r = client.post(path, json=body, headers=auth(at))
    assert r.status_code == code, r.text
    return r.json()


def _hierarchy(client, at):
    s = _post(client, at, "/api/admin/jurisdictions", {"name": "State", "jurisdiction_type": "STATE", "boundary": STATE})
    a = _post(client, at, "/api/admin/jurisdictions", {"name": "District A", "jurisdiction_type": "DISTRICT",
                                                      "parent_id": s["id"], "boundary": DIST_A})
    b = _post(client, at, "/api/admin/jurisdictions", {"name": "District B", "jurisdiction_type": "DISTRICT",
                                                      "parent_id": s["id"], "boundary": DIST_B})
    a1 = _post(client, at, "/api/admin/jurisdictions", {"name": "Ward A1", "jurisdiction_type": "WARD",
                                                       "parent_id": a["id"], "boundary": WARD_A1})
    a2 = _post(client, at, "/api/admin/jurisdictions", {"name": "Ward A2", "jurisdiction_type": "WARD",
                                                       "parent_id": a["id"], "boundary": WARD_A2})
    return s, a, b, a1, a2


def test_verification_status_rules(client, admin):
    at = admin[0]
    d1 = _post(client, at, "/api/admin/departments", {"name": "Roads", "source_reference": "Municipal Act s.58"})
    d2 = _post(client, at, "/api/admin/departments", {"name": "Water"})
    d3 = _post(client, at, "/api/admin/departments", {"name": "Parks", "source_reference": "x", "is_prototype": True})
    assert (d1["verification_status"], d2["verification_status"], d3["verification_status"]) == \
        ("VERIFIED", "PENDING_VERIFICATION", "PROTOTYPE")
    # editing an unrelated field does not change status; adding a source reference verifies
    r = client.patch(f"/api/admin/departments/{d3['id']}", json={"description": "Gardens"}, headers=auth(at)).json()
    assert r["verification_status"] == "PROTOTYPE"
    r = client.patch(f"/api/admin/departments/{d2['id']}", json={"source_reference": "Water Board Act"}, headers=auth(at)).json()
    assert r["verification_status"] == "VERIFIED"
    j = _post(client, at, "/api/admin/jurisdictions", {"name": "Ward X", "jurisdiction_type": "ward"})
    assert j["verification_status"] == "PENDING_VERIFICATION" and j["jurisdiction_type"] == "WARD" and not j["has_boundary"]
    refs = client.get("/api/admin/source-references", headers=auth(at)).json()
    assert refs["counts"] == {"VERIFIED": 2, "PROTOTYPE": 1, "PENDING_VERIFICATION": 1}


def test_hierarchy_cycle_and_tree(client, admin):
    at = admin[0]
    s, a, b, a1, a2 = _hierarchy(client, at)
    tree = client.get("/api/admin/jurisdictions?boundaries=false", headers=auth(at)).json()
    assert [t["name"] for t in tree] == ["State", "District A", "Ward A1", "Ward A2", "District B"]
    assert next(t for t in tree if t["name"] == "Ward A1")["path"] == "State › District A › Ward A1"
    r = client.patch(f"/api/admin/jurisdictions/{s['id']}", json={"parent_id": a1["id"]}, headers=auth(at))
    assert r.status_code == 422


def test_safe_delete(client, admin, db):
    at = admin[0]
    s, a, b, a1, a2 = _hierarchy(client, at)
    roads = _post(client, at, "/api/admin/departments", {"name": "Roads"})
    unused = _post(client, at, "/api/admin/departments", {"name": "Unused"})
    unit = _post(client, at, "/api/admin/units", {"department_id": roads["id"], "jurisdiction_id": a["id"]})
    # duplicate mapping rejected
    assert client.post("/api/admin/units", json={"department_id": roads["id"], "jurisdiction_id": a["id"]},
                       headers=auth(at)).status_code == 409

    # a jurisdiction with children is blocked
    deps = client.get(f"/api/admin/jurisdictions/{a['id']}/dependencies", headers=auth(at)).json()
    assert not deps["can_delete"] and any(x["label"] == "Sub-jurisdictions" for x in deps["blocking"])
    r = client.delete(f"/api/admin/jurisdictions/{a['id']}", headers=auth(at))
    assert r.status_code == 409 and r.json()["error_code"] == "DELETE_BLOCKED"

    # unused department deletes; leaf ward deletes
    assert client.delete(f"/api/admin/departments/{unused['id']}", headers=auth(at)).status_code == 200
    assert client.delete(f"/api/admin/jurisdictions/{a2['id']}", headers=auth(at)).status_code == 200

    # personnel block department and unit deletion
    make_user(db, Role.OFFICER, unit_id=uuid.UUID(unit["id"]))
    deps = client.get(f"/api/admin/departments/{roads['id']}/dependencies", headers=auth(at)).json()
    assert not deps["can_delete"] and deps["removed_with_it"][0]["label"] == "Department-jurisdiction mappings"
    assert client.delete(f"/api/admin/departments/{roads['id']}", headers=auth(at)).status_code == 409
    assert client.delete(f"/api/admin/units/{unit['id']}", headers=auth(at)).status_code == 409
    # deactivation is always possible
    r = client.patch(f"/api/admin/departments/{roads['id']}", json={"active": False}, headers=auth(at))
    assert r.status_code == 200 and r.json()["active"] is False


def _two_districts(client, at, db):
    s, a, b, a1, a2 = _hierarchy(client, at)
    roads = _post(client, at, "/api/admin/departments", {"name": "Roads", "source_reference": "Act"})
    _post(client, at, "/api/admin/responsibilities", {"department_id": roads["id"], "category": "ROAD_INFRASTRUCTURE",
                                                     "name": "Pothole repair"}, 200)
    ua = _post(client, at, "/api/admin/units", {"department_id": roads["id"], "jurisdiction_id": a["id"]})
    ub = _post(client, at, "/api/admin/units", {"department_id": roads["id"], "jurisdiction_id": b["id"]})
    officer_a1 = _post(client, at, "/api/admin/users", {"full_name": "Officer A1", "email": "oa1@example.com",
                                                         "password": "password-123", "role": "OFFICER", "unit_id": ua["id"],
                                                         "area_jurisdiction_ids": [a1["id"]]})
    officer_a2 = _post(client, at, "/api/admin/users", {"full_name": "Officer A2", "email": "oa2@example.com",
                                                         "password": "password-123", "role": "OFFICER", "unit_id": ua["id"],
                                                         "area_jurisdiction_ids": [a2["id"]]})
    _post(client, at, "/api/admin/users", {"full_name": "Admin A", "email": "da@example.com", "password": "password-123",
                                           "role": "DEPARTMENT_ADMIN", "unit_id": ua["id"]})
    _post(client, at, "/api/admin/users", {"full_name": "Admin B", "email": "db@example.com", "password": "password-123",
                                           "role": "DEPARTMENT_ADMIN", "unit_id": ub["id"]})
    tokens = {k: client.post("/api/auth/login", json={"email": f"{k}@example.com", "password": "password-123"}).json()["access_token"]
              for k in ("oa1", "oa2", "da", "db")}
    return {"a1": a1, "a2": a2, "b": b, "ua": ua, "ub": ub, "officer_a1": officer_a1, "officer_a2": officer_a2, **tokens}


def test_area_routing_and_district_isolation(client, admin, db):
    at = admin[0]
    w = _two_districts(client, at, db)
    # areas must be inside the unit
    r = client.post("/api/admin/users", json={"full_name": "Bad", "email": "bad@example.com", "password": "password-123",
                                              "role": "OFFICER", "unit_id": w["ua"]["id"], "area_jurisdiction_ids": [w["b"]["id"]]},
                    headers=auth(at))
    assert r.status_code == 422

    token, _ = register_citizen(client)
    c1 = create_complaint(client, token, location=IN_A1)
    c2 = create_complaint(client, token, location=IN_A2)
    cb = create_complaint(client, token, location=IN_B)
    assert c1["status"] == c2["status"] == "ASSIGNED"
    assert cb["status"] == "SUBMITTED" and cb["routing_status"] == "ROUTED"  # District B has no officers yet

    d1 = client.get(f"/api/authority/complaints/{c1['complaint_id']}", headers=auth(w["da"])).json()
    assert "Officer A1" in str(d1["assignments"]) and d1["assignments"][0]["automatic"]
    # officers see only their area; District A admin sees A only; District B admin sees B only
    refs = lambda t: {i["reference_id"] for i in client.get("/api/authority/complaints", headers=auth(t)).json()["items"]}  # noqa: E731
    assert refs(w["oa1"]) == {c1["reference_id"]}
    assert refs(w["oa2"]) == {c2["reference_id"]}
    assert refs(w["da"]) == {c1["reference_id"], c2["reference_id"]}
    assert refs(w["db"]) == {cb["reference_id"]}
    assert client.get(f"/api/authority/complaints/{cb['complaint_id']}", headers=auth(w["da"])).status_code == 404
    assert client.get(f"/api/authority/complaints/{c1['complaint_id']}", headers=auth(w["oa2"])).status_code == 404

    # District B admin sees the unassigned complaint in the queue but cannot assign an officer from District A
    assert client.get("/api/authority/complaints?assignment=unassigned", headers=auth(w["db"])).json()["total"] == 1
    r = client.post(f"/api/authority/complaints/{cb['complaint_id']}/assign",
                    json={"officer_id": w["officer_a1"]["officer"]["officer_id"]}, headers=auth(w["db"]))
    assert r.status_code == 422


def test_escalation_overdue_and_manual(client, admin, db):
    at = admin[0]
    w = _two_districts(client, at, db)
    token, _ = register_citizen(client)
    c = create_complaint(client, token, location=IN_A1)
    # manual escalation by the officer goes to the department administrator (level 1)
    r = client.post(f"/api/authority/complaints/{c['complaint_id']}/escalate", json={"reason": "Needs road closure"},
                    headers=auth(w["oa1"]))
    assert r.status_code == 201 and r.json()["level"] == 1
    esc = client.get("/api/authority/escalations", headers=auth(w["da"])).json()
    assert len(esc) == 1 and esc[0]["can_resolve"]
    assert client.get("/api/authority/escalations", headers=auth(w["db"])).json() == []
    assert client.post(f"/api/authority/escalations/{esc[0]['id']}/resolve", json={"note": "Closure approved"},
                       headers=auth(w["da"])).status_code == 200

    # overdue complaint escalates automatically, once
    row = db.get(Complaint, uuid.UUID(c["complaint_id"]))
    row.due_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()
    dash = client.get("/api/authority/dashboard", headers=auth(w["da"])).json()
    assert dash["overdue"] == 1 and dash["escalated"] == 1
    client.get("/api/authority/dashboard", headers=auth(w["da"]))
    db.expire_all()
    assert len(db.scalars(select(Escalation).where(Escalation.reason_code == "OVERDUE")).all()) == 1
    n = client.get("/api/notifications", headers=auth(w["da"])).json()
    assert any(i["notification_type"] == "ESCALATED" for i in n["items"])
    # long overdue -> level 2 to the main administration
    row.due_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()
    client.get("/api/authority/dashboard", headers=auth(w["da"]))
    db.expire_all()
    assert {e.level for e in db.scalars(select(Escalation).where(Escalation.reason_code == "OVERDUE"))} == {1, 2}
    admin_esc = client.get("/api/authority/escalations?level=2", headers=auth(at)).json()
    assert len(admin_esc) == 1 and admin_esc[0]["can_resolve"]


def test_overview_and_public_issue_workflow(client, admin, db):
    at = admin[0]
    w = _two_districts(client, at, db)
    token, citizen = register_citizen(client, name="Private Citizen")
    c1 = create_complaint(client, token, location=IN_A1)
    c2 = create_complaint(client, token, location={**IN_A1, "latitude": 14.5005})
    cb = create_complaint(client, token, location=IN_B)

    ov = client.get("/api/admin/overview", headers=auth(at)).json()
    assert ov["totals"]["total"] == 3 and ov["totals"]["under_investigation"] == 2 and ov["totals"]["awaiting_assignment"] == 1
    assert ov["by_department"] == [{"department": "Roads", "count": 3}]
    assert any(u["label"] == "Roads — District B" for u in ov["attention"]["units_without_officers"])
    assert "ai" not in str(ov.keys()) and len(ov["trend_weekly"]) == 12
    assert client.get("/api/admin/overview", headers=auth(w["da"])).status_code == 403

    # officer drafts an issue linking two complaints; cannot link another district's complaint
    r = client.post("/api/authority/public-issues", json={"title": "Potholes on Station Road", "description": "Several deep potholes reported.",
                                                         "general_location": "Station Road", "complaint_ids": [c1["complaint_id"], cb["complaint_id"]]},
                    headers=auth(w["oa1"]))
    assert r.status_code == 422
    issue = _post(client, w["oa1"], "/api/authority/public-issues",
                  {"title": "Potholes on Station Road", "description": "Several deep potholes reported.",
                   "general_location": "Station Road", "complaint_ids": [c1["complaint_id"]]})
    issue = _post(client, w["da"], f"/api/authority/public-issues/{issue['id']}/complaints",
                  {"complaint_ids": [c2["complaint_id"]]}, 200)
    assert issue["related_complaints"] == 2
    # cannot publish before verification; officer cannot publish
    assert client.post(f"/api/authority/public-issues/{issue['id']}/publish", headers=auth(w["oa1"])).status_code == 403
    assert client.post(f"/api/authority/public-issues/{issue['id']}/publish", headers=auth(w["da"])).status_code == 409
    _post(client, w["da"], f"/api/authority/public-issues/{issue['id']}/verify",
          {"impact_level": "HIGH", "impact_assessment": "Main bus route, affects many commuters."}, 200)
    assert client.get("/api/public/issues").json()["total"] == 0
    _post(client, w["da"], f"/api/authority/public-issues/{issue['id']}/publish", {}, 200)
    _post(client, w["oa1"], f"/api/authority/public-issues/{issue['id']}/updates",
          {"message": "Repair crew scheduled", "progress": "IN_PROGRESS"})
    # District B admin cannot see it
    assert client.get(f"/api/authority/public-issues/{issue['id']}", headers=auth(w["db"])).status_code == 404

    pub = client.get("/api/public/issues").json()
    assert pub["total"] == 1 and pub["items"][0]["related_complaints"] == 2 and pub["items"][0]["progress"] == "IN_PROGRESS"
    detail = client.get(f"/api/public/issues/{issue['id']}").json()
    text = str(pub) + str(detail)
    for leaked in ("Private Citizen", citizen["email"], citizen["id"], c1["reference_id"], "Officer A1", "author"):
        assert leaked not in text
    # resolve requires resolution info and an administrator
    assert client.post(f"/api/authority/public-issues/{issue['id']}/updates", json={"message": "Done now", "progress": "RESOLVED"},
                       headers=auth(w["da"])).status_code == 422
    _post(client, w["da"], f"/api/authority/public-issues/{issue['id']}/updates",
          {"message": "Road resurfaced", "progress": "RESOLVED", "resolution_info": "Resurfaced 300 m stretch."})
    assert client.get(f"/api/public/issues/{issue['id']}").json()["resolution_info"] == "Resurfaced 300 m stretch."
    _post(client, w["da"], f"/api/authority/public-issues/{issue['id']}/unpublish", {"reason": "Superseded by new issue"}, 200)
    assert client.get("/api/public/issues").json()["total"] == 0


def test_auto_public_issue_from_cluster(client, admin, db):
    """Three nearby reports become a public issue that the department cannot hide; it publishes after 7 days."""
    from app.models import PublicIssue
    from app.services.auto_issues import run_auto_public_issues

    at = admin[0]
    w = _two_districts(client, at, db)
    made = []
    for n in range(3):
        token, _ = register_citizen(client, email=f"resident{n}@example.com", name=f"Resident Number{n}")
        made.append(create_complaint(client, token, location={**IN_A1, "latitude": 14.5 + n * 0.0005}))
    far_token, _ = register_citizen(client, email="far@example.com")
    far = create_complaint(client, far_token, location=IN_A2)

    issues = client.get("/api/authority/public-issues", headers=auth(w["da"])).json()
    assert len(issues) == 1
    issue = issues[0]
    assert issue["auto_generated"] and issue["status"] == "DRAFT" and issue["related_complaints"] == 3
    assert issue["auto_publish_at"] and not issue["can_unpublish"]
    assert "Ward A1" in issue["title"]
    # a fourth nearby report joins the same issue; a far one does not
    token4, _ = register_citizen(client, email="resident4@example.com")
    create_complaint(client, token4, location={**IN_A1, "latitude": 14.5003})
    detail = client.get(f"/api/authority/public-issues/{issue['id']}", headers=auth(w["da"])).json()
    assert detail["related_complaints"] == 4
    assert far["reference_id"] not in str(detail["complaints"])
    # the department cannot remove reports from it
    r = client.delete(f"/api/authority/public-issues/{issue['id']}/complaints/{made[0]['complaint_id']}", headers=auth(w["da"]))
    assert r.status_code == 403
    assert client.get("/api/public/issues").json()["total"] == 0

    # 7 days pass with no review: published automatically
    run_auto_public_issues(db, now=datetime.now(timezone.utc) + timedelta(days=7, minutes=1))
    pub = client.get(f"/api/public/issues/{issue['id']}").json()
    assert pub["published_automatically"] and pub["verification"] == "Not yet reviewed by the department"
    assert pub["updates"][0]["automatic"]
    assert "Resident Number" not in str(pub) and made[0]["reference_id"] not in str(pub)
    # department administrator cannot unpublish it; the main administration can
    assert client.post(f"/api/authority/public-issues/{issue['id']}/unpublish", json={"reason": "Not a real problem"},
                       headers=auth(w["da"])).status_code == 403
    _post(client, at, f"/api/authority/public-issues/{issue['id']}/unpublish", {"reason": "Duplicate of another issue"}, 200)
    # an unpublished automatic issue is not recreated from the same reports
    run_auto_public_issues(db)
    db.expire_all()
    assert len(db.scalars(select(PublicIssue)).all()) == 1


def test_more_residents_reporting_raises_priority(client, admin, db):
    """Each independent resident reporting the same problem adds priority; repeats by one person and NOT_RELATED don't."""
    FULL = {"observed_severity": "MODERATE", "safety_risk": "LOW", "public_exposure": "STREET",
            "occurred_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    at = admin[0]
    w = _two_districts(client, at, db)
    t1, _ = register_citizen(client)
    first = create_complaint(client, t1, location=IN_A1, **FULL)
    # no sensitive-location data in this test setup: an officer confirms that factor so a score exists
    _post(client, w["da"], f"/api/authority/complaints/{first['complaint_id']}/priority",
          {"location_sensitivity": 20, "explanation": "Residential street, no school or hospital nearby."}, 200)
    base = client.get(f"/api/authority/complaints/{first['complaint_id']}", headers=auth(w["da"])).json()["priority"]
    assert base["community"]["other_reporters"] == 0
    # the same citizen reporting again does not count
    create_complaint(client, t1, location={**IN_A1, "latitude": 14.5001}, **FULL)
    again = client.get(f"/api/authority/complaints/{first['complaint_id']}", headers=auth(w["da"])).json()["priority"]
    assert again["community"]["other_reporters"] == 0 and again["priority_score"] == base["priority_score"]
    # two other residents: +10 on the first complaint
    others = []
    for n in range(2):
        tok, _ = register_citizen(client)
        others.append(create_complaint(client, tok, location={**IN_A1, "latitude": 14.5002 + n * 0.0001}, **FULL))
    p = client.get(f"/api/authority/complaints/{first['complaint_id']}", headers=auth(w["da"])).json()["priority"]
    assert p["community"]["other_reporters"] == 2 and p["community"]["boost"] == 10
    assert p["priority_score"] == round(base["priority_score"] + 10, 2)
    # officer marks one as not related: the boost drops back
    r = client.post(f"/api/complaints/{first['complaint_id']}/relationships",
                    json={"related_complaint_id": others[0]["complaint_id"], "relationship_status": "NOT_RELATED"},
                    headers=auth(w["da"]))
    assert r.status_code == 200, r.text
    p = client.get(f"/api/authority/complaints/{first['complaint_id']}", headers=auth(w["da"])).json()["priority"]
    assert p["community"]["other_reporters"] == 1 and p["priority_score"] == round(base["priority_score"] + 5, 2)
