from __future__ import annotations

import json
from typing import Any

from bottle import Bottle, BaseRequest, request, response

from quant_distill.api.routes.health import register_health_routes
from quant_distill.api.routes.metadata import register_metadata_routes
from quant_distill.api.routes.process import register_process_routes
from quant_distill.api.routes.runs import register_run_routes
from quant_distill.config import settings
from quant_distill.domain.schemas import ErrorEnvelope
from quant_distill.domain.service import build_default_service
from quant_distill.logging import configure_logging

SERVICE_NAME = "quant-distill-api"


def create_app(
    *,
    service: Any = None,
    readiness_check: Any = None,
    capabilities_handler: Any = None,
    stats_handler: Any = None,
    queue_handler: Any = None,
) -> Bottle:
    configure_logging()
    # bottle buffers the whole body in memory and rejects anything over MEMFILE_MAX (100KB default).
    BaseRequest.MEMFILE_MAX = settings.max_request_bytes
    app = Bottle()
    app.title = SERVICE_NAME
    service = service or build_default_service()
    stats = getattr(service, "stats", None)

    @app.hook("before_request")
    def track_request_start() -> None:
        if stats is not None:
            request.environ["quant_distill.request_token"] = stats.request_started(
                request.path, request.method
            )

    @app.hook("after_request")
    def track_request_end() -> None:
        if stats is not None:
            stats.request_finished(request.environ.pop("quant_distill.request_token", None))

    @app.hook("after_request")
    def add_cors_headers() -> None:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"

    def cors_preflight() -> str:
        response.status = 204
        return ""

    register_health_routes(
        app,
        service_name=SERVICE_NAME,
        readiness_check=readiness_check or service.readiness,
    )
    register_metadata_routes(
        app,
        capabilities_handler=capabilities_handler or service.capabilities,
        stats_handler=stats_handler or service.stats_snapshot,
        queue_handler=queue_handler or service.queue_snapshot,
    )
    register_process_routes(app, service=service)
    register_run_routes(app, service=service)
    for path in (
        "/health",
        "/ready",
        "/capabilities",
        "/stats",
        "/queue",
        "/v1/runs",
        "/v1/distill",
        "/v1/sentiment",
        "/v1/entities",
        "/v1/process",
    ):
        app.route(path, method="OPTIONS", callback=cors_preflight)

    @app.error(404)
    def not_found(_err: Exception) -> str:
        response.content_type = "application/json"
        return json.dumps(
            ErrorEnvelope(
                code="not_found",
                error="not found",
                detail=f"route {request.path} does not exist",
            ).model_dump(mode="json")
        )

    @app.error(413)
    def payload_too_large(_err: Exception) -> str:
        response.content_type = "application/json"
        return json.dumps(
            ErrorEnvelope(
                code="payload_too_large",
                error="request entity too large",
                detail=f"request body exceeds {settings.max_request_bytes} bytes",
            ).model_dump(mode="json")
        )

    return app


app = create_app()
