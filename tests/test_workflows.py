from uuid import uuid4

from fastapi.testclient import TestClient


def create_context(client: TestClient, name: str = "Acme") -> tuple[str, str, str]:
    organization_id = client.post("/organizations", json={"name": name}).json()["id"]
    contractor_id = client.post(
        f"/organizations/{organization_id}/contractors",
        json={"name": "Ada", "email": f"ada-{name}@example.com"},
    ).json()["id"]
    project_id = client.post(
        f"/organizations/{organization_id}/projects",
        json={"name": "Launch"},
    ).json()["id"]
    return organization_id, contractor_id, project_id


def test_records_and_lists_work_logs(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)

    created = auth_client.post(
        f"/organizations/{organization_id}/work-logs",
        json={
            "contractor_id": contractor_id,
            "project_id": project_id,
            "work_date": "2026-08-15",
            "minutes": 480,
            "description": "Backend work",
        },
    )
    listed = auth_client.get(f"/organizations/{organization_id}/work-logs")

    assert created.status_code == 201
    assert created.json()["minutes"] == 480
    assert listed.json()[0]["id"] == created.json()["id"]


def test_rejects_cross_organization_work_log(auth_client: TestClient) -> None:
    organization_id, contractor_id, _ = create_context(auth_client, "First")
    _, _, other_project_id = create_context(auth_client, "Second")

    response = auth_client.post(
        f"/organizations/{organization_id}/work-logs",
        json={
            "contractor_id": contractor_id,
            "project_id": other_project_id,
            "work_date": "2026-08-15",
            "minutes": 60,
        },
    )

    assert response.status_code == 404


def create_work_log(
    client: TestClient, organization_id: str, contractor_id: str, project_id: str
) -> str:
    response = client.post(
        f"/organizations/{organization_id}/work-logs",
        json={
            "contractor_id": contractor_id,
            "project_id": project_id,
            "work_date": "2026-08-15",
            "minutes": 120,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def register_user(client: TestClient, email: str) -> None:
    response = client.post(
        "/users/register",
        json={"email": email, "password": "strong-password"},
    )
    assert response.status_code == 201


def login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        data={"username": email, "password": "strong-password"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_work_log_is_submitted_by_default(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)

    created = auth_client.post(
        f"/organizations/{organization_id}/work-logs",
        json={
            "contractor_id": contractor_id,
            "project_id": project_id,
            "work_date": "2026-08-15",
            "minutes": 60,
        },
    )

    assert created.json()["status"] == "submitted"


def test_work_log_approval_is_transactional(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    work_log_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )

    approval = auth_client.post(
        f"/organizations/{organization_id}/work-logs/{work_log_id}/decision",
        json={"decision": "approved", "note": "Looks good"},
    )
    duplicate = auth_client.post(
        f"/organizations/{organization_id}/work-logs/{work_log_id}/decision",
        json={"decision": "rejected"},
    )
    listed = auth_client.get(f"/organizations/{organization_id}/work-logs")

    assert approval.status_code == 201
    assert approval.json()["decision"] == "approved"
    assert approval.json()["work_log_id"] == work_log_id
    assert approval.json()["leave_request_id"] is None
    assert duplicate.status_code == 409
    assert listed.json()[0]["status"] == "approved"


def test_work_log_decision_requires_admin_role(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    work_log_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )
    register_user(auth_client, "member@example.com")
    auth_client.post(
        f"/organizations/{organization_id}/members",
        json={"email": "member@example.com"},
    )
    member_headers = login_headers(auth_client, "member@example.com")

    response = auth_client.post(
        f"/organizations/{organization_id}/work-logs/{work_log_id}/decision",
        json={"decision": "approved"},
        headers=member_headers,
    )

    assert response.status_code == 403


def test_work_log_decision_requires_authentication(client: TestClient) -> None:
    response = client.post(
        f"/organizations/{uuid4()}/work-logs/{uuid4()}/decision",
        json={"decision": "approved"},
    )

    assert response.status_code == 401


def test_rejects_cross_organization_work_log_decision(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client, "First")
    other_organization_id, _, _ = create_context(auth_client, "Second")
    work_log_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )

    response = auth_client.post(
        f"/organizations/{other_organization_id}/work-logs/{work_log_id}/decision",
        json={"decision": "approved"},
    )

    assert response.status_code == 404


def test_work_log_decision_reports_missing_work_log(auth_client: TestClient) -> None:
    organization_id, _, _ = create_context(auth_client)

    response = auth_client.post(
        f"/organizations/{organization_id}/work-logs/{uuid4()}/decision",
        json={"decision": "approved"},
    )

    assert response.status_code == 404


def test_leave_request_approval_is_transactional(auth_client: TestClient) -> None:
    organization_id, contractor_id, _ = create_context(auth_client)
    leave = auth_client.post(
        f"/organizations/{organization_id}/leave-requests",
        json={
            "contractor_id": contractor_id,
            "start_date": "2026-09-01",
            "end_date": "2026-09-05",
            "reason": "Holiday",
        },
    )
    leave_id = leave.json()["id"]

    approval = auth_client.post(
        f"/organizations/{organization_id}/leave-requests/{leave_id}/decision",
        json={"decision": "approved", "note": "Approved"},
    )
    duplicate = auth_client.post(
        f"/organizations/{organization_id}/leave-requests/{leave_id}/decision",
        json={"decision": "rejected"},
    )
    listed = auth_client.get(
        f"/organizations/{organization_id}/leave-requests?limit=1&offset=0"
    )

    assert leave.status_code == 201
    assert approval.status_code == 201
    assert approval.json()["decision"] == "approved"
    assert duplicate.status_code == 409
    assert listed.json()[0]["status"] == "approved"


def test_leave_request_pagination_is_validated(auth_client: TestClient) -> None:
    organization_id, _, _ = create_context(auth_client)

    assert (
        auth_client.get(
            f"/organizations/{organization_id}/leave-requests?limit=0"
        ).status_code
        == 422
    )
    assert (
        auth_client.get(
            f"/organizations/{organization_id}/leave-requests?offset=-1"
        ).status_code
        == 422
    )


def test_rejects_invalid_leave_dates(auth_client: TestClient) -> None:
    organization_id, contractor_id, _ = create_context(auth_client)

    response = auth_client.post(
        f"/organizations/{organization_id}/leave-requests",
        json={
            "contractor_id": contractor_id,
            "start_date": "2026-09-05",
            "end_date": "2026-09-01",
        },
    )

    assert response.status_code == 422
