from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bottle import Bottle, response

from quant_distill.domain.schemas import HealthResponse, ReadyResponse, ReadinessDependency


def register_health_routes(
    app: Bottle,
    *,
    service_name: str,
    readiness_check: Callable[[], dict[str, Any]],
) -> None:
    @app.get("/health")
    def health() -> dict[str, Any]:
        response.content_type = "application/json"
        return HealthResponse(service=service_name).model_dump(mode="json")

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        result = readiness_check()
        payload = ReadyResponse(
            status="ok" if result["ok"] else "error",
            service=service_name,
            dependencies=[ReadinessDependency(**item) for item in result["dependencies"]],
        )
        response.content_type = "application/json"
        if not result["ok"]:
            response.status = 503
        return payload.model_dump(mode="json")
