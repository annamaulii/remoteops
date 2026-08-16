from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from remoteops.database import get_session
from remoteops.models import AuditEvent, User
from remoteops.organizations import require_role
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["audit"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID
    created_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int


def record_audit(
    session: Session,
    organization_id: UUID,
    actor_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
) -> None:
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


@router.get("/{organization_id}/audit-events", response_model=AuditEventPage)
def list_audit_events(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventPage:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    condition = AuditEvent.organization_id == organization_id
    events = session.scalars(
        select(AuditEvent)
        .where(condition)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        session.scalar(select(func.count()).select_from(AuditEvent).where(condition))
        or 0
    )
    return AuditEventPage(
        items=[AuditEventRead.model_validate(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )
