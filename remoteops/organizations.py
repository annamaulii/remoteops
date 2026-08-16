import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.database import get_session
from remoteops.models import (
    IdempotencyRecord,
    Organization,
    OrganizationMembership,
    User,
)
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["organizations"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
MemberRole = Literal["admin", "member"]
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")


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
    data: OrganizationCreate,
    session: SessionDependency,
    user: CurrentUser,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Organization | JSONResponse:
    if idempotency_key is not None and not IDEMPOTENCY_KEY_PATTERN.fullmatch(
        idempotency_key
    ):
        raise HTTPException(status_code=422, detail="Invalid Idempotency-Key")

    request_fingerprint = hashlib.sha256(
        json.dumps(
            data.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if idempotency_key is not None:
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        record_id = session.scalar(
            insert(IdempotencyRecord)
            .values(
                user_id=user.id,
                method="POST",
                path="/organizations",
                key_hash=key_hash,
                request_fingerprint=request_fingerprint,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "method", "path", "key_hash"]
            )
            .returning(IdempotencyRecord.id)
        )
        if record_id is None:
            record = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user.id,
                    IdempotencyRecord.method == "POST",
                    IdempotencyRecord.path == "/organizations",
                    IdempotencyRecord.key_hash == key_hash,
                )
            )
            if record is None or record.request_fingerprint != request_fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used with a different request",
                )
            status_code = record.status_code or status.HTTP_201_CREATED
            response_body = record.response_body
            return JSONResponse(
                status_code=status_code,
                content=response_body,
                headers={"X-Idempotent-Replayed": "true"},
            )

    organization = Organization(name=data.name)
    session.add(organization)
    try:
        session.flush()
        session.add(
            OrganizationMembership(
                organization_id=organization.id, user_id=user.id, role="owner"
            )
        )
        session.flush()
        if idempotency_key is not None:
            response_body = OrganizationRead.model_validate(organization).model_dump(
                mode="json"
            )
            session.execute(
                update(IdempotencyRecord)
                .where(IdempotencyRecord.id == record_id)
                .values(
                    status_code=status.HTTP_201_CREATED,
                    response_body=response_body,
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
    total = (
        session.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(membership_filter)
        )
        or 0
    )
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
    target = session.scalar(select(User).where(User.email == str(data.email).lower()))
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
        role=data.role,
        created_at=membership.created_at,
    )


@router.patch("/{organization_id}/members/{user_id}", response_model=MemberRead)
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
