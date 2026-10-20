"""Prometheus request counter. One HTTP middleware plus GET /metrics."""

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from app import diag
from app.config import settings

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests by route template, status and release version",
    ["method", "path", "status", "version"],
)


def _route_template(request: Request) -> str:
    """Route template (bounded label set), never the raw URL. Unmatched routes are 'other'."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "other"


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - catch-all on purpose: count, log evidence, hide trace
            diag.record_error(exc, request.url.path)
            response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
        REQUESTS.labels(
            request.method, _route_template(request), str(response.status_code), settings.app_version
        ).inc()
        return response

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
