"""Initial schema

Revision ID: 20260418_0000
Revises:
Create Date: 2026-04-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260418_0000"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    userrole_enum = postgresql.ENUM("ADMIN", "INSPECTOR", name="userrole")
    anomalyzone_enum = postgresql.ENUM("RED", "GREEN", name="anomalyzone")
    anomalystatus_enum = postgresql.ENUM("NEW", "IN_WORK", "RESOLVED", "DISMISSED", name="anomalystatus")

    bind = op.get_bind()
    userrole_enum.create(bind, checkfirst=True)
    anomalyzone_enum.create(bind, checkfirst=True)
    anomalystatus_enum.create(bind, checkfirst=True)

    op.create_table(
        "land_records",
        sa.Column("lid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cadastral_number", sa.String(), nullable=False),
        sa.Column("koatuu", sa.String(), nullable=False),
        sa.Column("ownership_type", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("agri_type", sa.String(), nullable=True),
        sa.Column("area_ha", sa.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("valuation", sa.DECIMAL(precision=15, scale=4), nullable=False),
        sa.Column("tax_id", sa.String(), nullable=True),
        sa.Column("owner_name", sa.String(), nullable=False),
        sa.Column("ownership_share", sa.String(), nullable=False),
        sa.Column("reg_date", sa.Date(), nullable=False),
        sa.Column("record_number", sa.String(), nullable=False),
        sa.Column("reg_authority", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("doc_subtype", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("lid"),
        sa.UniqueConstraint("cadastral_number"),
    )
    op.create_index(op.f("ix_land_records_cadastral_number"), "land_records", ["cadastral_number"], unique=True)
    op.create_index(op.f("ix_land_records_tax_id"), "land_records", ["tax_id"], unique=False)

    op.create_table(
        "real_estate_records",
        sa.Column("lid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tax_id", sa.String(), nullable=False),
        sa.Column("owner_name", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("cadastral_number", sa.String(), nullable=True),
        sa.Column("reg_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("total_area_sqm", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("joint_ownership_type", sa.String(), nullable=True),
        sa.Column("ownership_share", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("lid"),
    )
    op.create_index(op.f("ix_real_estate_records_cadastral_number"), "real_estate_records", ["cadastral_number"], unique=False)
    op.create_index(op.f("ix_real_estate_records_tax_id"), "real_estate_records", ["tax_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", postgresql.ENUM("ADMIN", "INSPECTOR", name="userrole", create_type=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "anomalies",
        sa.Column("lid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone", postgresql.ENUM("RED", "GREEN", name="anomalyzone", create_type=False), nullable=False),
        sa.Column("tax_id", sa.String(), nullable=True),
        sa.Column("land_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("real_estate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=False),
        sa.Column("potential_loss_uah", sa.DECIMAL(precision=15, scale=2), nullable=False),
        sa.Column("status", postgresql.ENUM("NEW", "IN_WORK", "RESOLVED", "DISMISSED", name="anomalystatus", create_type=False), nullable=False),
        sa.Column("inspector_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inspector_instruction", sa.Text(), nullable=True),
        sa.Column("inspector_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["inspector_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["land_id"], ["land_records.lid"]),
        sa.ForeignKeyConstraint(["real_estate_id"], ["real_estate_records.lid"]),
        sa.PrimaryKeyConstraint("lid"),
    )
    op.create_index(op.f("ix_anomalies_tax_id"), "anomalies", ["tax_id"], unique=False)
    op.create_index(op.f("ix_anomalies_zone"), "anomalies", ["zone"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("lid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anomaly_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomalies.lid"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("lid"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_anomalies_zone"), table_name="anomalies")
    op.drop_index(op.f("ix_anomalies_tax_id"), table_name="anomalies")
    op.drop_table("anomalies")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_real_estate_records_tax_id"), table_name="real_estate_records")
    op.drop_index(op.f("ix_real_estate_records_cadastral_number"), table_name="real_estate_records")
    op.drop_table("real_estate_records")
    op.drop_index(op.f("ix_land_records_tax_id"), table_name="land_records")
    op.drop_index(op.f("ix_land_records_cadastral_number"), table_name="land_records")
    op.drop_table("land_records")

    bind = op.get_bind()
    postgresql.ENUM(name="anomalystatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="anomalyzone").drop(bind, checkfirst=True)
    postgresql.ENUM(name="userrole").drop(bind, checkfirst=True)

