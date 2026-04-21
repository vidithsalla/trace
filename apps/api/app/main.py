from time import perf_counter
from uuid import uuid4

from redis import Redis
from sqlalchemy import text

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.metrics import metrics_registry
from app.db.session import SessionLocal
from app.services.storage import storage_service

configure_logging()
logger = structlog.get_logger(__name__)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    started_at = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        latency_ms = (perf_counter() - started_at) * 1000
        metrics_registry.observe_request(
            request.method,
            request.url.path,
            status_code,
            latency_ms,
        )
        logger.info(
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            latency_ms=round(latency_ms, 2),
        )


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/live")
def livecheck() -> dict[str, str]:
    return {"status": "alive", "app": settings.app_name}


@app.get("/health/ready")
def readiness_check() -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive phase-0 readiness
        checks["database"] = f"error: {exc}"

    try:
        Redis.from_url(settings.redis_url).ping()
        checks["redis"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive phase-0 readiness
        checks["redis"] = f"error: {exc}"

    try:
        storage_service._get_client().list_buckets()  # noqa: SLF001 - phase 0 readiness shortcut
        checks["object_storage"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive phase-0 readiness
        checks["object_storage"] = f"error: {exc}"

    overall = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": overall, "app": settings.app_name, "checks": checks}


@app.get("/metrics")
def metrics() -> Response:
    return Response(metrics_registry.render_prometheus(), media_type="text/plain")
