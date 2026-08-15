from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.database import get_session
from remoteops.models import Organization, OrganizationMembership, User
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["organizations"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
MemberRole = Literal["admin", "member"]


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=255)]


class OrganizationUpdate(OrganizationCreate):
    pass


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


class MemberCreate(BaseModel):
    email: EmailStr
    role: MemberRole = "member"


class MemberUpdate(BaseModel):
    role: MemberRole


class MemberRead(BaseModel):
    user_id: UUID
    email: EmailStr
    role: Literal["owner", "admin", "member"]
    created_at: datetime


def get_membership(
    organization_id: UUID, user_id: UUID, session: Session
) -> OrganizationMembership:
    membership = session.get(OrganizationMembership, (organization_id, user_id))
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return membership


def require_role(
    organization_id: UUID,
    user_id: UUID,
    session: Session,
    allowed_roles: set[str],
) -> OrganizationMembership:
    membership = get_membership(organization_id, user_id, session)
    if membership.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return membership


@router.post(
    "",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Organization name already exists"}},
)
def create_organization(
    data: OrganizationCreate, session: SessionDependency, user: CurrentUser
) -> Organization:
    organization = Organization(name=data.name)
    session.add(organization)
    try:
        session.flush()
        session.add(
            OrganizationMembership(
                organization_id=organization.id, user_id=user.id, role="owner"
            )
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Organization name already exists"
        ) from None
    session.refresh(organization)
    return organization


@router.get("", response_model=OrganizationList)
def list_organizations(
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrganizationList:
    membership_filter = OrganizationMembership.user_id == user.id
    organizations = session.scalars(
        select(Organization)
        .join(OrganizationMembership)
        .where(membership_filter)
        .order_by(Organization.name, Organization.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(
        select(func.count())
        .select_from(OrganizationMembership)
        .where(membership_filter)
    ) or 0
    return OrganizationList(
        items=[OrganizationRead.model_validate(item) for item in organizations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: UUID, session: SessionDependency, user: CurrentUser
) -> Organization:
    get_membership(organization_id, user.id, session)
    return session.get_one(Organization, organization_id)


@router.patch("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: UUID,
    data: OrganizationUpdate,
    session: SessionDependency,
    user: CurrentUser,
) -> Organization:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    organization = session.get_one(Organization, organization_id)
    organization.name = data.name
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Organization name already exists"
        ) from None
    session.refresh(organization)
    return organization


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: UUID, session: SessionDependency, user: CurrentUser
) -> None:
    require_role(organization_id, user.id, session, {"owner"})
    session.delete(session.get_one(Organization, organization_id))
    session.commit()


@router.get("/{organization_id}/members", response_model=list[MemberRead])
def list_members(
    organization_id: UUID, session: SessionDependency, user: CurrentUser
) -> list[MemberRead]:
    get_membership(organization_id, user.id, session)
    rows = session.execute(
        select(OrganizationMembership, User.email)
        .join(User)
        .where(OrganizationMembership.organization_id == organization_id)
        .order_by(User.email)
    ).all()
    return [
        MemberRead(
            user_id=membership.user_id,
            email=email,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, email in rows
    ]


@router.post(
    "/{organization_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    organization_id: UUID,
    data: MemberCreate,
    session: SessionDependency,
    user: CurrentUser,
) -> MemberRead:
    actor = require_role(organization_id, user.id, session, {"owner", "admin"})
    if actor.role == "admin" and data.role != "member":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    target = session.scalar(
        select(User).where(User.email == str(data.email).lower())
    )
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    membership = OrganizationMembership(
        organization_id=organization_id, user_id=target.id, role=data.role
    )
    session.add(membership)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="User is already a member"
        ) from None
    session.refresh(membership)
    return MemberRead(
        user_id=target.id,
        email=target.email,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.patch(
    "/{organization_id}/members/{user_id}", response_model=MemberRead
)
def update_member(
    organization_id: UUID,
    user_id: UUID,
    data: MemberUpdate,
    session: SessionDependency,
    user: CurrentUser,
) -> MemberRead:
    require_role(organization_id, user.id, session, {"owner"})
    membership = get_membership(organization_id, user_id, session)
    if membership.role == "owner":
        raise HTTPException(status_code=403, detail="Owner role cannot be changed")
    membership.role = data.role
    session.commit()
    session.refresh(membership)
    target = session.get_one(User, user_id)
    return MemberRead(
        user_id=target.id,
        email=target.email,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.delete(
    "/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    organization_id: UUID,
    user_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> None:
    actor = require_role(organization_id, user.id, session, {"owner", "admin"})
    membership = get_membership(organization_id, user_id, session)
    if membership.role == "owner" or (
        actor.role == "admin" and membership.role == "admin"
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    session.delete(membership)
    session.commit()
