"""add work log approvals

Revision ID: 084edd6ae044
Revises: b91e510b92ae
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "084edd6ae044"
down_revision: Union[str, Sequence[str], None] = "b91e510b92ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "work_logs",
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="submitted"
        ),
    )
    op.alter_column("work_logs", "status", server_default=None)
    op.create_check_constraint(
        "valid_work_log_status",
        "work_logs",
        "status IN ('submitted', 'approved', 'rejected')",
    )

    op.alter_column("approvals", "leave_request_id", nullable=True)
    op.add_column("approvals", sa.Column("work_log_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "approvals_work_log_id_fkey",
        "approvals",
        "work_logs",
        ["work_log_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "approvals_work_log_id_key", "approvals", ["work_log_id"]
    )
    op.create_check_constraint(
        "approval_target_exclusive",
        "approvals",
        "(leave_request_id IS NOT NULL) <> (work_log_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("approval_target_exclusive", "approvals", type_="check")
    op.drop_constraint("approvals_work_log_id_key", "approvals", type_="unique")
    op.drop_constraint("approvals_work_log_id_fkey", "approvals", type_="foreignkey")
    op.drop_column("approvals", "work_log_id")
    op.alter_column("approvals", "leave_request_id", nullable=False)

    op.drop_constraint("valid_work_log_status", "work_logs", type_="check")
    op.drop_column("work_logs", "status")
