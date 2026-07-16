"""Authenticated encryption helpers for secrets stored in application tables."""
from __future__ import annotations

import base64
import binascii
import os
import re
from typing import Any, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

ENCRYPTED_PREFIX = "enc:"
MASKED_URL = "****"
_VERSION_PATTERN = re.compile(r"^v[1-9][0-9]*$")
_NONCE_SIZE = 12


class SecretCryptoError(RuntimeError):
    """Base error for secret encryption and decryption."""


class SecretConfigurationError(SecretCryptoError):
    """Raised when the encryption key configuration is missing or invalid."""


class SecretDecryptionError(SecretCryptoError):
    """Raised when an encrypted value cannot be authenticated or decrypted."""


def decode_encryption_key(encoded_key: str) -> bytes:
    """Decode a URL-safe base64 AES-256 key."""
    if not encoded_key:
        raise SecretConfigurationError(
            "SECRET_ENCRYPTION_KEY is required before sensitive values can be written"
        )
    try:
        key = base64.b64decode(encoded_key, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SecretConfigurationError(
            "SECRET_ENCRYPTION_KEY must be URL-safe base64"
        ) from exc
    if len(key) != 32:
        raise SecretConfigurationError(
            "SECRET_ENCRYPTION_KEY must decode to exactly 32 bytes"
        )
    return key


class SecretCrypto:
    """Encrypt secrets with AES-256-GCM and a versioned storage prefix."""

    def __init__(self, encoded_key: str, key_version: str = "v1") -> None:
        if not _VERSION_PATTERN.fullmatch(key_version):
            raise SecretConfigurationError(
                "SECRET_ENCRYPTION_KEY_VERSION must use the form v1, v2, ..."
            )
        self.key_version = key_version
        self._aesgcm = AESGCM(decode_encryption_key(encoded_key))

    @property
    def prefix(self) -> str:
        return f"{ENCRYPTED_PREFIX}{self.key_version}:"

    def encrypt(
        self,
        value: str | None,
        *,
        max_ciphertext_length: int | None = None,
    ) -> str | None:
        """Encrypt a value, preserving ``None`` and empty strings.

        Existing versioned ciphertext is authenticated before being returned,
        making the operation idempotent without accepting malformed ciphertext.
        """
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            raise TypeError("Secret values must be strings")
        if is_encrypted_secret(value):
            self.decrypt(value, allow_plaintext=False)
            encrypted = value
        else:
            nonce = os.urandom(_NONCE_SIZE)
            aad = self._aad(self.key_version)
            ciphertext = self._aesgcm.encrypt(nonce, value.encode("utf-8"), aad)
            token = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
            encrypted = f"{self.prefix}{token.rstrip('=')}"
        if max_ciphertext_length is not None and len(encrypted) > max_ciphertext_length:
            raise SecretConfigurationError(
                "Encrypted secret exceeds the configured database column length"
            )
        return encrypted

    def decrypt(
        self,
        value: str | None,
        *,
        allow_plaintext: bool = True,
    ) -> str | None:
        """Decrypt a versioned value, optionally returning legacy plaintext."""
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            raise TypeError("Secret values must be strings")
        if not is_encrypted_secret(value):
            if allow_plaintext:
                return value
            raise SecretDecryptionError("Expected a versioned encrypted secret")

        parts = value.split(":", 2)
        if len(parts) != 3 or not parts[2]:
            raise SecretDecryptionError("Encrypted secret has an invalid format")
        version, token = parts[1], parts[2]
        if version != self.key_version:
            raise SecretDecryptionError(
                f"Encrypted secret uses unsupported key version: {version}"
            )
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        except (binascii.Error, ValueError) as exc:
            raise SecretDecryptionError(
                "Encrypted secret payload is not valid base64"
            ) from exc
        if len(raw) <= _NONCE_SIZE:
            raise SecretDecryptionError("Encrypted secret payload is truncated")
        nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
        try:
            plaintext = cast(
                bytes,
                self._aesgcm.decrypt(
                    nonce,
                    ciphertext,
                    self._aad(version),
                ),
            )
        except InvalidTag as exc:
            raise SecretDecryptionError(
                "Encrypted secret authentication failed; check the encryption key"
            ) from exc
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SecretDecryptionError(
                "Encrypted secret does not contain valid UTF-8"
            ) from exc

    @staticmethod
    def _aad(version: str) -> bytes:
        return f"AIRETEST:secret:{version}".encode("ascii")


def is_encrypted_secret(value: Any) -> bool:
    """Return whether a value uses the application's versioned ciphertext format."""
    if not isinstance(value, str) or not value.startswith(ENCRYPTED_PREFIX):
        return False
    parts = value.split(":", 2)
    return len(parts) == 3 and bool(_VERSION_PATTERN.fullmatch(parts[1]))


def get_secret_crypto() -> SecretCrypto:
    """Build the configured secret cipher.

    This intentionally does not silently fall back to ``SECRET_KEY`` or
    plaintext storage when the dedicated encryption key is unavailable.
    """
    settings = get_settings()
    return SecretCrypto(
        settings.SECRET_ENCRYPTION_KEY,
        settings.SECRET_ENCRYPTION_KEY_VERSION,
    )


def encrypt_secret(
    value: str | None,
    *,
    max_ciphertext_length: int | None = None,
) -> str | None:
    """Encrypt one optional secret using the active application key."""
    if value is None or value == "":
        return value
    return get_secret_crypto().encrypt(
        value,
        max_ciphertext_length=max_ciphertext_length,
    )


def decrypt_secret(
    value: str | None,
    *,
    allow_plaintext: bool = True,
) -> str | None:
    """Decrypt one optional secret while supporting legacy plaintext reads."""
    if value is None or value == "":
        return value
    if allow_plaintext and not is_encrypted_secret(value):
        return value
    return get_secret_crypto().decrypt(value, allow_plaintext=allow_plaintext)


def encrypt_url(
    value: str | None,
    *,
    max_ciphertext_length: int | None = None,
) -> str | None:
    """Encrypt an outbound URL with the active AES-256-GCM key."""
    return encrypt_secret(
        value,
        max_ciphertext_length=max_ciphertext_length,
    )


def decrypt_url(value: str | None) -> str | None:
    """Decrypt an outbound URL while accepting legacy plaintext rows."""
    return decrypt_secret(value, allow_plaintext=True)


def mask_url(value: str | None) -> str:
    """Return a stable response mask without decrypting the stored URL."""
    return MASKED_URL if value else ""


def is_masked_url(value: Any) -> bool:
    """Return whether a request contains the response URL placeholder."""
    return isinstance(value, str) and value == MASKED_URL


def prepare_url_for_storage(
    value: str | None,
    *,
    existing: str | None = None,
    max_ciphertext_length: int | None = None,
) -> str | None:
    """Encrypt a URL or preserve an existing value represented by its mask."""
    if is_masked_url(value):
        if existing:
            return existing
        raise SecretCryptoError("Masked URL cannot be used without an existing value")
    return encrypt_url(
        value,
        max_ciphertext_length=max_ciphertext_length,
    )


def redact_url_from_text(message: str, *urls: str | None) -> str:
    """Remove stored/plaintext URLs from an error message."""
    redacted = message
    for value in urls:
        if not value:
            continue
        redacted = redacted.replace(value, MASKED_URL)
        try:
            plaintext = decrypt_url(value)
        except SecretCryptoError:
            plaintext = None
        if plaintext:
            redacted = redacted.replace(plaintext, MASKED_URL)
    return redacted


def encrypt_db_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Encrypt ``db_config.password`` without mutating the input mapping."""
    if config is None:
        return None
    encrypted = dict(config)
    if "password" in encrypted:
        password = encrypted["password"]
        if password is not None and not isinstance(password, str):
            raise TypeError("db_config.password must be a string")
        encrypted["password"] = encrypt_secret(password)
    return encrypted


def encrypt_cookies(
    cookies: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Encrypt every Cookie ``value`` without mutating the input list."""
    encrypted_cookies: list[dict[str, Any]] = []
    for cookie in cookies or []:
        encrypted = dict(cookie)
        if "value" in encrypted:
            value = encrypted["value"]
            if value is not None and not isinstance(value, str):
                raise TypeError("Cookie values must be strings")
            encrypted["value"] = encrypt_secret(value)
        encrypted_cookies.append(encrypted)
    return encrypted_cookies


def decrypt_db_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Decrypt ``db_config.password`` without mutating the stored mapping."""
    if config is None:
        return None
    decrypted = dict(config)
    password = decrypted.get("password")
    if password is not None:
        if not isinstance(password, str):
            raise TypeError("db_config.password must be a string")
        decrypted["password"] = decrypt_secret(password)
    return decrypted


def decrypt_cookies(
    cookies: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Decrypt Cookie values before constructing outbound request headers."""
    decrypted_cookies: list[dict[str, Any]] = []
    for cookie in cookies or []:
        decrypted = dict(cookie)
        value = decrypted.get("value")
        if value is not None:
            if not isinstance(value, str):
                raise TypeError("Cookie values must be strings")
            decrypted["value"] = decrypt_secret(value)
        decrypted_cookies.append(decrypted)
    return decrypted_cookies
