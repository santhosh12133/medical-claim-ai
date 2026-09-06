"""add policy lifecycle and integrity metadata

Revision ID: 0005_policy_lifecycle
Revises: 0004_claim_ownership
Create Date: 2026-09-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_policy_lifecycle"
down_revision = "0004_claim_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policy_documents", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("policy_documents", sa.Column("effective_to", sa.Date(), nullable=True))
    op.add_column("policy_documents", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_policy_documents_content_sha256"), "policy_documents", ["content_sha256"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_policy_documents_content_sha256"), table_name="policy_documents")
    op.drop_column("policy_documents", "content_sha256")
    op.drop_column("policy_documents", "effective_to")
    op.drop_column("policy_documents", "effective_from")
