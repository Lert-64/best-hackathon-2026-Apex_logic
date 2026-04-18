from typing import Sequence, Union

from alembic import op


revision: str = "20260419_0002"
down_revision: Union[str, Sequence[str], None] = "20260418_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE anomalystatus ADD VALUE IF NOT EXISTS 'PENDING_ADMIN';")


def downgrade() -> None:
    pass

