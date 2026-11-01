"""Demo environment isolation: separate schema, environment-bound tokens, reset never touches production."""
from sqlalchemy import func, select, text

from app.core.db import get_engine
from app.core.environment import PRODUCTION
from app.models import Complaint
from tests.conftest import auth, create_complaint, register_citizen

DEMO = {"X-CC-Env": "demo"}


def _demo_login(client, role):
    r = client.post("/api/demo/login", json={"role": role}, headers=DEMO)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_demo_isolation_and_reset(client, configured, db):
    from app import demo
    with get_engine(PRODUCTION).begin() as conn:
        conn.execute(text('DROP SCHEMA IF EXISTS "demo" CASCADE'))
    demo.ensure()

    # production record
    token, _ = register_citizen(client)
    prod = create_complaint(client, token)
    prod_count = db.scalar(select(func.count()).select_from(Complaint))

    # demo login only inside the demo environment
    assert client.post("/api/demo/login", json={"role": "CITIZEN"}).status_code == 403
    assert client.get("/api/demo/status", headers=DEMO).json()["banner"] == "DEMONSTRATION ENVIRONMENT – SAMPLE DATA"
    tokens = {r: _demo_login(client, r) for r in ("SYSTEM_ADMIN", "DEPARTMENT_ADMIN", "OFFICER", "CITIZEN")}

    # tokens are bound to their environment
    assert client.get("/api/auth/me", headers=auth(tokens["CITIZEN"])).status_code == 401
    assert client.get("/api/auth/me", headers={**auth(token), **DEMO}).status_code == 401
    assert client.get("/api/auth/me", headers={**auth(tokens["OFFICER"]), **DEMO}).json()["role"] == "OFFICER"

    # demo data is visible only in demo; production data is invisible in demo
    ov = client.get("/api/admin/overview", headers={**auth(tokens["SYSTEM_ADMIN"]), **DEMO}).json()
    assert ov["totals"]["total"] == 12 and ov["totals"]["escalated"] >= 1
    assert ov["totals"]["awaiting_assignment"] >= 1  # Ward 4 has no officer
    assert prod["reference_id"] not in str(client.get("/api/authority/complaints?limit=200",
                                                      headers={**auth(tokens["SYSTEM_ADMIN"]), **DEMO}).json())
    assert client.get("/api/public/issues", headers=DEMO).json()["total"] == 1
    assert client.get("/api/public/issues").json()["total"] == 0
    assert db.scalar(select(func.count()).select_from(Complaint)) == prod_count

    # demo actions persist in demo only
    headers = {**auth(tokens["CITIZEN"]), **DEMO, "Idempotency-Key": "demo-1"}
    r = client.post("/api/complaints", json={"title": "Demo pothole test", "description": "A pothole created during the demo.",
                                             "category": "ROAD_INFRASTRUCTURE", "confirmed": True,
                                             "location": {"latitude": 15.455, "longitude": 74.985, "location_source": "MAP_SELECTION"}},
                    headers=headers)
    assert r.status_code == 201 and r.json()["status"] == "ASSIGNED", r.text
    assert client.get("/api/authority/complaints?assignment=mine", headers={**auth(tokens["OFFICER"]), **DEMO}).json()["total"] >= 3
    assert db.scalar(select(func.count()).select_from(Complaint)) == prod_count

    # reset rebuilds demo and leaves production alone
    assert client.post("/api/demo/reset").status_code == 403
    assert client.post("/api/demo/reset", headers=DEMO).status_code == 200
    t = _demo_login(client, "SYSTEM_ADMIN")
    assert client.get("/api/admin/overview", headers={**auth(t), **DEMO}).json()["totals"]["total"] == 12
    assert db.scalar(select(func.count()).select_from(Complaint)) == prod_count
    assert client.get(f"/api/complaints/{prod['complaint_id']}", headers=auth(token)).status_code == 200
