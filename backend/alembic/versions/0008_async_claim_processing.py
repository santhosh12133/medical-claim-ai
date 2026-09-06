from alembic import op
import sqlalchemy as sa

revision = "0008_async_claim_processing"
down_revision = "0007_decision_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("processing_status", sa.String(length=30), nullable=False, server_default="queued"))
    op.add_column("claims", sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("claims", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("claims", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claims", sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_claims_processing_status", "claims", ["processing_status"])


def downgrade() -> None:
    op.drop_index("ix_claims_processing_status", table_name="claims")
    op.drop_column("claims", "processing_completed_at")
    op.drop_column("claims", "processing_started_at")
    op.drop_column("claims", "processing_error")
    op.drop_column("claims", "processing_attempts")
    op.drop_column("claims", "processing_status")
