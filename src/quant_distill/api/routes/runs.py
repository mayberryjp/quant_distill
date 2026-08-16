from __future__ import annotations

from typing import Any

from bottle import Bottle, request, response
from pydantic import ValidationError

from quant_distill.domain.schemas import ErrorEnvelope, JobQuery, RunQuery
from quant_distill.domain.service import DependencyUnavailableError


def _error(status_code: int, code: str, error: str, detail: str) -> dict[str, Any]:
    response.status = status_code
    response.content_type = "application/json"
    return ErrorEnvelope(code=code, error=error, detail=detail).model_dump(mode="json")


def _query_error(exc: ValidationError) -> dict[str, Any]:
    err = exc.errors()[0]
    location = ".".join(str(part) for part in err.get("loc", []))
    return _error(
        422,
        "validation_error",
        "Invalid query",
        f"query parameter '{location}' {err.get('msg', 'is invalid')}",
    )


def register_run_routes(app: Bottle, *, service: Any) -> None:
    @app.get("/v1/runs")
    def list_runs() -> dict[str, Any]:
        params = {key: value for key, value in request.query.items() if value != ""}
        try:
            query = RunQuery.model_validate(params)
        except ValidationError as exc:
            return _query_error(exc)
        try:
            payload = service.list_runs(query)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)
        response.content_type = "application/json"
        return payload

    @app.get("/v1/runs/<request_id>")
    def get_run(request_id: str) -> dict[str, Any]:
        try:
            payload = service.get_run(request_id)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)
        if payload is None:
            return _error(404, "not_found", "not found", f"no run with request_id {request_id}")
        response.content_type = "application/json"
        return payload

    @app.get("/v1/jobs")
    def list_jobs() -> dict[str, Any]:
        params = {key: value for key, value in request.query.items() if value != ""}
        try:
            query = JobQuery.model_validate(params)
        except ValidationError as exc:
            return _query_error(exc)
        try:
            payload = service.list_jobs(query)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)
        response.content_type = "application/json"
        return payload

    @app.get("/v1/jobs/<job_id>")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            payload = service.get_job(job_id)
        except DependencyUnavailableError as exc:
            return _error(503, exc.code, exc.error, exc.detail)
        if payload is None:
            return _error(404, "not_found", "not found", f"no job with job_id {job_id}")
        response.content_type = "application/json"
        return payload
