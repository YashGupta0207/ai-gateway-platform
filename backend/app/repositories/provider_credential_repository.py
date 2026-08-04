import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import cipher
from app.models.models import ProviderCredential


class DuplicateVariableError(ValueError):
    pass


class ProviderCredentialRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_provider(self, provider_id: uuid.UUID) -> list[ProviderCredential]:
        result = await self.db.execute(
            select(ProviderCredential)
            .where(ProviderCredential.provider_id == provider_id)
            .order_by(ProviderCredential.created_at)
        )
        return list(result.scalars().all())

    async def decrypt_all(self, provider_id: uuid.UUID) -> dict[str, str]:
        """Returns {variable_name: decrypted_value} — used by the Gateway to build the credentials dict an adapter receives."""
        rows = await self.list_by_provider(provider_id)
        return {row.variable_name: cipher.decrypt(row.encrypted_value) for row in rows}

    @staticmethod
    def _normalize_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Trims whitespace, rejects empty names, rejects duplicates (case-sensitive)."""
        cleaned: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw_name, value in pairs:
            name = (raw_name or "").strip()
            if not name:
                raise ValueError("Variable name cannot be empty.")
            normalized_name = name.casefold()
            if normalized_name in seen:
                raise DuplicateVariableError(f"Duplicate variable name: '{name}'")
            if not (value or "").strip():
                raise ValueError(f"Value for variable '{name}' cannot be empty.")
            seen.add(normalized_name)
            cleaned.append((name, value))
        return cleaned

    async def replace_all(self, provider_id: uuid.UUID, pairs: list[tuple[str, str]]) -> list[ProviderCredential]:
        """
        Full replace: whatever variable/value rows are passed in become the
        complete credential set for this provider. Existing rows not present
        in `pairs` are deleted; matching ones are updated in place; new ones
        are inserted. Only `value` is encrypted — `variable_name` stays
        plaintext (per the encryption requirement).
        """
        cleaned = self._normalize_pairs(pairs)
        existing = {row.variable_name: row for row in await self.list_by_provider(provider_id)}
        incoming_names = {name for name, _ in cleaned}

        for name, row in existing.items():
            if name not in incoming_names:
                await self.db.delete(row)

        for name, value in cleaned:
            if name in existing:
                existing[name].encrypted_value = cipher.encrypt(value)
            else:
                self.db.add(ProviderCredential(
                    provider_id=provider_id, variable_name=name, encrypted_value=cipher.encrypt(value),
                ))

        await self.db.commit()
        return await self.list_by_provider(provider_id)

    async def upsert_many(self, provider_id: uuid.UUID, pairs: list[tuple[str, str]]) -> list[ProviderCredential]:
        """Partial update: only touches the variables provided; leaves the rest alone. Used for credential rotation."""
        cleaned = self._normalize_pairs(pairs)
        existing = {row.variable_name: row for row in await self.list_by_provider(provider_id)}

        for name, value in cleaned:
            if name in existing:
                existing[name].encrypted_value = cipher.encrypt(value)
            else:
                self.db.add(ProviderCredential(
                    provider_id=provider_id, variable_name=name, encrypted_value=cipher.encrypt(value),
                ))

        await self.db.commit()
        return await self.list_by_provider(provider_id)

    async def delete_variable(self, provider_id: uuid.UUID, variable_name: str) -> None:
        await self.db.execute(
            delete(ProviderCredential).where(
                ProviderCredential.provider_id == provider_id,
                ProviderCredential.variable_name == variable_name,
            )
        )
        await self.db.commit()
