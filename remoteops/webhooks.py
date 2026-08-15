import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.config import settings
from remoteops.database import get_session
from remoteops.models import (
    User,
    WebhookAttempt,
    WebhookDelivery,
    WebhookSubscription,
)
from remoteops.organizations import require_role
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["webhooks"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
WebhookEvent = Literal["leave_request.decided"]
Sender = Callable[[str, bytes, dict[str, str]], int]
MAX_ATTEMPTS = 5


def allowed_hosts() -> set[str]:
    return {
        host.strip().lower()
        for host in settings.webhook_allowed_hosts.split(",")
        if host.strip()
    }


def webhook_secret() -> str:
    if settings.webhook_signing_secret is None:
        raise HTTPException(status_code=503, detail="Webhooks are not configured")
    return settings.webhook_signing_secret.get_secret_value()


def validate_webhook_url(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Webhook URL has an invalid port") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in allowed_hosts()
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise ValueError("Webhook URL must use HTTPS on an allowed host")
    return value


def signing_secret(subscription_id: UUID) -> str:
    return hmac.new(
        webhook_secret().encode(),
        str(subscription_id).encode(),
        hashlib.sha256,
    ).hexdigest()


class SubscriptionCreate(BaseModel):
    url: Annotated[str, Field(max_length=2048)]
    event: WebhookEvent

    @field_validator("url")
    @classmethod
    def url_is_safe(cls, value: str) -> str:
        return validate_webhook_url(value)


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    url: str
    event: WebhookEvent
    created_at: datetime


class SubscriptionCreated(SubscriptionRead):
    signing_secret: str


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_number: int
    status_code: int | None
    error_code: str | None
    attempted_at: datetime


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    event: str
    status: str
    attempt_count: int
    next_attempt_at: datetime
    created_at: datetime
    attempts: list[AttemptRead]


@router.post(
    "/{organization_id}/webhooks",
    response_model=SubscriptionCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    organization_id: UUID,
    data: SubscriptionCreate,
    session: SessionDependency,
    user: CurrentUser,
) -> SubscriptionCreated:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    webhook_secret()
    subscription = WebhookSubscription(
        organization_id=organization_id, **data.model_dump()
    )
    session.add(subscription)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Webhook already exists") from None
    session.refresh(subscription)
    return SubscriptionCreated(
        **SubscriptionRead.model_validate(subscription).model_dump(),
        signing_secret=signing_secret(subscription.id),
    )


@router.get(
    "/{organization_id}/webhooks", response_model=list[SubscriptionRead]
)
def list_subscriptions(
    organization_id: UUID, session: SessionDependency, user: CurrentUser
) -> list[WebhookSubscription]:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    return list(
        session.scalars(
            select(WebhookSubscription)
            .where(WebhookSubscription.organization_id == organization_id)
            .order_by(WebhookSubscription.created_at, WebhookSubscription.id)
        )
    )


@router.delete(
    "/{organization_id}/webhooks/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subscription(
    organization_id: UUID,
    subscription_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> None:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    subscription = session.scalar(
        select(WebhookSubscription).where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.organization_id == organization_id,
        )
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    session.delete(subscription)
    session.commit()


@router.get(
    "/{organization_id}/webhook-deliveries", response_model=list[DeliveryRead]
)
def list_deliveries(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DeliveryRead]:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    deliveries = session.scalars(
        select(WebhookDelivery)
        .join(WebhookSubscription)
        .where(WebhookSubscription.organization_id == organization_id)
        .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        DeliveryRead(
            id=delivery.id,
            subscription_id=delivery.subscription_id,
            event=delivery.event,
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            next_attempt_at=delivery.next_attempt_at,
            created_at=delivery.created_at,
            attempts=list(
                session.scalars(
                    select(WebhookAttempt)
                    .where(WebhookAttempt.delivery_id == delivery.id)
                    .order_by(WebhookAttempt.attempt_number)
                )
            ),
        )
        for delivery in deliveries
    ]


def enqueue_event(
    session: Session, organization_id: UUID, event: WebhookEvent, data: dict
) -> None:
    payload = json.dumps(
        {"event": event, "data": data}, sort_keys=True, separators=(",", ":")
    )
    subscriptions = session.scalars(
        select(WebhookSubscription).where(
            WebhookSubscription.organization_id == organization_id,
            WebhookSubscription.event == event,
        )
    )
    session.add_all(
        WebhookDelivery(subscription_id=item.id, event=event, payload=payload)
        for item in subscriptions
    )


def http_sender(url: str, content: bytes, headers: dict[str, str]) -> int:
    with httpx.Client(follow_redirects=False, timeout=5.0) as client:
        return client.post(url, content=content, headers=headers).status_code


def process_due_deliveries(
    session: Session,
    sender: Sender = http_sender,
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> int:
    current_time = now or datetime.now(timezone.utc)
    deliveries = session.scalars(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status.in_(("pending", "retrying")),
            WebhookDelivery.next_attempt_at <= current_time,
        )
        .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    # ponytail: lock is held during a bounded HTTP call; use claim leases when throughput requires it.
    for delivery in deliveries:
        subscription = session.get_one(WebhookSubscription, delivery.subscription_id)
        attempt_number = delivery.attempt_count + 1
        timestamp = str(int(current_time.timestamp()))
        content = delivery.payload.encode()
        signature = hmac.new(
            signing_secret(subscription.id).encode(),
            timestamp.encode() + b"." + content,
            hashlib.sha256,
        ).hexdigest()
        response_status: int | None = None
        error_code: str | None = None
        try:
            response_status = sender(
                subscription.url,
                content,
                {
                    "Content-Type": "application/json",
                    "X-RemoteOps-Delivery": str(delivery.id),
                    "X-RemoteOps-Event": delivery.event,
                    "X-RemoteOps-Timestamp": timestamp,
                    "X-RemoteOps-Signature": f"sha256={signature}",
                },
            )
            succeeded = 200 <= response_status < 300
            if not succeeded:
                error_code = "http_error"
        except httpx.HTTPError:
            succeeded = False
            error_code = "network_error"

        session.add(
            WebhookAttempt(
                delivery_id=delivery.id,
                attempt_number=attempt_number,
                status_code=response_status,
                error_code=error_code,
            )
        )
        delivery.attempt_count = attempt_number
        if succeeded:
            delivery.status = "succeeded"
        elif attempt_number >= MAX_ATTEMPTS:
            delivery.status = "failed"
        else:
            delivery.status = "retrying"
            delivery.next_attempt_at = current_time + timedelta(
                seconds=min(2 ** (attempt_number - 1) * 60, 3600)
            )
    session.commit()
    return len(deliveries)
