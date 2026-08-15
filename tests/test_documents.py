from fastapi.testclient import TestClient


def test_document_crud_creates_immutable_audit_history(
    auth_client: TestClient,
) -> None:
    organization_id = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()["id"]
    created = auth_client.post(
        f"/organizations/{organization_id}/documents",
        json={
            "name": "contract.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
        },
    )
    document_id = created.json()["id"]
    listed = auth_client.get(
        f"/organizations/{organization_id}/documents?limit=1"
    ).json()
    updated = auth_client.patch(
        f"/organizations/{organization_id}/documents/{document_id}",
        json={
            "name": "signed-contract.pdf",
            "content_type": "application/pdf",
            "size_bytes": 2048,
        },
    )
    deleted = auth_client.delete(
        f"/organizations/{organization_id}/documents/{document_id}"
    )
    audit = auth_client.get(
        f"/organizations/{organization_id}/audit-events"
    ).json()

    assert created.status_code == 201
    assert listed["total"] == 1
    assert updated.json()["name"] == "signed-contract.pdf"
    assert deleted.status_code == 204
    assert {event["action"] for event in audit["items"]} == {
        "created",
        "updated",
        "deleted",
    }
    assert all(event["entity_id"] == document_id for event in audit["items"])


def test_document_metadata_is_validated(auth_client: TestClient) -> None:
    organization_id = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()["id"]

    assert auth_client.post(
        f"/organizations/{organization_id}/documents",
        json={"name": "file", "content_type": "text/plain", "size_bytes": -1},
    ).status_code == 422
    assert auth_client.post(
        f"/organizations/{organization_id}/documents",
        json={
            "name": "file",
            "content_type": "text/plain",
            "size_bytes": 1,
            "storage_key": "must-not-be-accepted",
        },
    ).status_code == 422


def test_document_names_are_unique(auth_client: TestClient) -> None:
    organization_id = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()["id"]
    data = {"name": "file.txt", "content_type": "text/plain", "size_bytes": 1}

    assert auth_client.post(
        f"/organizations/{organization_id}/documents", json=data
    ).status_code == 201
    assert auth_client.post(
        f"/organizations/{organization_id}/documents", json=data
    ).status_code == 409


def test_member_can_read_documents_but_not_audit_events(
    auth_client: TestClient,
) -> None:
    organization_id = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()["id"]
    credentials = {"email": "member@example.com", "password": "strong-password"}
    member = auth_client.post("/users/register", json=credentials).json()
    auth_client.post(
        f"/organizations/{organization_id}/members",
        json={"email": credentials["email"]},
    )
    login = auth_client.post(
        "/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert auth_client.get(
        f"/organizations/{organization_id}/documents", headers=headers
    ).status_code == 200
    assert auth_client.post(
        f"/organizations/{organization_id}/documents",
        json={"name": "file", "content_type": "text/plain", "size_bytes": 1},
        headers=headers,
    ).status_code == 403
    assert auth_client.get(
        f"/organizations/{organization_id}/audit-events", headers=headers
    ).status_code == 403
    assert member["email"] == credentials["email"]


def test_leave_decision_creates_audit_event(auth_client: TestClient) -> None:
    organization_id = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()["id"]
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
    audit = auth_client.get(
        f"/organizations/{organization_id}/audit-events"
    ).json()

    assert audit["total"] == 1
    assert audit["items"][0]["action"] == "approved"
    assert audit["items"][0]["entity_type"] == "leave_request"


def test_document_and_audit_data_are_tenant_isolated(
    auth_client: TestClient,
) -> None:
    organization_id = auth_client.post(
        "/organizations", json={"name": "Private"}
    ).json()["id"]
    document_id = auth_client.post(
        f"/organizations/{organization_id}/documents",
        json={"name": "secret", "content_type": "text/plain", "size_bytes": 1},
    ).json()["id"]
    credentials = {"email": "outsider@example.com", "password": "strong-password"}
    auth_client.post("/users/register", json=credentials)
    login = auth_client.post(
        "/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert auth_client.get(
        f"/organizations/{organization_id}/documents/{document_id}", headers=headers
    ).status_code == 404
    assert auth_client.patch(
        f"/organizations/{organization_id}/documents/{document_id}",
        json={"name": "stolen", "content_type": "text/plain", "size_bytes": 1},
        headers=headers,
    ).status_code == 404
    assert auth_client.get(
        f"/organizations/{organization_id}/audit-events", headers=headers
    ).status_code == 404
