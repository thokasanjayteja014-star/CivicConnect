import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import err
from app.core.ratelimit import rate_limit
from app.models import Complaint, Media, ResolutionEvidence
from app.models.enums import MediaPurpose
from app.security import create_media_token, decode_token
from app.security.deps import get_optional_actor, require_citizen
from app.security.permissions import Actor, can_view_complaint
from app.services.media import ABSOLUTE_MAX_BYTES, validate_upload
from app.services.storage import StorageError, get_storage
from app.services.views import media_out

router = APIRouter(prefix="/api/media", tags=["media"])


async def read_limited(file: UploadFile) -> bytes:
    data = await file.read(ABSOLUTE_MAX_BYTES + 1)
    if len(data) > ABSOLUTE_MAX_BYTES:
        raise err("FILE_TOO_LARGE", details={"limit_bytes": ABSOLUTE_MAX_BYTES})
    return data


@router.post("/upload", status_code=201, dependencies=[Depends(rate_limit("media", "RATE_LIMIT_MEDIA_UPLOAD"))])
async def upload(file: UploadFile = File(...), actor: Actor = Depends(require_citizen), db: Session = Depends(get_db)):
    """Validate and store complaint media. It stays unattached (visible only to the uploader)
    until the citizen confirms a complaint referencing it."""
    data = await read_limited(file)
    v = validate_upload(data, file.content_type)
    key = f"complaints/{actor.user_id}/{uuid.uuid4()}.{v.extension}"
    try:
        get_storage().put(key, v.data, v.mime_type)
    except StorageError:
        raise err("MEDIA_STORAGE_FAILURE")
    m = Media(uploaded_by=actor.user_id, purpose=MediaPurpose.COMPLAINT, media_type=v.media_type, storage_key=key,
              original_filename=(file.filename or "")[:255] or None, mime_type=v.mime_type, file_size_bytes=v.size,
              duration_seconds=v.duration_seconds, sha256=v.sha256, perceptual_hash=v.perceptual_hash)
    db.add(m)
    db.flush()
    audit.record(db, actor_id=actor.user_id, action="MEDIA_UPLOADED", entity_type="media", entity_id=m.id,
                 details={"media_type": v.media_type, "size": v.size})
    db.commit()
    return media_out(m)


def can_access_media(db: Session, actor: Actor | None, m: Media) -> bool:
    if actor is None:
        return False
    if m.complaint_id is None:
        return m.uploaded_by == actor.user_id
    complaint = db.get(Complaint, m.complaint_id)
    if complaint is None or not can_view_complaint(actor, complaint):
        return False
    if m.purpose == MediaPurpose.RESOLUTION_EVIDENCE and not actor.is_staff:
        ev = db.scalar(select(ResolutionEvidence).where(ResolutionEvidence.media_id == m.id))
        return bool(ev and ev.citizen_visible)
    return True


@router.get("/{media_id}/link")
def media_link(media_id: uuid.UUID, actor: Actor | None = Depends(get_optional_actor), db: Session = Depends(get_db)):
    """Return a short-lived signed URL usable in <img>/<audio>/<video> tags."""
    m = db.get(Media, media_id)
    if m is None or not can_access_media(db, actor, m):
        raise err("MEDIA_NOT_AVAILABLE")
    token, exp = create_media_token(m.id, actor.user_id if actor else None)
    return {"url": f"{get_settings().BACKEND_BASE_URL}/api/media/{m.id}?sig={token}", "expires_at": exp}


@router.get("/{media_id}")
def get_media(media_id: uuid.UUID, request: Request, sig: str | None = None,
              actor: Actor | None = Depends(get_optional_actor), db: Session = Depends(get_db)):
    m = db.get(Media, media_id)
    if m is None:
        raise err("MEDIA_NOT_AVAILABLE")
    allowed = False
    if sig:
        try:
            payload = decode_token(sig, expected_type="media")
            allowed = payload.get("mid") == str(m.id)
        except Exception:
            allowed = False
    if not allowed:
        allowed = can_access_media(db, actor, m)
    if not allowed:
        raise err("MEDIA_NOT_AVAILABLE")
    try:
        data = get_storage().get(m.storage_key)
    except StorageError:
        raise err("MEDIA_STORAGE_FAILURE", message="This media file is temporarily unavailable.")
    return Response(content=data, media_type=m.mime_type, headers={
        "Cache-Control": "private, max-age=60",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    })
