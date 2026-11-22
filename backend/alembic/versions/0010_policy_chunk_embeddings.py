"""Store policy-chunk embeddings in the database (SQL vector backend)

Revision ID: 0010_policy_chunk_embeddings
Revises: 0009_rag_pipeline_v2
Create Date: 2026-11-22 00:00:00.000000

Existing chunks keep embedding = NULL; the SQL vector store back-fills them from the stored
chunk text the first time it builds its index (or run scripts/reindex_policies.py).
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_policy_chunk_embeddings"
down_revision = "0009_rag_pipeline_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("policy_chunks") as batch_op:
        batch_op.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("policy_chunks") as batch_op:
        batch_op.drop_column("embedding")
