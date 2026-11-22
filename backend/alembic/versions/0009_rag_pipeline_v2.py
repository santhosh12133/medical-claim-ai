"""RAG pipeline v2: claim integrity, risk flags, review metadata and audit details

Revision ID: 0009_rag_pipeline_v2
Revises: 0008_async_claim_processing
Create Date: 2026-11-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_rag_pipeline_v2"
down_revision = "0008_async_claim_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("claims") as batch_op:
        batch_op.add_column(sa.Column("document_sha256", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("invoice_number", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("patient_name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("policy_category", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("risk_flags_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("final_approved_amount", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("reviewer_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_claims_reviewed_by_users", "users", ["reviewed_by"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_claims_document_sha256", ["document_sha256"], unique=False)
        batch_op.create_index("ix_claims_policy_category", ["policy_category"], unique=False)

    with op.batch_alter_table("claim_verification_audits") as batch_op:
        batch_op.add_column(sa.Column("extracted_rules_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("pipeline_version", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))

    # Backfill final amounts for claims that admins already approved.
    op.execute(
        "UPDATE claims SET final_approved_amount = COALESCE(policy_approved_amount, amount) "
        "WHERE status = 'Approved' AND final_approved_amount IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("claim_verification_audits") as batch_op:
        batch_op.drop_column("latency_ms")
        batch_op.drop_column("pipeline_version")
        batch_op.drop_column("extracted_rules_json")

    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_index("ix_claims_policy_category")
        batch_op.drop_index("ix_claims_document_sha256")
        batch_op.drop_constraint("fk_claims_reviewed_by_users", type_="foreignkey")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("reviewer_notes")
        batch_op.drop_column("final_approved_amount")
        batch_op.drop_column("risk_flags_json")
        batch_op.drop_column("policy_category")
        batch_op.drop_column("patient_name")
        batch_op.drop_column("invoice_number")
        batch_op.drop_column("document_sha256")
