from fastapi.testclient import TestClient


def create_context(client: TestClient, name: str = "Acme") -> tuple[str, str, str]:
    organization_id = client.post(
        "/organizations", json={"name": name}
    ).json()["id"]
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
    listed = auth_client.get(
        f"/organizations/{organization_id}/work-logs"
    )

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
        f"/organizations/{organization_id}/leave-requests"
    )

    assert leave.status_code == 201
    assert approval.status_code == 201
    assert approval.json()["decision"] == "approved"
    assert duplicate.status_code == 409
    assert listed.json()[0]["status"] == "approved"


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
