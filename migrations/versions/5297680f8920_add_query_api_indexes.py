"""add query api indexes

Revision ID: 5297680f8920
Revises: 084edd6ae044
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5297680f8920"
down_revision: Union[str, Sequence[str], None] = "084edd6ae044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_work_logs_org_date", "work_logs", ["organization_id", "work_date"]
    )

    op.add_column("approvals", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE approvals
        SET organization_id = COALESCE(
            (SELECT w.organization_id FROM work_logs w WHERE w.id = approvals.work_log_id),
            (SELECT l.organization_id FROM leave_requests l
             WHERE l.id = approvals.leave_request_id)
        )
        """
    )
    op.alter_column("approvals", "organization_id", nullable=False)
    op.create_foreign_key(
        "approvals_organization_id_fkey",
        "approvals",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_approvals_org_created", "approvals", ["organization_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_approvals_org_created", table_name="approvals")
    op.drop_constraint("approvals_organization_id_fkey", "approvals", type_="foreignkey")
    op.drop_column("approvals", "organization_id")

    op.drop_index("ix_work_logs_org_date", table_name="work_logs")
