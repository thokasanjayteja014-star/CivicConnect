"""Notifications channels, push subscriptions, preferences, geocoding proxy, perceptual
image hashing for duplicates, video frame sampling and voice transcription.
External services are mocked; nothing leaves the test process."""
import io
import os
import shutil
import subprocess
import tempfile
import uuid

import httpx
import pytest

from tests.conftest import auth, complaint_payload, create_complaint, register_citizen, wav_bytes


def _img(seed: int, size=(400, 300), shift=0) -> bytes:
    """A structured test image (gradient + blocks) so dHash has real edges to work with."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, (30, 30, 30))
    d = ImageDraw.Draw(img)
    import random
    rnd = random.Random(seed)
    for _ in range(12):
        x, y = rnd.randint(0, size[0] - 60), rnd.randint(0, size[1] - 60)
        c = rnd.randint(60, 255)
        d.rectangle([x + shift, y, x + shift + rnd.randint(20, 120), y + rnd.randint(20, 120)], fill=(c, c, c))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _settings(monkeypatch, **env):
    from app.core.config import get_settings
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return get_settings


# ---------------- perceptual hash ----------------
def test_dhash_matches_resized_copy_not_different_scene():
    from PIL import Image
    from app.services.media import difference_hash, hamming
    a = _img(1)
    small = io.BytesIO()
    Image.open(io.BytesIO(a)).resize((200, 150)).save(small, "JPEG", quality=60)
    ha, hs, hb = difference_hash(a), difference_hash(small.getvalue()), difference_hash(_img(2))
    assert len(ha) == 16
    assert hamming(ha, hs) <= 6
    assert hamming(ha, hb) > 12


def test_duplicate_detection_uses_photo_similarity():
    from datetime import datetime, timezone
    from app.duplicate_detection import CandidateInput, detect_duplicate_candidates
    now = datetime.now(timezone.utc)
    cands = [CandidateInput("a", "ROAD_INFRASTRUCTURE", now, 40.0, "completely unrelated words", ["ffffffff00000000"])]
    out = detect_duplicate_candidates(category="ROAD_INFRASTRUCTURE", created_at=now, text="pothole near bus stop",
                                      candidates=cands, image_hashes=["ffffffff00000001"])
    assert any("Similar photo" in r for r in out[0].match_reasons) and out[0].image_distance == 1
    far = detect_duplicate_candidates(category="ROAD_INFRASTRUCTURE", created_at=now, text="pothole near bus stop",
                                      candidates=cands, image_hashes=["0000000000ffffff"])
    assert not any("Similar photo" in r for r in far[0].match_reasons)
    assert out[0].similarity_score > far[0].similarity_score


def test_same_photo_flagged_as_related_end_to_end(client, configured):
    tok, _ = register_citizen(client)
    photo = _img(7)

    def upload(data):
        r = client.post("/api/media/upload", files={"file": ("p.jpg", data, "image/jpeg")}, headers=auth(tok))
        assert r.status_code == 201, r.text
        return r.json()["media_id"]

    create_complaint(client, tok, media_ids=[upload(photo)], description="Broken road surface here")
    from PIL import Image
    recompressed = io.BytesIO()
    Image.open(io.BytesIO(photo)).resize((300, 225)).save(recompressed, "JPEG", quality=50)
    c2 = create_complaint(client, tok, media_ids=[upload(recompressed.getvalue())],
                          description="Totally different wording about the issue")
    r = client.get(f"/api/complaints/{c2['complaint_id']}/related", headers=auth(configured["officer_token"]))
    assert r.status_code == 200, r.text
    reasons = [x for item in r.json() for x in item["match_reasons"]]
    assert any("Similar photo" in x for x in reasons)


# ---------------- notification preferences & channels ----------------
def test_preferences_update_and_sms_requires_phone(client):
    tok, user = register_citizen(client)
    assert user["notify_email"] is True and user["preferred_language"] == "en"
    r = client.patch("/api/auth/me/preferences", json={"notify_sms": True}, headers=auth(tok))
    assert r.status_code == 422
    r = client.patch("/api/auth/me/preferences", json={"notify_sms": True, "phone": "+919876543210",
                                                       "preferred_language": "kn"}, headers=auth(tok))
    assert r.status_code == 200, r.text
    assert r.json()["notify_sms"] is True and r.json()["preferred_language"] == "kn"
    assert client.patch("/api/auth/me/preferences", json={"preferred_language": "fr"}, headers=auth(tok)).status_code == 422


def test_external_delivery_email_and_sms(client, monkeypatch, db):
    gs = _settings(monkeypatch, EMAIL_PROVIDER="brevo", BREVO_API_KEY="k", EMAIL_FROM="noreply@example.com",
                   SMS_PROVIDER="twilio", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", TWILIO_FROM_NUMBER="+15550001111",
                   NOTIFY_EXTERNAL_SYNC="true")
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return httpx.Response(201, json={"ok": True})
    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        tok, _ = register_citizen(client)
        client.patch("/api/auth/me/preferences", json={"notify_sms": True, "phone": "+919876543210"}, headers=auth(tok))
        assert client.get("/api/notifications/channels").json()["email"] is True
        r = client.post("/api/notifications/test", headers=auth(tok))
        assert r.status_code == 200, r.text
        assert any("brevo" in u for u in calls) and any("twilio" in u for u in calls)
        items = client.get("/api/notifications", headers=auth(tok)).json()["items"]
        chans = {d["channel"]: d["status"] for d in items[0]["external_deliveries"]}
        assert chans == {"EMAIL": "SENT", "SMS": "SENT"}
    finally:
        monkeypatch.undo()
        gs.cache_clear()


def test_external_delivery_failure_recorded_and_opt_out(client, monkeypatch):
    gs = _settings(monkeypatch, EMAIL_PROVIDER="brevo", BREVO_API_KEY="k", EMAIL_FROM="noreply@example.com",
                   NOTIFY_EXTERNAL_SYNC="true")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(401, json={}))
    try:
        tok, _ = register_citizen(client)
        client.post("/api/notifications/test", headers=auth(tok))
        items = client.get("/api/notifications", headers=auth(tok)).json()["items"]
        assert items[0]["external_deliveries"] == [{"channel": "EMAIL", "status": "FAILED"}]
        client.patch("/api/auth/me/preferences", json={"notify_email": False}, headers=auth(tok))
        client.post("/api/notifications/test", headers=auth(tok))
        items = client.get("/api/notifications", headers=auth(tok)).json()["items"]
        assert items[0]["external_deliveries"] == []
    finally:
        monkeypatch.undo()
        gs.cache_clear()


def test_push_subscription_requires_vapid_then_works(client, monkeypatch):
    tok, _ = register_citizen(client)
    sub = {"endpoint": "https://push.example.com/abc123", "p256dh": "B" * 40, "auth": "a" * 16}
    assert client.post("/api/notifications/push-subscriptions", json=sub, headers=auth(tok)).status_code == 422
    gs = _settings(monkeypatch, VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", VAPID_SUBJECT="mailto:a@example.com")
    try:
        assert client.get("/api/notifications/channels").json()["vapid_public_key"] == "pub"
        assert client.post("/api/notifications/push-subscriptions", json=sub, headers=auth(tok)).status_code == 201
        assert client.post("/api/notifications/push-subscriptions", json=sub, headers=auth(tok)).status_code == 201
        r = client.delete("/api/notifications/push-subscriptions", params={"endpoint": sub["endpoint"]}, headers=auth(tok))
        assert r.status_code == 204
    finally:
        monkeypatch.undo()
        gs.cache_clear()


def test_status_change_still_notifies_in_app_when_no_channels(client, configured):
    tok, _ = register_citizen(client)
    c = create_complaint(client, tok)
    items = client.get("/api/notifications", headers=auth(tok)).json()["items"]
    assert items and all(i["external_deliveries"] == [] for i in items)


# ---------------- geocoding ----------------
def test_geo_search_and_reverse(client, monkeypatch):
    from app.api import geo
    geo._cache.clear()
    monkeypatch.setattr(geo.time, "sleep", lambda s: None)
    seen = []

    def fake_get(url, params, headers, timeout):
        seen.append((url, params, headers))
        if url.endswith("/search"):
            return httpx.Response(200, json=[{"lat": "15.45", "lon": "75.01", "display_name": "IIIT Dharwad, Karnataka", "type": "college"}])
        return httpx.Response(200, json={"display_name": "Some Road, Dharwad"})
    monkeypatch.setattr(httpx, "get", fake_get)
    tok, _ = register_citizen(client)
    r = client.get("/api/geo/search", params={"q": "IIIT Dharwad"}, headers=auth(tok))
    assert r.status_code == 200 and r.json()["results"][0]["latitude"] == 15.45
    assert seen[0][1]["countrycodes"] == "in" and "CivicConnect" in seen[0][2]["User-Agent"]
    assert "_lang" not in seen[0][1]
    client.get("/api/geo/search", params={"q": "IIIT Dharwad"}, headers=auth(tok))
    assert len(seen) == 1  # cached
    r = client.get("/api/geo/reverse", params={"lat": 15.45, "lng": 75.01}, headers=auth(tok))
    assert r.json()["display_name"] == "Some Road, Dharwad"
    assert client.get("/api/geo/search", params={"q": "IIIT"}).status_code == 401


def test_geo_provider_down(client, monkeypatch):
    from app.api import geo
    geo._cache.clear()
    monkeypatch.setattr(geo.time, "sleep", lambda s: None)
    def boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "get", boom)
    tok, _ = register_citizen(client)
    r = client.get("/api/geo/search", params={"q": "somewhere new"}, headers=auth(tok))
    assert r.status_code == 503 and r.json()["error_code"] == "GEOCODER_UNAVAILABLE"


# ---------------- video frames & voice ----------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_video_frames_extracted():
    from app.ai.ai_service import extract_video_frames
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "v.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
                        "-pix_fmt", "yuv420p", out], check=True)
        frames = extract_video_frames(open(out, "rb").read())
    assert len(frames) == 3 and all(f.startswith(b"\xff\xd8") for f in frames)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_video_frames_sent_to_vision_model(monkeypatch):
    import json as _json
    from app.ai import ai_service
    from app.ai.ai_service import MediaInput
    from tests.test_units import VALID_AI
    gs = _settings(monkeypatch, AI_PROVIDER="xai", AI_PROVIDER_API_KEY="k", AI_MODEL_NAME="grok-test", AI_MAX_RETRIES="0")
    sent = {}

    def fake_post(url, headers, timeout, json):
        sent["content"] = json["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(VALID_AI)}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "v.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
                            "-pix_fmt", "yuv420p", out], check=True)
            vid = MediaInput("vid-1", "VIDEO", "video/mp4", open(out, "rb").read())
        ai_service.analyze_complaint("water leaking from pipe", [vid], {})
        images = [p for p in sent["content"] if p["type"] == "image_url"]
        assert len(images) == 3 and "vid-1 (video frame)" in sent["content"][0]["text"]
        assert ai_service.ai_status().capabilities[5].status == "AVAILABLE"
    finally:
        monkeypatch.undo()
        gs.cache_clear()


def test_transcribe_endpoint(client, monkeypatch):
    tok, _ = register_citizen(client)
    r = client.post("/api/media/upload", files={"file": ("v.wav", wav_bytes(1.0), "audio/wav")}, headers=auth(tok))
    mid = r.json()["media_id"]
    r = client.post("/api/complaints/transcribe", json={"media_id": mid}, headers=auth(tok))
    assert r.status_code == 503 and r.json()["error_code"] == "AI_NOT_CONFIGURED"
    gs = _settings(monkeypatch, AI_PROVIDER="xai", AI_PROVIDER_API_KEY="k", AI_MODEL_NAME="grok",
                   SPEECH_PROVIDER="groq", SPEECH_API_KEY="gsk", SPEECH_MODEL_NAME="whisper-large-v3")
    seen = {}

    def fake_post(url, headers, timeout, **kw):
        seen.update(url=url, auth=headers["Authorization"])
        return httpx.Response(200, json={"text": "ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ", "language": "kn"})
    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        r = client.post("/api/complaints/transcribe", json={"media_id": mid}, headers=auth(tok))
        assert r.status_code == 200, r.text
        assert r.json()["language"] == "kn" and "ಗುಂಡಿ" in r.json()["transcription"]
        assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions" and seen["auth"] == "Bearer gsk"
    finally:
        monkeypatch.undo()
        gs.cache_clear()
