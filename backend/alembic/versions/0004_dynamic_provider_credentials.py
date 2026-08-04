"""dynamic provider credentials

Revision ID: 0004
Revises: 0003

Makes the Provider module fully generic:
  - adds `provider_credentials` (provider_id, variable_name, encrypted_value)
    — unlimited dynamic variable/value pairs per provider
  - adds `providers.description`
  - backfills every existing provider's `encrypted_credentials` JSONB blob
    into rows in the new table (values are already-encrypted ciphertext,
    so they're moved as-is — no re-encryption, no data loss)
  - drops the old fixed `providers.credential_schema` and
    `providers.encrypted_credentials` columns, now fully superseded

`providers.adapter_key` is untouched by this migration — it's still used,
now exposed to the API/UI as "provider_type", and is free text rather than
a constrained set of values.
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("description", sa.Text(), nullable=True))

    op.create_table(
        "provider_credentials",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", pg.UUID(as_uuid=True), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variable_name", sa.String(150), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "variable_name", name="uq_provider_credential_variable"),
    )
    op.create_index("ix_provider_credentials_provider_id", "provider_credentials", ["provider_id"])

    # --- Backfill: move each provider's existing encrypted_credentials JSONB
    # blob into individual rows. Values are already ciphertext produced by
    # the same CredentialCipher, so they carry over unchanged.
    connection = op.get_bind()
    existing_providers = connection.execute(
        sa.text("SELECT id, encrypted_credentials FROM providers WHERE encrypted_credentials IS NOT NULL")
    ).fetchall()

    insert_stmt = sa.text("""
        INSERT INTO provider_credentials (id, provider_id, variable_name, encrypted_value, created_at, updated_at)
        VALUES (:id, :provider_id, :variable_name, :encrypted_value, now(), now())
    """)
    for row in existing_providers:
        provider_id, creds = row[0], row[1] or {}
        for variable_name, encrypted_value in creds.items():
            connection.execute(insert_stmt, {
                "id": str(uuid.uuid4()), "provider_id": provider_id,
                "variable_name": variable_name, "encrypted_value": encrypted_value,
            })

    op.drop_column("providers", "credential_schema")
    op.drop_column("providers", "encrypted_credentials")


def downgrade() -> None:
    op.add_column("providers", sa.Column("encrypted_credentials", pg.JSONB(), nullable=False, server_default="{}"))
    op.add_column("providers", sa.Column("credential_schema", pg.JSONB(), nullable=False, server_default="[]"))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT provider_id, variable_name, encrypted_value FROM provider_credentials")).fetchall()
    grouped: dict[str, dict[str, str]] = {}
    for provider_id, variable_name, encrypted_value in rows:
        grouped.setdefault(str(provider_id), {})[variable_name] = encrypted_value
    for provider_id, creds in grouped.items():
        connection.execute(
            sa.text("UPDATE providers SET encrypted_credentials = :creds WHERE id = :id"),
            {"creds": sa.type_coerce(creds, pg.JSONB), "id": provider_id},
        )

    op.drop_index("ix_provider_credentials_provider_id", table_name="provider_credentials")
    op.drop_table("provider_credentials")
    op.drop_column("providers", "description")
