"""add claim activity timeline

Revision ID: 0006_claim_activity_timeline
Revises: 0005_policy_lifecycle
Create Date: 2026-09-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_claim_activity_timeline"
down_revision = "0005_policy_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claim_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("status_before", sa.String(length=30), nullable=True),
        sa.Column("status_after", sa.String(length=30), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_claim_events_id"), "claim_events", ["id"], unique=False)
    op.create_index(op.f("ix_claim_events_claim_id"), "claim_events", ["claim_id"], unique=False)
    op.create_index(op.f("ix_claim_events_actor_user_id"), "claim_events", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_claim_events_event_type"), "claim_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_claim_events_created_at"), "claim_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_claim_events_created_at"), table_name="claim_events")
    op.drop_index(op.f("ix_claim_events_event_type"), table_name="claim_events")
    op.drop_index(op.f("ix_claim_events_actor_user_id"), table_name="claim_events")
    op.drop_index(op.f("ix_claim_events_claim_id"), table_name="claim_events")
    op.drop_index(op.f("ix_claim_events_id"), table_name="claim_events")
    op.drop_table("claim_events")
