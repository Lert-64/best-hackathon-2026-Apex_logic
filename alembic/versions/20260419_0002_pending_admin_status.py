"""Add pending admin anomaly status

Revision ID: 20260419_0002
Revises: 20260418_0001
Create Date: 2026-04-19 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260419_0002"
down_revision: Union[str, Sequence[str], None] = "20260418_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE anomalystatus ADD VALUE IF NOT EXISTS 'PENDING_ADMIN';")


def downgrade() -> None:
    # PostgreSQL enum values are not removed automatically to avoid rewrite risks.
    pass

