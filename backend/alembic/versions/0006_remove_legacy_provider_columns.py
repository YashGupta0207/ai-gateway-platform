"""remove legacy provider columns

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Drop provider_credentials table
    op.drop_index('ix_provider_credentials_provider_id', table_name='provider_credentials')
    op.drop_table('provider_credentials')
    
    # Drop provider_id from developer_tokens
    op.drop_constraint('developer_tokens_provider_id_fkey', 'developer_tokens', type_='foreignkey')
    op.drop_column('developer_tokens', 'provider_id')

def downgrade() -> None:
    # Re-add provider_id to developer_tokens
    op.add_column('developer_tokens', sa.Column('provider_id', pg.UUID(as_uuid=True), sa.ForeignKey("providers.id", ondelete="RESTRICT"), nullable=True))
    
    # Re-add provider_credentials table
    op.create_table(
        "provider_credentials",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", pg.UUID(as_uuid=True), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variable_name", sa.String(150), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "variable_name", name="uq_provider_credential_variable")
    )
    op.create_index("ix_provider_credentials_provider_id", "provider_credentials", ["provider_id"])
