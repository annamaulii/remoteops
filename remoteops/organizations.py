from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.database import get_session
from remoteops.models import Organization

router = APIRouter(prefix="/organizations", tags=["organizations"])
SessionDependency = Annotated[Session, Depends(get_session)]


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=255)]


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class OrganizationList(BaseModel):
    items: list[OrganizationRead]
    total: int
    limit: int
    offset: int


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Organization name already exists"}},
)
def create_organization(
    data: OrganizationCreate, session: SessionDependency
) -> Organization:
    organization = Organization(name=data.name)
    session.add(organization)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization name already exists",
        ) from None

    session.refresh(organization)
    return organization


@router.get("", response_model=OrganizationList)
def list_organizations(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrganizationList:
    organizations = session.scalars(
        select(Organization)
        .order_by(Organization.name, Organization.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(select(func.count()).select_from(Organization)) or 0
    return OrganizationList(
        items=[OrganizationRead.model_validate(item) for item in organizations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{organization_id}",
    response_model=OrganizationRead,
    responses={404: {"description": "Organization not found"}},
)
def get_organization(organization_id: UUID, session: SessionDependency) -> Organization:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return organization
