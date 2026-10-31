"""Media validation (spec 5.B, E6-E10). Content is sniffed; extensions are not trusted."""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from app.core.errors import err
from app.models.enums import MediaType

MB = 1024 * 1024
LIMITS = {
    MediaType.IMAGE: {"max_bytes": 10 * MB, "max_count": 5, "max_seconds": None},
    MediaType.AUDIO: {"max_bytes": 15 * MB, "max_count": 1, "max_seconds": 120},
    MediaType.VIDEO: {"max_bytes": 50 * MB, "max_count": 1, "max_seconds": 60},
}
ABSOLUTE_MAX_BYTES = 50 * MB


@dataclass
class ValidatedMedia:
    media_type: MediaType
    mime_type: str
    data: bytes
    size: int
    duration_seconds: float | None
    sha256: str
    extension: str
    perceptual_hash: str | None = None


def difference_hash(data: bytes, size: int = 8) -> str | None:
    """64-bit dHash of an image as 16 hex chars. Robust to resizing, recompression and small
    brightness changes, so the same scene photographed twice gives nearby hashes. Deterministic."""
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
            px = list(img.tobytes())
    except Exception:
        return None
    bits = 0
    for row in range(size):
        for col in range(size):
            left, right = px[row * (size + 1) + col], px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def sniff(data: bytes) -> tuple[MediaType, str, str] | None:
    """Detect type from magic bytes. Returns (media_type, mime, ext) or None."""
    head = data[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return MediaType.IMAGE, "image/jpeg", "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return MediaType.IMAGE, "image/png", "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return MediaType.IMAGE, "image/webp", "webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return MediaType.AUDIO, "audio/wav", "wav"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return MediaType.AUDIO, "audio/mpeg", "mp3"
    if head.startswith(b"OggS"):
        return MediaType.AUDIO, "audio/ogg", "ogg"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return MediaType.AUDIO, "audio/mp4", "m4a"
        if brand in (b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"MSNV", b"M4V ", b"dash", b"iso5", b"iso6", b"qt  "):
            return MediaType.VIDEO, "video/mp4", "mp4"
    return None


def _duration_ffprobe(data: bytes) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".bin") as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", tmp.name],
                capture_output=True, text=True, timeout=20,
            )
            return float(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
        except (subprocess.SubprocessError, ValueError):
            return None


def _duration_mutagen(data: bytes) -> float | None:
    try:
        import mutagen

        f = mutagen.File(io.BytesIO(data))
        if f is not None and f.info is not None and getattr(f.info, "length", None):
            return float(f.info.length)
    except Exception:
        return None
    return None


def media_duration(data: bytes) -> float | None:
    return _duration_mutagen(data) or _duration_ffprobe(data)


def validate_upload(data: bytes, declared_mime: str | None = None) -> ValidatedMedia:
    if not data:
        raise err("CORRUPT_MEDIA")
    detected = sniff(data)
    if detected is None:
        raise err("UNSUPPORTED_MEDIA_TYPE")
    media_type, mime, ext = detected
    limit = LIMITS[media_type]
    if len(data) > limit["max_bytes"]:
        raise err("FILE_TOO_LARGE", details={"limit_bytes": limit["max_bytes"], "media_type": media_type.value})

    duration = None
    if media_type == MediaType.IMAGE:
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as img:
                img.verify()
        except Exception:
            raise err("CORRUPT_MEDIA")
    else:
        duration = media_duration(data)
        if duration is None:
            raise err("CORRUPT_MEDIA")
        if duration > limit["max_seconds"]:
            raise err("MEDIA_DURATION_EXCEEDED", details={"limit_seconds": limit["max_seconds"], "duration_seconds": round(duration, 1)})

    return ValidatedMedia(
        media_type=media_type,
        mime_type=mime,
        data=data,
        size=len(data),
        duration_seconds=round(duration, 2) if duration is not None else None,
        sha256=hashlib.sha256(data).hexdigest(),
        extension=ext,
        perceptual_hash=difference_hash(data) if media_type == MediaType.IMAGE else None,
    )


def check_media_counts(types: list[MediaType]) -> None:
    for mt, limit in LIMITS.items():
        n = sum(1 for t in types if t == mt)
        if n > limit["max_count"]:
            if mt == MediaType.IMAGE:
                raise err("TOO_MANY_IMAGES")
            raise err("TOO_MANY_MEDIA", message=f"You can attach a maximum of {limit['max_count']} {mt.value.lower()} file per complaint.")
