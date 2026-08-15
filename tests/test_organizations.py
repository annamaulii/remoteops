from uuid import UUID, uuid4

from fastapi.testclient import TestClient


def test_create_and_get_organization(client: TestClient) -> None:
    create_response = client.post("/organizations", json={"name": "Acme GmbH"})

    assert create_response.status_code == 201
    created = create_response.json()
    assert UUID(created["id"])
    assert created["name"] == "Acme GmbH"
    assert created["created_at"]

    get_response = client.get(f"/organizations/{created['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == created


def test_create_organization_rejects_duplicate_name(client: TestClient) -> None:
    first_response = client.post("/organizations", json={"name": "Duplicate"})

    response = client.post("/organizations", json={"name": "Duplicate"})

    assert first_response.status_code == 201
    assert response.status_code == 409
    assert response.json() == {"detail": "Organization name already exists"}


def test_get_organization_reports_missing_id(client: TestClient) -> None:
    response = client.get(f"/organizations/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Organization not found"}


def test_create_organization_validates_name(client: TestClient) -> None:
    assert client.post("/organizations", json={"name": "   "}).status_code == 422
    assert client.post("/organizations", json={"name": "a" * 256}).status_code == 422


def test_list_organizations_paginates(client: TestClient) -> None:
    for name in ("Alpha", "Beta", "Gamma"):
        assert client.post("/organizations", json={"name": name}).status_code == 201

    response = client.get("/organizations?limit=2&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["Beta", "Gamma"]
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_list_organizations_validates_pagination(client: TestClient) -> None:
    assert client.get("/organizations?limit=0").status_code == 422
    assert client.get("/organizations?limit=101").status_code == 422
    assert client.get("/organizations?offset=-1").status_code == 422
