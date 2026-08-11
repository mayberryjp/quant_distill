from __future__ import annotations

from webtest import TestApp

from quant_distill.api.app import create_app


def test_health() -> None:
    client = TestApp(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "service": "quant-distill-api"}


def test_not_found_json() -> None:
    client = TestApp(create_app())
    response = client.get("/missing", status=404)
    assert response.json["status"] == "error"
    assert response.json["code"] == "not_found"
