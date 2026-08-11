from __future__ import annotations

import json
from typing import Any

from bottle import Bottle, request, response

from quant_distill.api.routes.health import register_health_routes
from quant_distill.api.routes.metadata import register_metadata_routes
from quant_distill.api.routes.process import register_process_routes
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
) -> Bottle:
    configure_logging()
    app = Bottle()
    app.title = SERVICE_NAME
    service = service or build_default_service()

    register_health_routes(
        app,
        service_name=SERVICE_NAME,
        readiness_check=readiness_check or service.readiness,
    )
    register_metadata_routes(
        app,
        capabilities_handler=capabilities_handler or service.capabilities,
        stats_handler=stats_handler or service.stats_snapshot,
    )
    register_process_routes(app, service=service)

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

    return app


app = create_app()
