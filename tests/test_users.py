from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from remoteops.database import SessionFactory
from remoteops.models import AuthToken, User
from remoteops.users import (
    RefreshTokenRequest,
    create_password_reset_token,
    create_refresh_token,
    get_valid_auth_token,
    hash_auth_token,
    password_hash,
    refresh_access_token,
)


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
    assert (
        client.post(
            "/users/register",
            json={"email": "valid@example.com", "password": "short"},
        ).status_code
        == 422
    )


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
    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert login.json()["refresh_token"]
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


def test_refresh_rotates_refresh_token(client: TestClient, db_session: Session) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "strong-password"},
    )
    login = client.post(
        "/auth/login",
        data={"username": "anna@example.com", "password": "strong-password"},
    )

    refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    reused = client.post(
        "/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )

    assert refresh.status_code == 200
    assert refresh.json()["access_token"]
    assert refresh.json()["refresh_token"] != login.json()["refresh_token"]
    assert reused.status_code == 401
    stored_token = db_session.scalar(
        select(AuthToken).where(AuthToken.purpose == "refresh")
    )
    assert stored_token is not None
    assert stored_token.token_hash == hash_auth_token(refresh.json()["refresh_token"])
    assert stored_token.token_hash != refresh.json()["refresh_token"]


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "strong-password"},
    )
    login = client.post(
        "/auth/login",
        data={"username": "anna@example.com", "password": "strong-password"},
    )

    logout = client.post(
        "/auth/logout",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )

    assert logout.status_code == 204
    assert refresh.status_code == 401


def test_password_reset_request_does_not_reveal_accounts(
    client: TestClient, db_session: Session
) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "old-password"},
    )

    existing = client.post(
        "/auth/password-reset/request", json={"email": "anna@example.com"}
    )
    missing = client.post(
        "/auth/password-reset/request", json={"email": "missing@example.com"}
    )

    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.json() == missing.json()
    assert (
        db_session.scalar(
            select(AuthToken).where(AuthToken.purpose == "password_reset")
        )
        is not None
    )


def test_confirms_password_reset_and_revokes_old_tokens(
    client: TestClient, db_session: Session
) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "old-password"},
    )
    user = db_session.scalar(select(User).where(User.email == "anna@example.com"))
    assert user is not None
    login = client.post(
        "/auth/login",
        data={"username": "anna@example.com", "password": "old-password"},
    )
    reset_token = create_password_reset_token(db_session, user)

    confirm = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "new_password": "new-password",
        },
    )
    old_login = client.post(
        "/auth/login",
        data={"username": "anna@example.com", "password": "old-password"},
    )
    old_refresh = client.post(
        "/auth/refresh",
        json={"refresh_token": login.json()["refresh_token"]},
    )

    assert confirm.status_code == 204
    assert old_login.status_code == 401
    assert old_refresh.status_code == 401
    assert db_session.scalar(select(AuthToken)) is None

    new_login = client.post(
        "/auth/login",
        data={"username": "anna@example.com", "password": "new-password"},
    )
    assert new_login.status_code == 200

    reused = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "another-password"},
    )
    assert reused.status_code == 400


def test_rejects_expired_password_reset_token(
    client: TestClient, db_session: Session
) -> None:
    client.post(
        "/users/register",
        json={"email": "anna@example.com", "password": "old-password"},
    )
    user = db_session.scalar(select(User).where(User.email == "anna@example.com"))
    assert user is not None
    reset_token = create_password_reset_token(db_session, user)
    stored_token = db_session.scalar(
        select(AuthToken).where(AuthToken.purpose == "password_reset")
    )
    assert stored_token is not None
    assert stored_token.token_hash == hash_auth_token(reset_token)
    assert stored_token.token_hash != reset_token
    stored_token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "new-password"},
    )

    assert response.status_code == 400
    assert db_session.get(AuthToken, stored_token.id) is None


def test_concurrent_refresh_allows_only_one_rotation() -> None:
    with SessionFactory() as setup:
        user = User(
            email="race@example.com",
            password_hash=password_hash.hash("strong-password"),
        )
        setup.add(user)
        setup.flush()
        raw_token = create_refresh_token(setup, user)
        user_id = user.id
        setup.commit()

    refresh_started = Event()

    def rotate() -> int:
        with SessionFactory() as session:
            refresh_started.set()
            try:
                refresh_access_token(
                    RefreshTokenRequest(refresh_token=raw_token), session
                )
                return 200
            except HTTPException as error:
                return error.status_code

    try:
        with SessionFactory() as locker:
            locked_token = get_valid_auth_token(locker, raw_token, "refresh")
            assert locked_token is not None

            with ThreadPoolExecutor(max_workers=1) as executor:
                competing_refresh = executor.submit(rotate)
                assert refresh_started.wait(timeout=1)
                with pytest.raises(FutureTimeoutError):
                    competing_refresh.result(timeout=0.2)

                user = locker.get(User, user_id)
                assert user is not None
                locker.delete(locked_token)
                create_refresh_token(locker, user)
                locker.commit()

                status = competing_refresh.result(timeout=2)

        with SessionFactory() as verify:
            remaining = verify.scalars(
                select(AuthToken).where(
                    AuthToken.user_id == user_id,
                    AuthToken.purpose == "refresh",
                )
            ).all()
        assert status == 401
        assert len(remaining) == 1
    finally:
        with SessionFactory() as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.commit()
