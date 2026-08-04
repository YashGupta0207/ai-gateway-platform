"""request outcome counters

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("developer_tokens", sa.Column("successful_requests", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("developer_tokens", sa.Column("failed_requests", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("developer_tokens", sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("developer_tokens", "first_used_at")
    op.drop_column("developer_tokens", "failed_requests")
    op.drop_column("developer_tokens", "successful_requests")
