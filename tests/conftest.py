import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://remoteops:remoteops@localhost:5432/remoteops",
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-at-least-32-characters")
os.environ.setdefault(
    "WEBHOOK_SIGNING_SECRET", "test-webhook-secret-at-least-32-characters"
)
os.environ.setdefault("WEBHOOK_ALLOWED_HOSTS", "webhooks.example.com")

from remoteops.database import engine, get_session
from remoteops.main import app
from remoteops.models import (
    Approval,
    AuditEvent,
    AuthToken,
    Contractor,
    Document,
    IdempotencyRecord,
    LeaveRequest,
    Organization,
    OrganizationMembership,
    Project,
    Team,
    User,
    WebhookAttempt,
    WebhookDelivery,
    WebhookSubscription,
    WorkLog,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            session.execute(delete(AuditEvent))
            session.execute(delete(WebhookAttempt))
            session.execute(delete(WebhookDelivery))
            session.execute(delete(WebhookSubscription))
            session.execute(delete(Document))
            session.execute(delete(Approval))
            session.execute(delete(WorkLog))
            session.execute(delete(LeaveRequest))
            session.execute(delete(Contractor))
            session.execute(delete(Project))
            session.execute(delete(Team))
            session.execute(delete(OrganizationMembership))
            session.execute(delete(IdempotencyRecord))
            session.execute(delete(AuthToken))
            session.execute(delete(User))
            session.execute(delete(Organization))
            session.flush()
            yield session
        transaction.rollback()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    credentials = {"email": "owner@example.com", "password": "strong-password"}
    client.post("/users/register", json=credentials)
    login = client.post(
        "/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return client
