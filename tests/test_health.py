from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from remoteops.main import app, parse_cors_origins

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_disabled_by_default() -> None:
    assert not any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_parses_multiple_cors_origins() -> None:
    origins = parse_cors_origins(" http://localhost:5173 ,, https://app.example.com")

    assert origins == ["http://localhost:5173", "https://app.example.com"]


def test_parses_empty_cors_origins() -> None:
    assert parse_cors_origins("") == []
