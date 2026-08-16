from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.audit import record_audit
from remoteops.database import get_session
from remoteops.models import Document, User
from remoteops.organizations import get_membership, require_role
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["documents"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class DocumentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]
    content_type: Annotated[str, Field(min_length=1, max_length=255)]
    size_bytes: Annotated[int, Field(ge=0)]


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


def get_document(
    organization_id: UUID, document_id: UUID, session: Session
) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def commit_document(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Document name already exists"
        ) from None


@router.post(
    "/{organization_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    organization_id: UUID,
    data: DocumentInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Document:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    document = Document(
        id=uuid4(),
        organization_id=organization_id,
        created_by_user_id=user.id,
        **data.model_dump(),
    )
    session.add(document)
    record_audit(session, organization_id, user.id, "created", "document", document.id)
    commit_document(session)
    session.refresh(document)
    return document


@router.get("/{organization_id}/documents", response_model=DocumentPage)
def list_documents(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    get_membership(organization_id, user.id, session)
    condition = Document.organization_id == organization_id
    documents = session.scalars(
        select(Document)
        .where(condition)
        .order_by(Document.name, Document.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        session.scalar(select(func.count()).select_from(Document).where(condition)) or 0
    )
    return DocumentPage(
        items=[DocumentRead.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{organization_id}/documents/{document_id}", response_model=DocumentRead)
def read_document(
    organization_id: UUID,
    document_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> Document:
    get_membership(organization_id, user.id, session)
    return get_document(organization_id, document_id, session)


@router.patch("/{organization_id}/documents/{document_id}", response_model=DocumentRead)
def update_document(
    organization_id: UUID,
    document_id: UUID,
    data: DocumentInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Document:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    document = get_document(organization_id, document_id, session)
    document.name = data.name
    document.content_type = data.content_type
    document.size_bytes = data.size_bytes
    record_audit(session, organization_id, user.id, "updated", "document", document.id)
    commit_document(session)
    session.refresh(document)
    return document


@router.delete(
    "/{organization_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    organization_id: UUID,
    document_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> None:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    document = get_document(organization_id, document_id, session)
    record_audit(session, organization_id, user.id, "deleted", "document", document.id)
    session.delete(document)
    session.commit()
