from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bottle import Bottle, response


def register_metadata_routes(
    app: Bottle,
    *,
    capabilities_handler: Callable[[], dict[str, Any]],
    stats_handler: Callable[[], dict[str, Any]],
    queue_handler: Callable[[], dict[str, Any]],
) -> None:
    @app.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        response.content_type = "application/json"
        return capabilities_handler()

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        response.content_type = "application/json"
        return stats_handler()

    @app.get("/queue")
    def queue() -> dict[str, Any]:
        response.content_type = "application/json"
        return queue_handler()
