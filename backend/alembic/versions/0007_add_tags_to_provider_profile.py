"""add tags to provider profile

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('provider_profiles', sa.Column('tags', pg.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))

def downgrade() -> None:
    op.drop_column('provider_profiles', 'tags')
