from alembic import op
import sqlalchemy as sa

revision = "0007_decision_engine"
down_revision = "0006_claim_activity_timeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claim_verification_audits", sa.Column("deterministic_decision", sa.String(length=40), nullable=True))
    op.add_column("claim_verification_audits", sa.Column("deterministic_confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column("claim_verification_audits", sa.Column("gpt_decision", sa.String(length=40), nullable=True))
    op.add_column("claim_verification_audits", sa.Column("gpt_confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column(
        "claim_verification_audits",
        sa.Column("final_decision_source", sa.String(length=30), nullable=False, server_default="deterministic"),
    )
    op.add_column(
        "claim_verification_audits",
        sa.Column("auto_decision", sa.String(length=30), nullable=False, server_default="human"),
    )
    op.add_column("claim_verification_audits", sa.Column("risk_flags_json", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("claim_verification_audits", "risk_flags_json")
    op.drop_column("claim_verification_audits", "auto_decision")
    op.drop_column("claim_verification_audits", "final_decision_source")
    op.drop_column("claim_verification_audits", "gpt_confidence")
    op.drop_column("claim_verification_audits", "gpt_decision")
    op.drop_column("claim_verification_audits", "deterministic_confidence")
    op.drop_column("claim_verification_audits", "deterministic_decision")
