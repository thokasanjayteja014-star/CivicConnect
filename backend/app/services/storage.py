"""Object storage: S3-compatible when MEDIA_STORAGE_ENDPOINT is set, otherwise a
private local directory (development only; never served directly)."""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import get_settings


class StorageError(Exception):
    pass


class LocalStorage:
    kind = "local-development"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise StorageError("invalid key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            p = self._path(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
        except OSError as exc:
            raise StorageError(str(exc)) from exc

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError(str(exc)) from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            pass

    def healthy(self) -> bool:
        return self.root.exists() and os.access(self.root, os.W_OK)


class S3Storage:
    kind = "s3"

    def __init__(self):
        import boto3
        from botocore.config import Config

        s = get_settings()
        self.bucket = s.MEDIA_STORAGE_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=s.MEDIA_STORAGE_ENDPOINT,
            aws_access_key_id=s.MEDIA_STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=s.MEDIA_STORAGE_SECRET_KEY or None,
            region_name=s.MEDIA_STORAGE_REGION,
            # Path-style URLs work with MinIO, Supabase Storage and Cloudflare R2.
            config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except Exception as exc:
            raise StorageError(type(exc).__name__) from exc

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise StorageError(type(exc).__name__) from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            pass

    def healthy(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.MEDIA_STORAGE_ENDPOINT else LocalStorage(s.MEDIA_LOCAL_DIR)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None
