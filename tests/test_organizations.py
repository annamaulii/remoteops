from uuid import UUID, uuid4

from fastapi.testclient import TestClient


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
        auth_client.post("/organizations", json={"name": "a" * 256}).status_code
        == 422
    )


def test_list_organizations_paginates(auth_client: TestClient) -> None:
    for name in ("Alpha", "Beta", "Gamma"):
        assert (
            auth_client.post("/organizations", json={"name": name}).status_code
            == 201
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
    missing = auth_client.patch(
        f"/organizations/{uuid4()}", json={"name": "Missing"}
    )

    assert conflict.status_code == 409
    assert missing.status_code == 404


def test_delete_organization(auth_client: TestClient) -> None:
    created = auth_client.post("/organizations", json={"name": "Temporary"}).json()

    response = auth_client.delete(f"/organizations/{created['id']}")

    assert response.status_code == 204
    assert auth_client.get(f"/organizations/{created['id']}").status_code == 404
    assert auth_client.delete(f"/organizations/{uuid4()}").status_code == 404
