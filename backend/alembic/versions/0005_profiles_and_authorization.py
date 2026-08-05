"""provider profiles and token authorization

Revision ID: 0005
Revises: 0004
"""
import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("provider_profiles", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), sa.Column("provider_id", pg.UUID(as_uuid=True), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(150), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("priority", sa.Integer(), nullable=False, server_default="0"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_provider_profiles_provider_id", "provider_profiles", ["provider_id"])
    op.create_table("provider_profile_credentials", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), sa.Column("profile_id", pg.UUID(as_uuid=True), sa.ForeignKey("provider_profiles.id", ondelete="CASCADE"), nullable=False), sa.Column("variable_name", sa.String(150), nullable=False), sa.Column("encrypted_value", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("profile_id", "variable_name", name="uq_profile_credential_variable"))
    op.create_index("ix_provider_profile_credentials_profile_id", "provider_profile_credentials", ["profile_id"])
    op.create_table("token_provider_authorizations", sa.Column("id", pg.UUID(as_uuid=True), primary_key=True), sa.Column("developer_token_id", pg.UUID(as_uuid=True), sa.ForeignKey("developer_tokens.id", ondelete="CASCADE"), nullable=False), sa.Column("provider_id", pg.UUID(as_uuid=True), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("developer_token_id", "provider_id", name="uq_token_provider_authorization"))
    op.create_index("ix_token_provider_authorizations_developer_token_id", "token_provider_authorizations", ["developer_token_id"])
    bind = op.get_bind()
    for provider_id, display_name in bind.execute(sa.text("SELECT id, display_name FROM providers")):
        profile_id = uuid.uuid4()
        bind.execute(sa.text("INSERT INTO provider_profiles (id, provider_id, name, is_active, is_default, priority) VALUES (:id, :provider_id, :name, true, true, 0)"), {"id": str(profile_id), "provider_id": provider_id, "name": "Default"})
        credentials = bind.execute(sa.text("SELECT variable_name, encrypted_value FROM provider_credentials WHERE provider_id = :provider_id"), {"provider_id": provider_id}).fetchall()
        for variable_name, encrypted_value in credentials:
            bind.execute(sa.text("INSERT INTO provider_profile_credentials (id, profile_id, variable_name, encrypted_value) VALUES (:id, :profile_id, :variable_name, :encrypted_value)"), {"id": str(uuid.uuid4()), "profile_id": str(profile_id), "variable_name": variable_name, "encrypted_value": encrypted_value})
    for token_id, provider_id in bind.execute(sa.text("SELECT id, provider_id FROM developer_tokens")):
        bind.execute(sa.text("INSERT INTO token_provider_authorizations (id, developer_token_id, provider_id) VALUES (:id, :token_id, :provider_id)"), {"id": str(uuid.uuid4()), "token_id": token_id, "provider_id": provider_id})

def downgrade() -> None:
    op.drop_table("token_provider_authorizations")
    op.drop_table("provider_profile_credentials")
    op.drop_table("provider_profiles")
