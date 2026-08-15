from datetime import datetime
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.database import get_session
from remoteops.models import Contractor, Project, Team, User
from remoteops.organizations import get_membership, require_role
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["resources"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Resource = TypeVar("Resource", Team, Contractor, Project)


class NameInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=255)]


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    created_at: datetime


class TeamPage(BaseModel):
    items: list[TeamRead]
    total: int
    limit: int
    offset: int


class ContractorInput(NameInput):
    email: EmailStr


class ContractorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    email: EmailStr
    created_at: datetime


class ContractorPage(BaseModel):
    items: list[ContractorRead]
    total: int
    limit: int
    offset: int


class ProjectInput(NameInput):
    description: Annotated[str, Field(max_length=2000)] = ""


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    description: str
    created_at: datetime


class ProjectPage(BaseModel):
    items: list[ProjectRead]
    total: int
    limit: int
    offset: int


def get_resource(
    model: type[Resource],
    organization_id: UUID,
    resource_id: UUID,
    session: Session,
    label: str,
) -> Resource:
    resource = session.scalar(
        select(model).where(
            model.id == resource_id,
            model.organization_id == organization_id,
        )
    )
    if resource is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return resource


def list_resources(
    model: type[Resource],
    organization_id: UUID,
    session: Session,
    limit: int,
    offset: int,
) -> tuple[list[Resource], int]:
    condition = model.organization_id == organization_id
    items = list(
        session.scalars(
            select(model)
            .where(condition)
            .order_by(model.name, model.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = session.scalar(
        select(func.count()).select_from(model).where(condition)
    ) or 0
    return items, total


def commit_or_conflict(session: Session, detail: str) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=detail) from None


@router.post(
    "/{organization_id}/teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
)
def create_team(
    organization_id: UUID,
    data: NameInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Team:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    team = Team(organization_id=organization_id, name=data.name)
    session.add(team)
    commit_or_conflict(session, "Team name already exists")
    session.refresh(team)
    return team


@router.get("/{organization_id}/teams", response_model=TeamPage)
def list_teams(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TeamPage:
    get_membership(organization_id, user.id, session)
    items, total = list_resources(Team, organization_id, session, limit, offset)
    return TeamPage(
        items=[TeamRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{organization_id}/teams/{team_id}", response_model=TeamRead)
def get_team(
    organization_id: UUID,
    team_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> Team:
    get_membership(organization_id, user.id, session)
    return get_resource(Team, organization_id, team_id, session, "Team")


@router.patch("/{organization_id}/teams/{team_id}", response_model=TeamRead)
def update_team(
    organization_id: UUID,
    team_id: UUID,
    data: NameInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Team:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    team = get_resource(Team, organization_id, team_id, session, "Team")
    team.name = data.name
    commit_or_conflict(session, "Team name already exists")
    session.refresh(team)
    return team


@router.delete(
    "/{organization_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_team(
    organization_id: UUID,
    team_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> None:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    session.delete(get_resource(Team, organization_id, team_id, session, "Team"))
    session.commit()


@router.post(
    "/{organization_id}/contractors",
    response_model=ContractorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_contractor(
    organization_id: UUID,
    data: ContractorInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Contractor:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    contractor = Contractor(
        organization_id=organization_id,
        name=data.name,
        email=str(data.email).lower(),
    )
    session.add(contractor)
    commit_or_conflict(session, "Contractor email already exists")
    session.refresh(contractor)
    return contractor


@router.get("/{organization_id}/contractors", response_model=ContractorPage)
def list_contractors(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ContractorPage:
    get_membership(organization_id, user.id, session)
    items, total = list_resources(
        Contractor, organization_id, session, limit, offset
    )
    return ContractorPage(
        items=[ContractorRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{organization_id}/contractors/{contractor_id}",
    response_model=ContractorRead,
)
def get_contractor(
    organization_id: UUID,
    contractor_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> Contractor:
    get_membership(organization_id, user.id, session)
    return get_resource(
        Contractor, organization_id, contractor_id, session, "Contractor"
    )


@router.patch(
    "/{organization_id}/contractors/{contractor_id}",
    response_model=ContractorRead,
)
def update_contractor(
    organization_id: UUID,
    contractor_id: UUID,
    data: ContractorInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Contractor:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    contractor = get_resource(
        Contractor, organization_id, contractor_id, session, "Contractor"
    )
    contractor.name = data.name
    contractor.email = str(data.email).lower()
    commit_or_conflict(session, "Contractor email already exists")
    session.refresh(contractor)
    return contractor


@router.delete(
    "/{organization_id}/contractors/{contractor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contractor(
    organization_id: UUID,
    contractor_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> None:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    contractor = get_resource(
        Contractor, organization_id, contractor_id, session, "Contractor"
    )
    session.delete(contractor)
    session.commit()


@router.post(
    "/{organization_id}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    organization_id: UUID,
    data: ProjectInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Project:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    project = Project(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
    )
    session.add(project)
    commit_or_conflict(session, "Project name already exists")
    session.refresh(project)
    return project


@router.get("/{organization_id}/projects", response_model=ProjectPage)
def list_projects(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectPage:
    get_membership(organization_id, user.id, session)
    items, total = list_resources(Project, organization_id, session, limit, offset)
    return ProjectPage(
        items=[ProjectRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{organization_id}/projects/{project_id}", response_model=ProjectRead)
def get_project(
    organization_id: UUID,
    project_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> Project:
    get_membership(organization_id, user.id, session)
    return get_resource(Project, organization_id, project_id, session, "Project")


@router.patch(
    "/{organization_id}/projects/{project_id}", response_model=ProjectRead
)
def update_project(
    organization_id: UUID,
    project_id: UUID,
    data: ProjectInput,
    session: SessionDependency,
    user: CurrentUser,
) -> Project:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    project = get_resource(
        Project, organization_id, project_id, session, "Project"
    )
    project.name = data.name
    project.description = data.description
    commit_or_conflict(session, "Project name already exists")
    session.refresh(project)
    return project


@router.delete(
    "/{organization_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project(
    organization_id: UUID,
    project_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> None:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    session.delete(
        get_resource(Project, organization_id, project_id, session, "Project")
    )
    session.commit()
