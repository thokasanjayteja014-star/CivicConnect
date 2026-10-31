"""Test harness. Uses an ISOLATED test database (civicconnect_test by default).

All records created here are synthetic test fixtures and exist only inside
this test database; they are truncated after every test.
"""
import io
import os
import struct
import tempfile
import uuid
import wave

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://civic:civic@localhost:5432/civicconnect_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["AUTH_SECRET"] = "test-secret-" + "x" * 40
os.environ["MEDIA_LOCAL_DIR"] = tempfile.mkdtemp(prefix="cc-media-")
os.environ["MEDIA_STORAGE_ENDPOINT"] = ""
os.environ["RATE_LIMIT_ENABLED"] = "false"
for k in ("AI_PROVIDER", "AI_PROVIDER_API_KEY", "AI_MODEL_NAME", "EMBEDDING_MODEL_NAME", "SPEECH_MODEL_NAME", "VISION_MODEL_NAME"):
    os.environ[k] = ""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal, reset_engine  # noqa: E402

get_settings.cache_clear()
reset_engine()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def database():
    engine = create_engine(TEST_DB)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "migrations"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    engine = create_engine(TEST_DB)
    with engine.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','spatial_ref_sys')"))]
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    engine.dispose()


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


# ---------------- helpers ----------------
def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_citizen(client, email=None, name="Test Citizen"):
    email = email or f"citizen-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"full_name": name, "email": email, "password": "password-123"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"], r.json()["user"]


def make_user(db, role, department_id=None, designation="Officer", email=None):
    from app.models import Officer, User
    from app.models.enums import AccountStatus
    from app.security import create_access_token, hash_password

    u = User(full_name=f"Test {role.value}", email=email or f"{role.value.lower()}-{uuid.uuid4().hex[:8]}@example.com",
             password_hash=hash_password("password-123"), role=role, account_status=AccountStatus.ACTIVE)
    db.add(u)
    db.flush()
    officer = None
    if department_id:
        officer = Officer(user_id=u.id, department_id=department_id, designation=designation)
        db.add(officer)
    db.commit()
    token, _ = create_access_token(u.id, role.value)
    return token, u, officer


SQUARE = {"type": "Polygon", "coordinates": [[[77.0, 15.0], [77.2, 15.0], [77.2, 15.2], [77.0, 15.2], [77.0, 15.0]]]}
INSIDE = {"latitude": 15.1, "longitude": 77.1, "location_source": "MAP_SELECTION"}
OUTSIDE = {"latitude": 10.0, "longitude": 70.0, "location_source": "MAP_SELECTION"}


@pytest.fixture
def admin(db):
    from app.models.enums import Role
    token, user, _ = make_user(db, Role.SYSTEM_ADMIN)
    return token, user


@pytest.fixture
def configured(client, admin, db):
    """One jurisdiction + one department responsible (verified) for ROAD_INFRASTRUCTURE,
    with a department admin and an officer. Returns a dict of handles."""
    from app.models.enums import Role
    at = admin[0]
    dept = client.post("/api/admin/departments", json={"name": "Test Roads Dept"}, headers=auth(at)).json()
    other = client.post("/api/admin/departments", json={"name": "Test Water Dept"}, headers=auth(at)).json()
    j = client.post("/api/admin/jurisdictions", json={"name": "Test Ward", "boundary": SQUARE,
                                                      "department_ids": [dept["id"], other["id"]]}, headers=auth(at))
    assert j.status_code == 200, j.text
    r = client.post("/api/admin/responsibilities", json={"department_id": dept["id"], "category": "ROAD_INFRASTRUCTURE",
                                                         "verified": True}, headers=auth(at))
    assert r.status_code == 200, r.text
    r = client.post("/api/admin/responsibilities", json={"department_id": other["id"], "category": "WATER_SUPPLY",
                                                         "verified": True}, headers=auth(at))
    did, oid = uuid.UUID(dept["id"]), uuid.UUID(other["id"])
    dadmin_token, dadmin, dadmin_officer = make_user(db, Role.DEPARTMENT_ADMIN, did, "Head")
    off_token, off, off_officer = make_user(db, Role.OFFICER, did, "Field officer")
    other_token, _, _ = make_user(db, Role.OFFICER, oid, "Water officer")
    return {"dept": dept, "other": other, "jurisdiction": j.json(), "admin_token": at,
            "dadmin_token": dadmin_token, "dadmin_officer": dadmin_officer, "officer_token": off_token,
            "officer": off_officer, "other_officer_token": other_token}


def complaint_payload(**over):
    p = {
        "title": "Large pothole on main road",
        "description": "There is a deep pothole near the bus stop causing two-wheelers to swerve.",
        "category": "ROAD_INFRASTRUCTURE",
        "location": INSIDE,
        "confirmed": True,
    }
    p.update(over)
    return p


def create_complaint(client, token, key=None, **over):
    headers = auth(token)
    headers["Idempotency-Key"] = key or uuid.uuid4().hex
    r = client.post("/api/complaints", json=complaint_payload(**over), headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def png_bytes(size=(32, 32)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 120, 120)).save(buf, "PNG")
    return buf.getvalue()


def wav_bytes(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * int(8000 * seconds))
    return buf.getvalue()
