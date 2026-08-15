from fastapi.testclient import TestClient


def create_organization(client: TestClient) -> str:
    response = client.post("/organizations", json={"name": "Acme"})
    assert response.status_code == 201
    return response.json()["id"]


def test_team_crud_and_pagination(auth_client: TestClient) -> None:
    organization_id = create_organization(auth_client)
    for name in ("Alpha", "Beta", "Gamma"):
        assert auth_client.post(
            f"/organizations/{organization_id}/teams", json={"name": name}
        ).status_code == 201

    page = auth_client.get(
        f"/organizations/{organization_id}/teams?limit=2&offset=1"
    ).json()
    team = page["items"][0]
    updated = auth_client.patch(
        f"/organizations/{organization_id}/teams/{team['id']}",
        json={"name": "Changed"},
    )
    deleted = auth_client.delete(
        f"/organizations/{organization_id}/teams/{team['id']}"
    )

    assert [item["name"] for item in page["items"]] == ["Beta", "Gamma"]
    assert page["total"] == 3
    assert updated.json()["name"] == "Changed"
    assert deleted.status_code == 204
    assert auth_client.get(
        f"/organizations/{organization_id}/teams/{team['id']}"
    ).status_code == 404


def test_contractor_crud(auth_client: TestClient) -> None:
    organization_id = create_organization(auth_client)
    created = auth_client.post(
        f"/organizations/{organization_id}/contractors",
        json={"name": "Ada", "email": "ADA@example.com"},
    )
    contractor = created.json()
    listed = auth_client.get(
        f"/organizations/{organization_id}/contractors"
    ).json()
    updated = auth_client.patch(
        f"/organizations/{organization_id}/contractors/{contractor['id']}",
        json={"name": "Ada Lovelace", "email": "ada@example.com"},
    )
    deleted = auth_client.delete(
        f"/organizations/{organization_id}/contractors/{contractor['id']}"
    )

    assert created.status_code == 201
    assert contractor["email"] == "ada@example.com"
    assert listed["total"] == 1
    assert updated.json()["name"] == "Ada Lovelace"
    assert deleted.status_code == 204


def test_project_crud(auth_client: TestClient) -> None:
    organization_id = create_organization(auth_client)
    created = auth_client.post(
        f"/organizations/{organization_id}/projects",
        json={"name": "Launch", "description": "Initial release"},
    )
    project = created.json()
    listed = auth_client.get(f"/organizations/{organization_id}/projects").json()
    updated = auth_client.patch(
        f"/organizations/{organization_id}/projects/{project['id']}",
        json={"name": "Launch", "description": "Ready"},
    )
    deleted = auth_client.delete(
        f"/organizations/{organization_id}/projects/{project['id']}"
    )

    assert created.status_code == 201
    assert listed["items"][0]["name"] == "Launch"
    assert updated.json()["description"] == "Ready"
    assert deleted.status_code == 204


def test_member_can_read_but_cannot_manage_resources(
    auth_client: TestClient,
) -> None:
    organization_id = create_organization(auth_client)
    credentials = {"email": "member@example.com", "password": "strong-password"}
    auth_client.post("/users/register", json=credentials)
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
        f"/organizations/{organization_id}/teams", headers=headers
    ).status_code == 200
    assert auth_client.post(
        f"/organizations/{organization_id}/teams",
        json={"name": "Forbidden"},
        headers=headers,
    ).status_code == 403
