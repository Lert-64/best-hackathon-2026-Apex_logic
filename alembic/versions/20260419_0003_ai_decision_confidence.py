from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260419_0003"
down_revision: Union[str, Sequence[str], None] = "20260419_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("anomalies", sa.Column("ai_decision_confidence", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("anomalies", "ai_decision_confidence")

