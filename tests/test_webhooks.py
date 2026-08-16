import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from remoteops.config import settings
from remoteops.models import WebhookAttempt, WebhookDelivery, WebhookSubscription
from remoteops.webhooks import process_due_deliveries


def create_subscription(client: TestClient, name: str = "Acme") -> tuple[str, dict]:
    organization_id = client.post("/organizations", json={"name": name}).json()["id"]
    response = client.post(
        f"/organizations/{organization_id}/webhooks",
        json={
            "url": "https://webhooks.example.com/remoteops",
            "event": "leave_request.decided",
        },
    )
    assert response.status_code == 201
    return organization_id, response.json()


def test_subscription_secret_is_returned_only_on_create(
    auth_client: TestClient,
) -> None:
    organization_id, created = create_subscription(auth_client)
    listed = auth_client.get(f"/organizations/{organization_id}/webhooks")

    assert len(created["signing_secret"]) == 64
    assert "signing_secret" not in listed.json()[0]
    assert (
        auth_client.delete(
            f"/organizations/{organization_id}/webhooks/{created['id']}"
        ).status_code
        == 204
    )
    assert auth_client.get(f"/organizations/{organization_id}/webhooks").json() == []


def test_webhook_url_validation_blocks_ssrf_shapes(auth_client: TestClient) -> None:
    organization_id = auth_client.post("/organizations", json={"name": "Acme"}).json()[
        "id"
    ]
    invalid_urls = [
        "http://webhooks.example.com/hook",
        "https://localhost/hook",
        "https://webhooks.example.com.evil.test/hook",
        "https://user@webhooks.example.com/hook",
        "https://webhooks.example.com:444/hook",
        "https://webhooks.example.com/hook#fragment",
    ]

    for url in invalid_urls:
        response = auth_client.post(
            f"/organizations/{organization_id}/webhooks",
            json={"url": url, "event": "leave_request.decided"},
        )
        assert response.status_code == 422


def test_subscription_requires_signing_secret(
    auth_client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id = auth_client.post("/organizations", json={"name": "Acme"}).json()[
        "id"
    ]
    monkeypatch.setattr(settings, "webhook_signing_secret", None)

    response = auth_client.post(
        f"/organizations/{organization_id}/webhooks",
        json={
            "url": "https://webhooks.example.com/remoteops",
            "event": "leave_request.decided",
        },
    )

    assert response.status_code == 503
    assert db_session.scalar(select(WebhookSubscription)) is None


def test_webhook_management_enforces_rbac_and_idor(auth_client: TestClient) -> None:
    first_id, created = create_subscription(auth_client, "First")
    second_id = auth_client.post("/organizations", json={"name": "Second"}).json()["id"]
    credentials = {"email": "member@example.com", "password": "strong-password"}
    user = auth_client.post("/users/register", json=credentials).json()
    auth_client.post(
        f"/organizations/{first_id}/members",
        json={"email": credentials["email"], "role": "member"},
    )
    login = auth_client.post(
        "/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    ).json()
    member_headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert (
        auth_client.post(
            f"/organizations/{first_id}/webhooks",
            json={
                "url": "https://webhooks.example.com/member",
                "event": "leave_request.decided",
            },
            headers=member_headers,
        ).status_code
        == 403
    )
    assert (
        auth_client.get(
            f"/organizations/{first_id}/webhooks", headers=member_headers
        ).status_code
        == 403
    )
    assert (
        auth_client.delete(
            f"/organizations/{second_id}/webhooks/{created['id']}"
        ).status_code
        == 404
    )
    assert user["email"] == credentials["email"]


def test_leave_decision_enqueues_delivery_in_same_transaction(
    auth_client: TestClient, db_session: Session
) -> None:
    organization_id, _ = create_subscription(auth_client)
    contractor_id = auth_client.post(
        f"/organizations/{organization_id}/contractors",
        json={"name": "Ada", "email": "ada@example.com"},
    ).json()["id"]
    leave_id = auth_client.post(
        f"/organizations/{organization_id}/leave-requests",
        json={
            "contractor_id": contractor_id,
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
        },
    ).json()["id"]

    response = auth_client.post(
        f"/organizations/{organization_id}/leave-requests/{leave_id}/decision",
        json={"decision": "approved"},
    )
    delivery = db_session.scalar(select(WebhookDelivery))

    assert response.status_code == 201
    assert json.loads(delivery.payload) == {
        "event": "leave_request.decided",
        "data": {"decision": "approved", "leave_request_id": leave_id},
    }


def queued_delivery(
    auth_client: TestClient, db_session: Session
) -> tuple[str, WebhookDelivery, str]:
    organization_id, subscription = create_subscription(auth_client)
    contractor_id = auth_client.post(
        f"/organizations/{organization_id}/contractors",
        json={"name": "Ada", "email": "ada@example.com"},
    ).json()["id"]
    leave_id = auth_client.post(
        f"/organizations/{organization_id}/leave-requests",
        json={
            "contractor_id": contractor_id,
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
        },
    ).json()["id"]
    auth_client.post(
        f"/organizations/{organization_id}/leave-requests/{leave_id}/decision",
        json={"decision": "approved"},
    )
    return (
        organization_id,
        db_session.scalar(select(WebhookDelivery)),
        subscription["signing_secret"],
    )


def test_worker_signs_exact_stored_payload_and_succeeds(
    auth_client: TestClient, db_session: Session
) -> None:
    organization_id, delivery, secret = queued_delivery(auth_client, db_session)
    now = datetime.now(UTC) + timedelta(seconds=1)
    captured = {}

    def sender(url: str, content: bytes, headers: dict[str, str]) -> int:
        captured.update(url=url, content=content, headers=headers)
        return 204

    process_due_deliveries(db_session, sender, now=now)
    expected = hmac.new(
        secret.encode(),
        str(int(now.timestamp())).encode() + b"." + delivery.payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    assert captured["content"] == delivery.payload.encode()
    assert captured["headers"]["X-RemoteOps-Delivery"] == str(delivery.id)
    assert captured["headers"]["X-RemoteOps-Signature"] == f"sha256={expected}"
    assert delivery.status == "succeeded"
    assert delivery.attempt_count == 1
    history = auth_client.get(
        f"/organizations/{organization_id}/webhook-deliveries"
    ).json()
    assert history[0]["attempts"][0]["status_code"] == 204
    assert (
        auth_client.get(
            f"/organizations/{organization_id}/webhook-deliveries?limit=0"
        ).status_code
        == 422
    )


def test_worker_retries_then_fails_without_storing_exception(
    auth_client: TestClient, db_session: Session
) -> None:
    _, delivery, _ = queued_delivery(auth_client, db_session)
    now = datetime.now(UTC) + timedelta(seconds=1)

    def unavailable(_url: str, _content: bytes, _headers: dict[str, str]) -> int:
        return 503

    process_due_deliveries(db_session, unavailable, now=now)
    assert delivery.status == "retrying"
    assert delivery.next_attempt_at == now + timedelta(seconds=60)

    delivery.attempt_count = 4
    delivery.next_attempt_at = now

    def network_error(_url: str, _content: bytes, _headers: dict[str, str]) -> int:
        raise httpx.ConnectError("private internal detail")

    process_due_deliveries(db_session, network_error, now=now)
    attempt = db_session.scalar(
        select(WebhookAttempt).where(WebhookAttempt.attempt_number == 5)
    )
    assert delivery.status == "failed"
    assert attempt.error_code == "network_error"
    assert "private internal detail" not in repr(attempt.__dict__)


def test_worker_skips_not_due_delivery(
    auth_client: TestClient, db_session: Session
) -> None:
    _, delivery, _ = queued_delivery(auth_client, db_session)
    delivery.next_attempt_at = datetime.now(UTC) + timedelta(hours=1)
    db_session.flush()

    called = False

    def sender(_url: str, _content: bytes, _headers: dict[str, str]) -> int:
        nonlocal called
        called = True
        return 200

    assert process_due_deliveries(db_session, sender) == 0
    assert called is False
    assert delivery.status == "pending"
