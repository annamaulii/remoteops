from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from remoteops.audit import record_audit
from remoteops.database import get_session
from remoteops.models import Approval, Contractor, LeaveRequest, Project, User, WorkLog
from remoteops.organizations import get_membership, require_role
from remoteops.resources import get_resource
from remoteops.users import get_current_user
from remoteops.webhooks import enqueue_event

router = APIRouter(prefix="/organizations", tags=["workflows"])
SessionDependency = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class WorkLogCreate(BaseModel):
    contractor_id: UUID
    project_id: UUID
    work_date: date
    minutes: Annotated[int, Field(ge=1, le=1440, examples=[480])]
    description: Annotated[str, Field(max_length=2000, examples=["Backend work"])] = ""


class WorkLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    contractor_id: UUID
    project_id: UUID
    work_date: date
    minutes: int
    description: str
    status: Literal["submitted", "approved", "rejected"]
    created_at: datetime


class WorkLogPage(BaseModel):
    items: list[WorkLogRead]
    total: int
    limit: int
    offset: int


class LeaveCreate(BaseModel):
    contractor_id: UUID
    start_date: date
    end_date: date
    reason: Annotated[str, Field(max_length=2000, examples=["Family holiday"])] = ""

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


class LeavePage(BaseModel):
    items: list[LeaveRead]
    total: int
    limit: int
    offset: int


class DecisionCreate(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Annotated[str, Field(max_length=2000, examples=["Looks good"])] = ""


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leave_request_id: UUID | None
    work_log_id: UUID | None
    reviewer_user_id: UUID
    decision: Literal["approved", "rejected"]
    note: str
    created_at: datetime


class ApprovalPage(BaseModel):
    items: list[ApprovalRead]
    total: int
    limit: int
    offset: int


def get_leave(organization_id: UUID, leave_id: UUID, session: Session) -> LeaveRequest:
    leave = session.scalar(
        select(LeaveRequest).where(
            LeaveRequest.id == leave_id,
            LeaveRequest.organization_id == organization_id,
        )
    )
    if leave is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return leave


def get_work_log(organization_id: UUID, work_log_id: UUID, session: Session) -> WorkLog:
    work_log = session.scalar(
        select(WorkLog).where(
            WorkLog.id == work_log_id,
            WorkLog.organization_id == organization_id,
        )
    )
    if work_log is None:
        raise HTTPException(status_code=404, detail="Work log not found")
    return work_log


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


@router.get("/{organization_id}/work-logs", response_model=WorkLogPage)
def list_work_logs(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    work_log_status: Annotated[
        Literal["submitted", "approved", "rejected"] | None,
        Query(alias="status"),
    ] = None,
    contractor_id: UUID | None = None,
    project_id: UUID | None = None,
    work_date_from: date | None = None,
    work_date_to: date | None = None,
) -> WorkLogPage:
    get_membership(organization_id, user.id, session)
    if (
        work_date_from is not None
        and work_date_to is not None
        and work_date_from > work_date_to
    ):
        raise HTTPException(
            status_code=422, detail="work_date_from must be on or before work_date_to"
        )

    conditions = [WorkLog.organization_id == organization_id]
    if work_log_status is not None:
        conditions.append(WorkLog.status == work_log_status)
    if contractor_id is not None:
        conditions.append(WorkLog.contractor_id == contractor_id)
    if project_id is not None:
        conditions.append(WorkLog.project_id == project_id)
    if work_date_from is not None:
        conditions.append(WorkLog.work_date >= work_date_from)
    if work_date_to is not None:
        conditions.append(WorkLog.work_date <= work_date_to)

    items = session.scalars(
        select(WorkLog)
        .where(*conditions)
        .order_by(WorkLog.work_date.desc(), WorkLog.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        session.scalar(select(func.count()).select_from(WorkLog).where(*conditions))
        or 0
    )
    return WorkLogPage(
        items=[WorkLogRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{organization_id}/work-logs/{work_log_id}/decision",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
def decide_work_log(
    organization_id: UUID,
    work_log_id: UUID,
    data: DecisionCreate,
    session: SessionDependency,
    user: CurrentUser,
) -> Approval:
    require_role(organization_id, user.id, session, {"owner", "admin"})
    work_log = get_work_log(organization_id, work_log_id, session)
    if work_log.status != "submitted":
        raise HTTPException(status_code=409, detail="Work log already decided")
    work_log.status = data.decision
    approval = Approval(
        organization_id=organization_id,
        work_log_id=work_log.id,
        reviewer_user_id=user.id,
        decision=data.decision,
        note=data.note,
    )
    session.add(approval)
    record_audit(
        session,
        organization_id,
        user.id,
        data.decision,
        "work_log",
        work_log.id,
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Work log already decided"
        ) from None
    session.refresh(approval)
    return approval


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


@router.get("/{organization_id}/leave-requests", response_model=LeavePage)
def list_leave_requests(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeavePage:
    get_membership(organization_id, user.id, session)
    condition = LeaveRequest.organization_id == organization_id
    items = session.scalars(
        select(LeaveRequest)
        .where(condition)
        .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        session.scalar(select(func.count()).select_from(LeaveRequest).where(condition))
        or 0
    )
    return LeavePage(
        items=[LeaveRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
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
        organization_id=organization_id,
        leave_request_id=leave.id,
        reviewer_user_id=user.id,
        decision=data.decision,
        note=data.note,
    )
    session.add(approval)
    record_audit(
        session,
        organization_id,
        user.id,
        data.decision,
        "leave_request",
        leave.id,
    )
    enqueue_event(
        session,
        organization_id,
        "leave_request.decided",
        {
            "leave_request_id": str(leave.id),
            "decision": data.decision,
        },
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Leave request already decided"
        ) from None
    session.refresh(approval)
    return approval


@router.get("/{organization_id}/approvals", response_model=ApprovalPage)
def list_approvals(
    organization_id: UUID,
    session: SessionDependency,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    target_type: Annotated[Literal["work_log", "leave_request"] | None, Query()] = None,
    decision: Annotated[Literal["approved", "rejected"] | None, Query()] = None,
) -> ApprovalPage:
    get_membership(organization_id, user.id, session)
    conditions = [Approval.organization_id == organization_id]
    if target_type == "work_log":
        conditions.append(Approval.work_log_id.is_not(None))
    elif target_type == "leave_request":
        conditions.append(Approval.leave_request_id.is_not(None))
    if decision is not None:
        conditions.append(Approval.decision == decision)

    items = session.scalars(
        select(Approval)
        .where(*conditions)
        .order_by(Approval.created_at.desc(), Approval.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = (
        session.scalar(select(func.count()).select_from(Approval).where(*conditions))
        or 0
    )
    return ApprovalPage(
        items=[ApprovalRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
