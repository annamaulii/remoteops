from fastapi.testclient import TestClient


def test_organizations_require_authentication(client: TestClient) -> None:
    assert client.get("/organizations").status_code == 401


def register_user(client: TestClient, email: str) -> dict[str, str]:
    credentials = {"email": email, "password": "strong-password"}
    response = client.post("/users/register", json=credentials)
    assert response.status_code == 201
    return response.json()


def login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        data={"username": email, "password": "strong-password"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_creator_becomes_owner(auth_client: TestClient) -> None:
    organization = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()

    response = auth_client.get(f"/organizations/{organization['id']}/members")

    assert response.status_code == 200
    assert response.json()[0]["email"] == "owner@example.com"
    assert response.json()[0]["role"] == "owner"


def test_member_access_is_scoped_and_read_only(auth_client: TestClient) -> None:
    organization = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()
    register_user(auth_client, "member@example.com")
    added = auth_client.post(
        f"/organizations/{organization['id']}/members",
        json={"email": "member@example.com"},
    )
    member_headers = login_headers(auth_client, "member@example.com")

    visible = auth_client.get(
        f"/organizations/{organization['id']}", headers=member_headers
    )
    forbidden = auth_client.patch(
        f"/organizations/{organization['id']}",
        json={"name": "Changed"},
        headers=member_headers,
    )

    assert added.status_code == 201
    assert visible.status_code == 200
    assert forbidden.status_code == 403


def test_owner_manages_member_roles(auth_client: TestClient) -> None:
    organization = auth_client.post(
        "/organizations", json={"name": "Acme"}
    ).json()
    user = register_user(auth_client, "admin@example.com")
    auth_client.post(
        f"/organizations/{organization['id']}/members",
        json={"email": "admin@example.com"},
    )

    promoted = auth_client.patch(
        f"/organizations/{organization['id']}/members/{user['id']}",
        json={"role": "admin"},
    )
    admin_update = auth_client.patch(
        f"/organizations/{organization['id']}",
        json={"name": "Admin changed"},
        headers=login_headers(auth_client, "admin@example.com"),
    )
    removed = auth_client.delete(
        f"/organizations/{organization['id']}/members/{user['id']}"
    )

    assert promoted.json()["role"] == "admin"
    assert admin_update.status_code == 200
    assert removed.status_code == 204


def test_non_member_cannot_discover_organization(auth_client: TestClient) -> None:
    organization = auth_client.post(
        "/organizations", json={"name": "Private"}
    ).json()
    register_user(auth_client, "outsider@example.com")

    response = auth_client.get(
        f"/organizations/{organization['id']}",
        headers=login_headers(auth_client, "outsider@example.com"),
    )

    assert response.status_code == 404
