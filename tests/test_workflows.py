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
    assert listed.json()["items"][0]["id"] == created.json()["id"]


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
    client: TestClient,
    organization_id: str,
    contractor_id: str,
    project_id: str,
    *,
    work_date: str = "2026-08-15",
) -> str:
    response = client.post(
        f"/organizations/{organization_id}/work-logs",
        json={
            "contractor_id": contractor_id,
            "project_id": project_id,
            "work_date": work_date,
            "minutes": 120,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def decide_work_log(
    client: TestClient, organization_id: str, work_log_id: str, decision: str
) -> None:
    response = client.post(
        f"/organizations/{organization_id}/work-logs/{work_log_id}/decision",
        json={"decision": decision},
    )
    assert response.status_code == 201


def create_leave_request(
    client: TestClient, organization_id: str, contractor_id: str
) -> str:
    response = client.post(
        f"/organizations/{organization_id}/leave-requests",
        json={
            "contractor_id": contractor_id,
            "start_date": "2026-09-01",
            "end_date": "2026-09-02",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def decide_leave_request(
    client: TestClient, organization_id: str, leave_id: str, decision: str
) -> None:
    response = client.post(
        f"/organizations/{organization_id}/leave-requests/{leave_id}/decision",
        json={"decision": decision},
    )
    assert response.status_code == 201


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
    assert listed.json()["items"][0]["status"] == "approved"


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
    assert listed.json()["items"][0]["status"] == "approved"


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


def test_work_log_list_is_empty_by_default(auth_client: TestClient) -> None:
    organization_id, _, _ = create_context(auth_client)

    response = auth_client.get(f"/organizations/{organization_id}/work-logs")

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_work_log_pagination_reports_total_and_respects_limit_offset(
    auth_client: TestClient,
) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    for day in range(1, 6):
        create_work_log(
            auth_client,
            organization_id,
            contractor_id,
            project_id,
            work_date=f"2026-08-{day:02d}",
        )

    first_page = auth_client.get(
        f"/organizations/{organization_id}/work-logs?limit=2&offset=0"
    ).json()
    second_page = auth_client.get(
        f"/organizations/{organization_id}/work-logs?limit=2&offset=4"
    ).json()
    beyond_end = auth_client.get(
        f"/organizations/{organization_id}/work-logs?limit=2&offset=10"
    ).json()

    assert first_page["total"] == 5
    assert len(first_page["items"]) == 2
    assert [item["work_date"] for item in first_page["items"]] == [
        "2026-08-05",
        "2026-08-04",
    ]
    assert second_page["total"] == 5
    assert len(second_page["items"]) == 1
    assert beyond_end["total"] == 5
    assert beyond_end["items"] == []


def test_work_log_pagination_rejects_invalid_limit_and_offset(
    auth_client: TestClient,
) -> None:
    organization_id, _, _ = create_context(auth_client)

    assert (
        auth_client.get(
            f"/organizations/{organization_id}/work-logs?limit=0"
        ).status_code
        == 422
    )
    assert (
        auth_client.get(
            f"/organizations/{organization_id}/work-logs?offset=-1"
        ).status_code
        == 422
    )


def test_work_log_filters_by_status(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    approved_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )
    rejected_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )
    create_work_log(auth_client, organization_id, contractor_id, project_id)
    decide_work_log(auth_client, organization_id, approved_id, "approved")
    decide_work_log(auth_client, organization_id, rejected_id, "rejected")

    approved = auth_client.get(
        f"/organizations/{organization_id}/work-logs?status=approved"
    ).json()
    submitted = auth_client.get(
        f"/organizations/{organization_id}/work-logs?status=submitted"
    ).json()

    assert approved["total"] == 1
    assert approved["items"][0]["id"] == approved_id
    assert submitted["total"] == 1


def test_work_log_filters_by_contractor_and_project(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    other_contractor_id = auth_client.post(
        f"/organizations/{organization_id}/contractors",
        json={"name": "Grace", "email": "grace@example.com"},
    ).json()["id"]
    other_project_id = auth_client.post(
        f"/organizations/{organization_id}/projects", json={"name": "Migrate"}
    ).json()["id"]
    create_work_log(auth_client, organization_id, contractor_id, project_id)
    create_work_log(auth_client, organization_id, other_contractor_id, other_project_id)

    by_contractor = auth_client.get(
        f"/organizations/{organization_id}/work-logs?contractor_id={contractor_id}"
    ).json()
    by_project = auth_client.get(
        f"/organizations/{organization_id}/work-logs?project_id={other_project_id}"
    ).json()

    assert by_contractor["total"] == 1
    assert by_contractor["items"][0]["contractor_id"] == contractor_id
    assert by_project["total"] == 1
    assert by_project["items"][0]["project_id"] == other_project_id


def test_work_log_filters_by_date_range(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    create_work_log(
        auth_client, organization_id, contractor_id, project_id, work_date="2026-08-01"
    )
    create_work_log(
        auth_client, organization_id, contractor_id, project_id, work_date="2026-08-10"
    )
    create_work_log(
        auth_client, organization_id, contractor_id, project_id, work_date="2026-08-20"
    )

    in_range = auth_client.get(
        f"/organizations/{organization_id}/work-logs"
        "?work_date_from=2026-08-05&work_date_to=2026-08-15"
    ).json()

    assert in_range["total"] == 1
    assert in_range["items"][0]["work_date"] == "2026-08-10"


def test_work_log_filters_combine_with_and_semantics(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    matching_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id, work_date="2026-08-10"
    )
    create_work_log(
        auth_client, organization_id, contractor_id, project_id, work_date="2026-08-10"
    )
    decide_work_log(auth_client, organization_id, matching_id, "approved")

    response = auth_client.get(
        f"/organizations/{organization_id}/work-logs"
        f"?status=approved&contractor_id={contractor_id}&work_date_from=2026-08-10"
    ).json()

    assert response["total"] == 1
    assert response["items"][0]["id"] == matching_id


def test_work_log_rejects_invalid_date_range(auth_client: TestClient) -> None:
    organization_id, _, _ = create_context(auth_client)

    response = auth_client.get(
        f"/organizations/{organization_id}/work-logs"
        "?work_date_from=2026-08-20&work_date_to=2026-08-01"
    )

    assert response.status_code == 422


def test_work_log_rejects_invalid_status_filter(auth_client: TestClient) -> None:
    organization_id, _, _ = create_context(auth_client)

    response = auth_client.get(
        f"/organizations/{organization_id}/work-logs?status=bogus"
    )

    assert response.status_code == 422


def test_work_log_list_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/organizations/{uuid4()}/work-logs")

    assert response.status_code == 401


def test_work_log_list_is_organization_scoped(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client, "First")
    other_organization_id, other_contractor_id, other_project_id = create_context(
        auth_client, "Second"
    )
    create_work_log(auth_client, organization_id, contractor_id, project_id)
    create_work_log(
        auth_client, other_organization_id, other_contractor_id, other_project_id
    )

    first_org_logs = auth_client.get(
        f"/organizations/{organization_id}/work-logs"
    ).json()

    assert first_org_logs["total"] == 1


def test_list_approvals_paginates_and_filters(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client)
    work_log_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )
    leave_id = create_leave_request(auth_client, organization_id, contractor_id)
    decide_work_log(auth_client, organization_id, work_log_id, "approved")
    decide_leave_request(auth_client, organization_id, leave_id, "rejected")

    all_approvals = auth_client.get(
        f"/organizations/{organization_id}/approvals"
    ).json()
    work_log_only = auth_client.get(
        f"/organizations/{organization_id}/approvals?target_type=work_log"
    ).json()
    rejected_only = auth_client.get(
        f"/organizations/{organization_id}/approvals?decision=rejected"
    ).json()

    assert all_approvals["total"] == 2
    assert work_log_only["total"] == 1
    assert work_log_only["items"][0]["work_log_id"] == work_log_id
    assert rejected_only["total"] == 1
    assert rejected_only["items"][0]["leave_request_id"] == leave_id


def test_list_approvals_is_organization_scoped(auth_client: TestClient) -> None:
    organization_id, contractor_id, project_id = create_context(auth_client, "First")
    other_organization_id, other_contractor_id, other_project_id = create_context(
        auth_client, "Second"
    )
    work_log_id = create_work_log(
        auth_client, organization_id, contractor_id, project_id
    )
    other_work_log_id = create_work_log(
        auth_client, other_organization_id, other_contractor_id, other_project_id
    )
    decide_work_log(auth_client, organization_id, work_log_id, "approved")
    decide_work_log(auth_client, other_organization_id, other_work_log_id, "approved")

    first_org_approvals = auth_client.get(
        f"/organizations/{organization_id}/approvals"
    ).json()

    assert first_org_approvals["total"] == 1
    assert first_org_approvals["items"][0]["work_log_id"] == work_log_id


def test_list_approvals_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/organizations/{uuid4()}/approvals")

    assert response.status_code == 401


def test_list_approvals_rejects_invalid_pagination(auth_client: TestClient) -> None:
    organization_id, _, _ = create_context(auth_client)

    assert (
        auth_client.get(
            f"/organizations/{organization_id}/approvals?limit=101"
        ).status_code
        == 422
    )
