from __future__ import annotations

from webtest import TestApp

from quant_distill.api.app import create_app


def test_health() -> None:
    client = TestApp(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "service": "quant-distill-api"}
    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_preflight() -> None:
    client = TestApp(create_app())
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]


def test_not_found_json() -> None:
    client = TestApp(create_app())
    response = client.get("/missing", status=404)
    assert response.json["status"] == "error"
    assert response.json["code"] == "not_found"
