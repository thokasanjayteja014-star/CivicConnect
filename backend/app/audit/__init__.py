"""Audit trail (spec F14, L14). Callers commit within their own transaction."""
import contextvars
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    details: dict | None = None,
    actor_label: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        actor_label=actor_label or (f"user:{actor_id}" if actor_id else "system"),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=_jsonable(details or {}),
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
