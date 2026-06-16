"""initial claims schema

Revision ID: 0001_initial_claims_schema
Revises:
Create Date: 2026-06-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial_claims_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_name", sa.String(length=100), nullable=False),
        sa.Column("hospital_name", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("claim_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'Pending'")),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("validation_message", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_claims_id"), "claims", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_claims_id"), table_name="claims")
    op.drop_table("claims")