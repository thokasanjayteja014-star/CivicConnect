import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, auth, authority, complaints, geo, media, misc, public
from app.audit import request_id_var
from app.core.config import get_settings
from app.core.errors import ApiError, err

log = logging.getLogger("civicconnect")


def _error(status: int, code: str, message: str, details=None, request_id=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error_code": code, "message": message, "details": details,
                                                     "request_id": request_id})


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.LOG_LEVEL)
    app = FastAPI(
        title="CivicConnect API",
        version="1.0.0",
        description="AI-assisted citizen grievance reporting, deterministic routing and resolution tracking. "
                    "Internal CivicConnect workflow; no government portal integration.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        rid = rid[:64]
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return _error(exc.status_code, exc.error_code, exc.message, exc.details, getattr(request.state, "request_id", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        fields = {d["field"] for d in details}
        code = "VALIDATION_ERROR"
        if any(f.startswith("location.latitude") or f.startswith("location.longitude") for f in fields):
            code = "INVALID_COORDINATES"
        e = err(code)
        return _error(422, code, e.message, details, getattr(request.state, "request_id", None))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "NOT_FOUND", 401: "UNAUTHENTICATED", 403: "FORBIDDEN"}.get(exc.status_code, "CONFLICT")
        return _error(exc.status_code, code, err(code).message, None, getattr(request.state, "request_id", None))

    @app.exception_handler(OperationalError)
    async def db_down(request: Request, exc: OperationalError):
        log.error("database unavailable request_id=%s", getattr(request.state, "request_id", None))
        e = err("DATABASE_UNAVAILABLE")
        return _error(503, e.error_code, e.message, None, getattr(request.state, "request_id", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", None))
        e = err("INTERNAL_ERROR")
        return _error(500, e.error_code, e.message, None, getattr(request.state, "request_id", None))

    for r in (auth.router, complaints.router, media.router, authority.router, public.router, admin.router, misc.router, geo.router):
        app.include_router(r)
    return app


app = create_app()
