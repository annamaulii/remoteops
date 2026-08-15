"""create workflow tables

Revision ID: edb843e8f953
Revises: 5fdc4fff3f6c
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "edb843e8f953"
down_revision: Union[str, Sequence[str], None] = "5fdc4fff3f6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def timestamp_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def organization_foreign_key() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"], ["organizations.id"], ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contractor_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        timestamp_column(),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="valid_leave_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="valid_leave_dates"),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractors.id"], ondelete="CASCADE"
        ),
        organization_foreign_key(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "work_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contractor_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        timestamp_column(),
        sa.CheckConstraint("minutes > 0", name="positive_work_minutes"),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractors.id"], ondelete="CASCADE"
        ),
        organization_foreign_key(),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("leave_request_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        timestamp_column(),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="valid_approval_decision",
        ),
        sa.ForeignKeyConstraint(
            ["leave_request_id"], ["leave_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("leave_request_id"),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("work_logs")
    op.drop_table("leave_requests")
