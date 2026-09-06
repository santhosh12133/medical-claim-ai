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
    with op.batch_alter_table("claims") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_claims_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_claims_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_index("ix_claims_user_id")
        batch_op.drop_constraint("fk_claims_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
