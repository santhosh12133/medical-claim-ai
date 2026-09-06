"""add claim ownership

Revision ID: 0004_claim_ownership
Revises: 0003_phase2_rag_policy_verification
Create Date: 2026-09-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_claim_ownership"
down_revision = "0003_phase2_rag_policy_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_claims_user_id_users",
        "claims",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_claims_user_id"), "claims", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_claims_user_id"), table_name="claims")
    op.drop_constraint("fk_claims_user_id_users", "claims", type_="foreignkey")
    op.drop_column("claims", "user_id")
