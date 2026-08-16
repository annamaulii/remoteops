import json
import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from remoteops.main import app
from remoteops.reliability import FixedWindowRateLimiter


def test_request_id_is_returned_and_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    request_id = "test-request-123"

    with caplog.at_level(logging.INFO, logger="remoteops.requests"):
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id
    record = json.loads(caplog.records[-1].message)
    assert record["method"] == "GET"
    assert record["path"] == "/health"
    assert record["status"] == 200
    assert record["request_id"] == request_id
    assert isinstance(record["duration_ms"], float)
    assert set(record) == {"method", "path", "status", "duration_ms", "request_id"}


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "unsafe request-id"})

    assert response.headers["X-Request-ID"] != "unsafe request-id"
    assert len(response.headers["X-Request-ID"]) == 36


def test_http_error_uses_consistent_envelope(client: TestClient) -> None:
    @app.get("/_test/validation/{item_id}")
    def validated_route(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    response = client.get("/_test/validation/not-an-integer")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["message"] == "Request validation failed"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_http_exception_uses_consistent_envelope(client: TestClient) -> None:
    @app.get("/_test/http-error")
    def http_error() -> None:
        raise HTTPException(status_code=418, detail="No coffee")

    response = client.get("/_test/http-error")

    assert response.status_code == 418
    assert response.json()["error"] == {
        "code": "http_error",
        "message": "No coffee",
        "request_id": response.headers["X-Request-ID"],
    }


def test_unexpected_error_hides_internal_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @app.get("/_test/unexpected-error")
    def unexpected_error() -> None:
        raise RuntimeError("secret database detail")

    with caplog.at_level(logging.INFO, logger="remoteops.requests"):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/_test/unexpected-error")

    assert response.status_code == 500
    assert response.json()["error"]["message"] == "Internal server error"
    assert "secret database detail" not in response.text
    assert response.headers["X-Request-ID"]
    request_logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "remoteops.requests"
    ]
    assert request_logs[-1]["status"] == 500


def test_fixed_window_rate_limiter_is_deterministic() -> None:
    now = [100.0]
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])

    assert limiter.check("client") is None
    assert limiter.check("client") is None
    assert limiter.check("client") == 10
    now[0] = 110.0
    assert limiter.check("client") is None


def test_rate_limiter_prunes_expired_clients() -> None:
    now = [100.0]
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    limiter.check("old-client-1")
    limiter.check("old-client-2")

    now[0] = 110.0
    limiter.check("fresh-client")

    assert set(limiter._windows) == {"fresh-client"}


def test_auth_rate_limit_returns_retry_after(client: TestClient) -> None:
    limiter = app.state.auth_rate_limiter
    original_limit = limiter.limit
    limiter.clear()
    limiter.limit = 1
    try:
        first = client.post(
            "/auth/login", data={"username": "none@example.com", "password": "wrong"}
        )
        second = client.post(
            "/auth/login", data={"username": "none@example.com", "password": "wrong"}
        )
    finally:
        limiter.limit = original_limit
        limiter.clear()

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.headers["Retry-After"]
    assert second.json()["error"]["code"] == "rate_limit_exceeded"


def test_registration_is_rate_limited(client: TestClient) -> None:
    limiter = app.state.auth_rate_limiter
    original_limit = limiter.limit
    limiter.clear()
    limiter.limit = 1
    try:
        first = client.post(
            "/users/register",
            json={"email": "first@example.com", "password": "strong-password"},
        )
        second = client.post(
            "/users/register",
            json={"email": "second@example.com", "password": "strong-password"},
        )
    finally:
        limiter.limit = original_limit
        limiter.clear()

    assert first.status_code == 201
    assert second.status_code == 429


def test_readiness_checks_database(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_hides_database_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from remoteops import main

    def fail() -> None:
        raise OperationalError("statement", {}, Exception("private detail"))

    monkeypatch.setattr(main, "check_database", fail)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Service unavailable"
    assert "private detail" not in response.text


def test_server_http_exception_hides_detail(client: TestClient) -> None:
    @app.get("/_test/server-http-error")
    def server_http_error() -> None:
        raise HTTPException(status_code=503, detail="private upstream hostname")

    response = client.get("/_test/server-http-error")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Service unavailable"
    assert "private upstream hostname" not in response.text
