from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from remoteops.models import User
from remoteops.users import password_hash


def test_registers_user_with_normalized_email_and_hashed_password(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/users/register",
        json={"email": "ANNA@example.com", "password": "strong-password"},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "anna@example.com"
    assert "password" not in response.json()
    user = db_session.scalar(select(User).where(User.email == "anna@example.com"))
    assert user is not None
    assert user.password_hash != "strong-password"
    assert password_hash.verify("strong-password", user.password_hash)


def test_rejects_duplicate_email_and_invalid_password(client: TestClient) -> None:
    data = {"email": "anna@example.com", "password": "strong-password"}
    assert client.post("/users/register", json=data).status_code == 201

    assert client.post("/users/register", json=data).status_code == 409
    assert client.post(
        "/users/register",
        json={"email": "valid@example.com", "password": "short"},
    ).status_code == 422


def test_logs_in_and_reads_current_user(client: TestClient) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "strong-password"},
    )

    login = client.post(
        "/auth/login",
        data={"username": "ANNA@example.com", "password": "strong-password"},
    )
    token = login.json()["access_token"]
    response = client.get(
        "/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert response.status_code == 200
    assert response.json()["email"] == "anna@example.com"


def test_rejects_invalid_login_and_token(client: TestClient) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "strong-password"},
    )

    login = client.post(
        "/auth/login",
        data={"username": "anna@example.com", "password": "wrong-password"},
    )
    current_user = client.get(
        "/users/me", headers={"Authorization": "Bearer invalid-token"}
    )

    assert login.status_code == 401
    assert current_user.status_code == 401
