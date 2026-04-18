"""Add volunteer task-pool workflow fields and enum values

Revision ID: 20260418_0001
Revises: 20260418_0000
Create Date: 2026-04-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260418_0001"
down_revision: Union[str, Sequence[str], None] = "20260418_0000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'VOLUNTEER';")
    op.execute("ALTER TYPE anomalystatus ADD VALUE IF NOT EXISTS 'PENDING_INSPECTOR';")

    op.add_column(
        "anomalies",
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "anomalies",
        sa.Column("volunteer_photo_path", sa.String(), nullable=True),
    )
    op.add_column(
        "anomalies",
        sa.Column("volunteer_comment", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_anomalies_volunteer_id_users",
        "anomalies",
        "users",
        ["volunteer_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_anomalies_volunteer_id_users", "anomalies", type_="foreignkey")
    op.drop_column("anomalies", "volunteer_comment")
    op.drop_column("anomalies", "volunteer_photo_path")
    op.drop_column("anomalies", "volunteer_id")

    # PostgreSQL enums are not dropped here to avoid data-loss and type rewrite risks.

