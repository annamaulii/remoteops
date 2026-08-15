from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from remoteops.database import get_session
from remoteops.models import Approval, Contractor, LeaveRequest, Project, User, WorkLog
from remoteops.organizations import get_membership, require_role
from remoteops.resources import get_resource
from remoteops.users import get_current_user

router = APIRouter(prefix="/organizations", tags=["workflows"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class WorkLogCreate(BaseModel):
    contractor_id: UUID
    project_id: UUID
    work_date: date
    minutes: Annotated[int, Field(ge=1, le=1440)]
    description: Annotated[str, Field(max_length=2000)] = ""


class WorkLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    contractor_id: UUID
    project_id: UUID
    work_date: date
    minutes: int
    description: str
    created_at: datetime


class LeaveCreate(BaseModel):
    contractor_id: UUID
    start_date: date
    end_date: date
    reason: Annotated[str, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def validate_dates(self) -> "LeaveCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LeaveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    contractor_id: UUID
    start_date: date
    end_date: date
    reason: str
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime


class DecisionCreate(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Annotated[str, Field(max_length=2000)] = ""


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leave_request_id: UUID
    reviewer_user_id: UUID
    decision: Literal["approved", "rejected"]
    note: str
    created_at: datetime


def get_leave(
    organization_id: UUID, leave_id: UUID, session: Session
) -> LeaveRequest:
    leave = session.scalar(
        select(LeaveRequest).where(
            LeaveRequest.id == leave_id,
            LeaveRequest.organization_id == organization_id,
        )
    )
    if leave is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return leave


@router.post(
    "/{organization_id}/work-logs",
    response_model=WorkLogRead,
    status_code=status.HTTP_201_CREATED,
)
def create_work_log(
    organization_id: UUID,
    data: WorkLogCreate,
    session: SessionDependency,
    user: CurrentUser,
) -> WorkLog:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    get_resource(Contractor, organization_id, data.contractor_id, session, "Contractor")
    get_resource(Project, organization_id, data.project_id, session, "Project")
    work_log = WorkLog(organization_id=organization_id, **data.model_dump())
    session.add(work_log)
    session.commit()
    session.refresh(work_log)
    return work_log


@router.get("/{organization_id}/work-logs", response_model=list[WorkLogRead])
def list_work_logs(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkLog]:
    get_membership(organization_id, user.id, session)
    return list(
        session.scalars(
            select(WorkLog)
            .where(WorkLog.organization_id == organization_id)
            .order_by(WorkLog.work_date.desc(), WorkLog.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )


@router.post(
    "/{organization_id}/leave-requests",
    response_model=LeaveRead,
    status_code=status.HTTP_201_CREATED,
)
def create_leave_request(
    organization_id: UUID,
    data: LeaveCreate,
    session: SessionDependency,
    user: CurrentUser,
) -> LeaveRequest:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    get_resource(Contractor, organization_id, data.contractor_id, session, "Contractor")
    leave = LeaveRequest(organization_id=organization_id, **data.model_dump())
    session.add(leave)
    session.commit()
    session.refresh(leave)
    return leave


@router.get(
    "/{organization_id}/leave-requests", response_model=list[LeaveRead]
)
def list_leave_requests(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
) -> list[LeaveRequest]:
    get_membership(organization_id, user.id, session)
    return list(
        session.scalars(
            select(LeaveRequest)
            .where(LeaveRequest.organization_id == organization_id)
            .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id)
        ).all()
    )


@router.post(
    "/{organization_id}/leave-requests/{leave_id}/decision",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
def decide_leave_request(
    organization_id: UUID,
    leave_id: UUID,
    data: DecisionCreate,
    session: SessionDependency,
    user: CurrentUser,
) -> Approval:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    leave = get_leave(organization_id, leave_id, session)
    if leave.status != "pending":
        raise HTTPException(status_code=409, detail="Leave request already decided")
    leave.status = data.decision
    approval = Approval(
        leave_request_id=leave.id,
        reviewer_user_id=user.id,
        decision=data.decision,
        note=data.note,
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return approval
