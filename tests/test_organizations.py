import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from remoteops.database import SessionFactory
from remoteops.main import app
from remoteops.models import IdempotencyRecord, Organization, User


def test_create_and_get_organization(auth_client: TestClient) -> None:
    create_response = auth_client.post("/organizations", json={"name": "Acme GmbH"})

    assert create_response.status_code == 201
    created = create_response.json()
    assert UUID(created["id"])
    assert created["name"] == "Acme GmbH"
    assert created["created_at"]

    get_response = auth_client.get(f"/organizations/{created['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == created


def test_create_organization_rejects_duplicate_name(auth_client: TestClient) -> None:
    first_response = auth_client.post("/organizations", json={"name": "Duplicate"})

    response = auth_client.post("/organizations", json={"name": "Duplicate"})

    assert first_response.status_code == 201
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Organization name already exists"


def test_get_organization_reports_missing_id(auth_client: TestClient) -> None:
    response = auth_client.get(f"/organizations/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Organization not found"


def test_create_organization_validates_name(auth_client: TestClient) -> None:
    assert auth_client.post("/organizations", json={"name": "   "}).status_code == 422
    assert (
        auth_client.post("/organizations", json={"name": "a" * 256}).status_code == 422
    )


def test_create_organization_without_idempotency_key_creates_no_record(
    auth_client: TestClient, db_session: Session
) -> None:
    response = auth_client.post("/organizations", json={"name": "Ordinary"})

    assert response.status_code == 201
    assert db_session.scalar(select(func.count(IdempotencyRecord.id))) == 0


def test_create_organization_replays_idempotent_response(
    auth_client: TestClient, db_session: Session
) -> None:
    headers = {"Idempotency-Key": "create-acme-1"}

    first = auth_client.post(
        "/organizations", json={"name": "Idempotent Acme"}, headers=headers
    )
    replay = auth_client.post(
        "/organizations", json={"name": "Idempotent Acme"}, headers=headers
    )

    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()
    assert replay.headers["X-Idempotent-Replayed"] == "true"
    assert db_session.scalar(select(func.count(Organization.id))) == 1
    assert db_session.scalar(select(func.count(IdempotencyRecord.id))) == 1
    record = db_session.scalars(select(IdempotencyRecord)).one()
    assert record.key_hash != headers["Idempotency-Key"]
    assert len(record.key_hash) == 64


def test_idempotency_uses_normalized_payload(auth_client: TestClient) -> None:
    headers = {"Idempotency-Key": "normalized-1"}
    first = auth_client.post(
        "/organizations", json={"name": "Normalized"}, headers=headers
    )

    replay = auth_client.post(
        "/organizations", json={"name": "  Normalized  "}, headers=headers
    )

    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert replay.headers["X-Idempotent-Replayed"] == "true"


def test_idempotency_rejects_different_payload(auth_client: TestClient) -> None:
    headers = {"Idempotency-Key": "conflict-1"}
    auth_client.post("/organizations", json={"name": "First payload"}, headers=headers)

    response = auth_client.post(
        "/organizations", json={"name": "Different payload"}, headers=headers
    )

    assert response.status_code == 409
    assert "different request" in response.json()["error"]["message"]


def test_different_users_can_reuse_idempotency_key(
    auth_client: TestClient, client: TestClient, db_session: Session
) -> None:
    key = {"Idempotency-Key": "shared-key"}
    assert (
        auth_client.post(
            "/organizations", json={"name": "First user's org"}, headers=key
        ).status_code
        == 201
    )
    credentials = {"email": "second@example.com", "password": "strong-password"}
    assert client.post("/users/register", json=credentials).status_code == 201
    login = client.post(
        "/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    response = client.post(
        "/organizations", json={"name": "Second user's org"}, headers=key
    )

    assert response.status_code == 201
    assert db_session.scalar(select(func.count(IdempotencyRecord.id))) == 2


@pytest.mark.parametrize("key", ["", "contains space", "contains/slash", "x" * 256])
def test_idempotency_key_is_validated(auth_client: TestClient, key: str) -> None:
    response = auth_client.post(
        "/organizations",
        json={"name": f"Invalid key {len(key)}"},
        headers={"Idempotency-Key": key},
    )

    assert response.status_code == 422


def test_concurrent_idempotent_requests_create_one_organization() -> None:
    unique = uuid4().hex
    credentials = {
        "email": f"concurrent-{unique}@example.com",
        "password": "strong-password",
    }
    organization_name = f"Concurrent {unique}"
    headers = {"Idempotency-Key": f"concurrent-{unique}"}
    key_hash = hashlib.sha256(headers["Idempotency-Key"].encode()).hexdigest()
    with TestClient(app) as setup_client:
        assert setup_client.post("/users/register", json=credentials).status_code == 201
        login = setup_client.post(
            "/auth/login",
            data={
                "username": credentials["email"],
                "password": credentials["password"],
            },
        )
        authorization = f"Bearer {login.json()['access_token']}"

    def create() -> tuple[int, dict, str | None]:
        with TestClient(app, headers={"Authorization": authorization}) as thread_client:
            response = thread_client.post(
                "/organizations", json={"name": organization_name}, headers=headers
            )
            return (
                response.status_code,
                response.json(),
                response.headers.get("X-Idempotent-Replayed"),
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create(), range(2)))

        assert [result[0] for result in results] == [201, 201]
        assert results[0][1] == results[1][1]
        assert sorted(result[2] or "false" for result in results) == ["false", "true"]
        with SessionFactory() as session:
            assert (
                session.scalar(
                    select(func.count(Organization.id)).where(
                        Organization.name == organization_name
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count(IdempotencyRecord.id)).where(
                        IdempotencyRecord.key_hash == key_hash
                    )
                )
                == 1
            )
    finally:
        with SessionFactory.begin() as session:
            user = session.scalar(
                select(User).where(User.email == credentials["email"])
            )
            organization = session.scalar(
                select(Organization).where(Organization.name == organization_name)
            )
            if user is not None:
                session.delete(user)
            if organization is not None:
                session.delete(organization)


def test_list_organizations_paginates(auth_client: TestClient) -> None:
    for name in ("Alpha", "Beta", "Gamma"):
        assert (
            auth_client.post("/organizations", json={"name": name}).status_code == 201
        )

    response = auth_client.get("/organizations?limit=2&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Beta", "Gamma"]
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_list_organizations_validates_pagination(auth_client: TestClient) -> None:
    assert auth_client.get("/organizations?limit=0").status_code == 422
    assert auth_client.get("/organizations?limit=101").status_code == 422
    assert auth_client.get("/organizations?offset=-1").status_code == 422


def test_update_organization(auth_client: TestClient) -> None:
    created = auth_client.post("/organizations", json={"name": "Old name"}).json()

    response = auth_client.patch(
        f"/organizations/{created['id']}", json={"name": "New name"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New name"


def test_update_organization_handles_conflicts_and_missing_ids(
    auth_client: TestClient,
) -> None:
    first = auth_client.post("/organizations", json={"name": "First"}).json()
    auth_client.post("/organizations", json={"name": "Second"})

    conflict = auth_client.patch(
        f"/organizations/{first['id']}", json={"name": "Second"}
    )
    missing = auth_client.patch(f"/organizations/{uuid4()}", json={"name": "Missing"})

    assert conflict.status_code == 409
    assert missing.status_code == 404


def test_delete_organization(auth_client: TestClient) -> None:
    created = auth_client.post("/organizations", json={"name": "Temporary"}).json()

    response = auth_client.delete(f"/organizations/{created['id']}")

    assert response.status_code == 204
    assert auth_client.get(f"/organizations/{created['id']}").status_code == 404
    assert auth_client.delete(f"/organizations/{uuid4()}").status_code == 404
