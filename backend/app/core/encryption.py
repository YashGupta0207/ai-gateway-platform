"""
Credential encryption service.

Every provider credential value (API key, connection string, endpoint,
secret, custom field) is encrypted before it ever touches the database.
Uses Fernet: AES-128-CBC for confidentiality + HMAC-SHA256 for integrity,
so tampered ciphertext is rejected rather than silently decrypted.

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
and set it as CREDENTIAL_ENCRYPTION_KEY in the environment. Never hardcode it.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class EncryptionError(Exception):
    pass


class CredentialCipher:
    def __init__(self, key: str | None = None):
        self._fernet = Fernet((key or settings.CREDENTIAL_ENCRYPTION_KEY).encode())

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            raise EncryptionError("Cannot encrypt None value")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise EncryptionError("Credential ciphertext is invalid or has been tampered with") from exc

    def encrypt_dict(self, data: dict[str, str]) -> dict[str, str]:
        """Encrypt every value in a dynamic credential dict (see CREDENTIAL_STORAGE requirement)."""
        return {k: self.encrypt(v) for k, v in data.items() if v is not None}

    def decrypt_dict(self, data: dict[str, str]) -> dict[str, str]:
        return {k: self.decrypt(v) for k, v in data.items()}


cipher = CredentialCipher()
