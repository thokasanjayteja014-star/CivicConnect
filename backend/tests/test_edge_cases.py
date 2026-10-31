"""Additional edge cases: video evidence, DB failure (S8), notifications, misuse flag."""
import shutil
import subprocess
import tempfile

import pytest
from sqlalchemy.exc import OperationalError

from tests.conftest import auth, complaint_payload, create_complaint, register_citizen


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_video_upload_and_duration_limit(client):
    token, _ = register_citizen(client)

    def mp4(seconds):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=32x32:d={seconds}",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", f.name], check=True)
            return open(f.name, "rb").read()

    r = client.post("/api/media/upload", files={"file": ("v.mp4", mp4(2), "video/mp4")}, headers=auth(token))
    assert r.status_code == 201 and r.json()["media_type"] == "VIDEO"
    r = client.post("/api/media/upload", files={"file": ("long.mp4", mp4(61), "video/mp4")}, headers=auth(token))
    assert r.status_code == 422 and r.json()["error_code"] == "MEDIA_DURATION_EXCEEDED"


def test_database_failure_returns_503_without_reference(client, monkeypatch):
    token, _ = register_citizen(client)
    import app.services.complaints as svc

    def boom(*a, **k):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(svc, "create_complaint", boom)
    import app.api.complaints  # noqa: F401  (create() imports from the module at call time)
    r = client.post("/api/complaints", json=complaint_payload(), headers={**auth(token), "Idempotency-Key": "x1"})
    assert r.status_code == 503 and r.json()["error_code"] == "DATABASE_UNAVAILABLE"
    assert "reference_id" not in r.text and "connection refused" not in r.text


def test_notifications_and_misuse(client, configured):
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    n = client.get("/api/notifications", headers=auth(token)).json()
    types = {i["notification_type"] for i in n["items"]}
    assert {"SUBMITTED", "ROUTED"} <= types and n["unread"] >= 2
    officer_n = client.get("/api/notifications", headers=auth(configured["officer_token"])).json()
    assert any(i["notification_type"] == "NEW_DEPARTMENT_COMPLAINT" for i in officer_n["items"])
    assert client.post("/api/notifications/read-all", headers=auth(token)).status_code == 200
    assert client.get("/api/notifications", headers=auth(token)).json()["unread"] == 0

    ot = configured["officer_token"]
    client.post(f"/api/authority/complaints/{c['complaint_id']}/publication",
                json={"approve": True, "public_summary": "Pothole near the bus stop"}, headers=auth(ot))
    assert client.get("/api/public/complaints").json()["total"] == 1
    r = client.post(f"/api/admin/complaints/{c['complaint_id']}/misuse", json={"flagged": True, "reason": "spam test"},
                    headers=auth(configured["admin_token"]))
    assert r.status_code == 200
    assert client.get("/api/public/complaints").json()["total"] == 0
    # record is preserved for the citizen
    assert client.get(f"/api/complaints/{c['complaint_id']}", headers=auth(token)).status_code == 200


def test_citizen_patch_only_before_review(client, configured):
    token, _ = register_citizen(client)
    c = create_complaint(client, token)
    r = client.patch(f"/api/complaints/{c['complaint_id']}", json={"title": "Updated pothole title"}, headers=auth(token))
    assert r.status_code == 200 and r.json()["title"] == "Updated pothole title"
    assert r.json()["original_description"]  # original preserved
    client.post(f"/api/authority/complaints/{c['complaint_id']}/status", json={"status": "UNDER_REVIEW"}, headers=auth(configured["officer_token"]))
    r = client.patch(f"/api/complaints/{c['complaint_id']}", json={"title": "Another new title"}, headers=auth(token))
    assert r.status_code == 409
