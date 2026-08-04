"""token management and usage

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("developer_tokens", sa.Column("encrypted_token", sa.Text(), nullable=True))
    op.add_column("developer_tokens", sa.Column("last_client_ip", sa.String(64), nullable=True))
    op.add_column("developer_tokens", sa.Column("last_user_agent", sa.String(1000), nullable=True))
    for name in ("daily_request_limit", "monthly_request_limit", "daily_token_limit", "monthly_token_limit"):
        op.add_column("developer_tokens", sa.Column(name, sa.Integer(), nullable=True))
    for name in ("total_requests", "prompt_tokens", "completion_tokens", "total_tokens", "total_latency_ms"):
        op.add_column("developer_tokens", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("developer_tokens", sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"))
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        op.add_column("api_request_logs", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("api_request_logs", sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"))
    op.add_column("api_request_logs", sa.Column("user_agent", sa.String(1000), nullable=True))
    op.add_column("api_request_logs", sa.Column("is_streaming", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_api_request_logs_token_created", "api_request_logs", ["developer_token_id", "created_at"])
    op.create_index("ix_api_request_logs_provider_created", "api_request_logs", ["provider_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_request_logs_provider_created", table_name="api_request_logs")
    op.drop_index("ix_api_request_logs_token_created", table_name="api_request_logs")
    for name in ("is_streaming", "user_agent", "estimated_cost", "total_tokens", "completion_tokens", "prompt_tokens"):
        op.drop_column("api_request_logs", name)
    for name in ("estimated_cost", "total_latency_ms", "total_tokens", "completion_tokens", "prompt_tokens", "total_requests", "monthly_token_limit", "daily_token_limit", "monthly_request_limit", "daily_request_limit", "last_user_agent", "last_client_ip", "encrypted_token"):
        op.drop_column("developer_tokens", name)
