from __future__ import annotations

from typing import Any

from bottle import Bottle, request, response
from pydantic import ValidationError

from quant_distill.domain.schemas import DistillRequest, ErrorEnvelope, ProcessRequest, SummaryRequest
from quant_distill.domain.service import DependencyUnavailableError


def _validation_detail(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "validation error"
    err = errors[0]
    location = ".".join(str(part) for part in err.get("loc", []))
    return f"field '{location}' {err.get('msg', 'is invalid')}"


def _error(status_code: int, code: str, error: str, detail: str) -> dict[str, Any]:
    response.status = status_code
    response.content_type = "application/json"
    return ErrorEnvelope(code=code, error=error, detail=detail).model_dump(mode="json")


def register_process_routes(app: Bottle, *, service: Any) -> None:
    @app.post("/v1/distill")
    def distill_route() -> dict[str, Any]:
        try:
            payload = DistillRequest.model_validate(request.json or {})
        except ValidationError as exc:
            return _error(422, "validation_error", "Invalid request", _validation_detail(exc))
        try:
            return service.distill(payload)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)

    @app.post("/v1/sentiment")
    def sentiment_route() -> dict[str, Any]:
        try:
            payload = SummaryRequest.model_validate(request.json or {})
        except ValidationError as exc:
            return _error(422, "validation_error", "Invalid request", _validation_detail(exc))
        try:
            return service.sentiment(payload)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)

    @app.post("/v1/entities")
    def entities_route() -> dict[str, Any]:
        try:
            payload = SummaryRequest.model_validate(request.json or {})
        except ValidationError as exc:
            return _error(422, "validation_error", "Invalid request", _validation_detail(exc))
        try:
            return service.entities(payload)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)

    @app.post("/v1/process")
    def process_route() -> dict[str, Any]:
        try:
            payload = ProcessRequest.model_validate(request.json or {})
        except ValidationError as exc:
            return _error(422, "validation_error", "Invalid request", _validation_detail(exc))
        try:
            return service.process(payload)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)
