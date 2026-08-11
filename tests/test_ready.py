from __future__ import annotations

from webtest import TestApp

from quant_distill.api.app import create_app


def test_ready_ok() -> None:
    client = TestApp(
        create_app(
            readiness_check=lambda: {
                "ok": True,
                "dependencies": [
                    {"name": "llm", "status": "ok", "detail": "ok"},
                    {"name": "watchlist", "status": "disabled", "detail": None},
                    {"name": "momentum", "status": "disabled", "detail": None},
                ],
            }
        )
    )
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["service"] == "quant-distill-api"


def test_ready_503() -> None:
    client = TestApp(
        create_app(
            readiness_check=lambda: {
                "ok": False,
                "dependencies": [
                    {"name": "llm", "status": "unavailable", "detail": "timeout"},
                ],
            }
        )
    )
    response = client.get("/ready", status=503)
    assert response.json["status"] == "error"
    assert response.json["dependencies"][0]["name"] == "llm"
