"""phase 2 rag policy verification

Revision ID: 0003_phase2_rag_policy_verification
Revises: 0002_users_auth_table
Create Date: 2026-06-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_phase2_rag_policy_verification"
down_revision = "0002_users_auth_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("treatment", sa.String(length=120), nullable=True))
    op.add_column("claims", sa.Column("policy_decision", sa.String(length=40), nullable=True))
    op.add_column("claims", sa.Column("policy_approved_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("claims", sa.Column("policy_confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column("claims", sa.Column("policy_source", sa.Text(), nullable=True))
    op.add_column("claims", sa.Column("policy_reason", sa.Text(), nullable=True))
    op.add_column("claims", sa.Column("policy_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_claims_treatment"), "claims", ["treatment"], unique=False)
    op.create_index(op.f("ix_claims_policy_decision"), "claims", ["policy_decision"], unique=False)

    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("policy_type", sa.String(length=100), nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_policy_documents_id"), "policy_documents", ["id"], unique=False)
    op.create_index(op.f("ix_policy_documents_title"), "policy_documents", ["title"], unique=False)
    op.create_index(op.f("ix_policy_documents_policy_type"), "policy_documents", ["policy_type"], unique=False)
    op.create_index(op.f("ix_policy_documents_department"), "policy_documents", ["department"], unique=False)
    op.create_index(op.f("ix_policy_documents_status"), "policy_documents", ["status"], unique=False)

    op.create_table(
        "policy_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "policy_document_id",
            sa.Integer(),
            sa.ForeignKey("policy_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("vector_id", sa.String(length=128), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_policy_chunks_id"), "policy_chunks", ["id"], unique=False)
    op.create_index(op.f("ix_policy_chunks_policy_document_id"), "policy_chunks", ["policy_document_id"], unique=False)
    op.create_index(op.f("ix_policy_chunks_vector_id"), "policy_chunks", ["vector_id"], unique=True)

    op.create_table(
        "claim_verification_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "policy_document_id",
            sa.Integer(),
            sa.ForeignKey("policy_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("claim_payload_json", sa.JSON(), nullable=False),
        sa.Column("retrieved_chunks_json", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("approved_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("policy_source", sa.String(length=255), nullable=False),
        sa.Column("policy_used", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_trace_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_claim_verification_audits_id"), "claim_verification_audits", ["id"], unique=False)
    op.create_index(op.f("ix_claim_verification_audits_claim_id"), "claim_verification_audits", ["claim_id"], unique=False)
    op.create_index(
        op.f("ix_claim_verification_audits_policy_document_id"),
        "claim_verification_audits",
        ["policy_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_claim_verification_audits_decision"),
        "claim_verification_audits",
        ["decision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_claim_verification_audits_decision"), table_name="claim_verification_audits")
    op.drop_index(op.f("ix_claim_verification_audits_policy_document_id"), table_name="claim_verification_audits")
    op.drop_index(op.f("ix_claim_verification_audits_claim_id"), table_name="claim_verification_audits")
    op.drop_index(op.f("ix_claim_verification_audits_id"), table_name="claim_verification_audits")
    op.drop_table("claim_verification_audits")

    op.drop_index(op.f("ix_policy_chunks_vector_id"), table_name="policy_chunks")
    op.drop_index(op.f("ix_policy_chunks_policy_document_id"), table_name="policy_chunks")
    op.drop_index(op.f("ix_policy_chunks_id"), table_name="policy_chunks")
    op.drop_table("policy_chunks")

    op.drop_index(op.f("ix_policy_documents_status"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_department"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_policy_type"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_title"), table_name="policy_documents")
    op.drop_index(op.f("ix_policy_documents_id"), table_name="policy_documents")
    op.drop_table("policy_documents")

    op.drop_index(op.f("ix_claims_policy_decision"), table_name="claims")
    op.drop_index(op.f("ix_claims_treatment"), table_name="claims")
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_column("policy_checked_at")
        batch_op.drop_column("policy_reason")
        batch_op.drop_column("policy_source")
        batch_op.drop_column("policy_confidence")
        batch_op.drop_column("policy_approved_amount")
        batch_op.drop_column("policy_decision")
        batch_op.drop_column("treatment")
