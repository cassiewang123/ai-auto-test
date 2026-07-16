"""Sensitive-field authenticated encryption, redaction, and migration tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.config import Settings
from app.models.environment import Environment
from app.models.notification_channel import NotificationChannel
from app.models.webhook_config import WebhookConfig
from app.services.ci_cd_service import sign_payload
from app.services.notification_service import gen_sign
from app.services.security.secret_crypto import (
    SecretConfigurationError,
    SecretCrypto,
    SecretDecryptionError,
    decrypt_cookies,
    decrypt_db_config,
    decrypt_secret,
    encrypt_secret,
    is_encrypted_secret,
)
from scripts.encrypt_existing_secrets import encrypt_existing_secrets


def _key(byte: int) -> str:
    return base64.urlsafe_b64encode(bytes([byte]) * 32).decode("ascii")


def test_authenticated_encryption_round_trip() -> None:
    crypto = SecretCrypto(_key(1), "v1")

    encrypted = crypto.encrypt("数据库密码-Secret123")

    assert encrypted is not None
    assert encrypted.startswith("enc:v1:")
    assert "Secret123" not in encrypted
    assert crypto.decrypt(encrypted) == "数据库密码-Secret123"
    assert crypto.encrypt(encrypted) == encrypted


def test_environment_secret_helpers_decrypt_for_runtime_use() -> None:
    encrypted_password = encrypt_secret("runtime-db-password")
    encrypted_cookie = encrypt_secret("runtime-cookie")

    db_config = decrypt_db_config({"db_type": "oracle", "password": encrypted_password})
    cookies = decrypt_cookies([{"name": "session", "value": encrypted_cookie}])

    assert db_config is not None
    assert db_config["password"] == "runtime-db-password"
    assert cookies[0]["value"] == "runtime-cookie"


def test_wrong_key_and_tampering_are_rejected() -> None:
    encrypted = SecretCrypto(_key(1)).encrypt("secret")
    assert encrypted is not None

    with pytest.raises(SecretDecryptionError, match="authentication failed"):
        SecretCrypto(_key(2)).decrypt(encrypted)

    tamper_index = len("enc:v1:") + 8
    replacement = "A" if encrypted[tamper_index] != "A" else "B"
    tampered = encrypted[:tamper_index] + replacement + encrypted[tamper_index + 1 :]
    with pytest.raises(SecretDecryptionError):
        SecretCrypto(_key(1)).decrypt(tampered)


def test_legacy_plaintext_read_is_supported() -> None:
    assert decrypt_secret("legacy-plaintext") == "legacy-plaintext"
    with pytest.raises(SecretDecryptionError):
        SecretCrypto(_key(1)).decrypt(
            "legacy-plaintext",
            allow_plaintext=False,
        )


def test_missing_development_key_fails_sensitive_write_clearly() -> None:
    settings = SimpleNamespace(
        SECRET_ENCRYPTION_KEY="",
        SECRET_ENCRYPTION_KEY_VERSION="v1",
    )
    with (
        patch(
            "app.services.security.secret_crypto.get_settings",
            return_value=settings,
        ),
        pytest.raises(SecretConfigurationError, match="required"),
    ):
        encrypt_secret("must-not-be-plaintext")


def test_missing_development_key_returns_api_error_without_plaintext_write(
    client,
    db_session,
) -> None:
    settings = SimpleNamespace(
        SECRET_ENCRYPTION_KEY="",
        SECRET_ENCRYPTION_KEY_VERSION="v1",
    )
    with patch(
        "app.services.security.secret_crypto.get_settings",
        return_value=settings,
    ):
        response = client.post(
            "/api/v1/notifications/channels",
            json={
                "name": "must-fail",
                "type": "feishu",
                "webhook_url": "https://example.com/notification",
                "secret": "must-not-be-stored",
            },
        )

    assert response.status_code == 422
    assert "SECRET_ENCRYPTION_KEY is required" in response.text
    assert db_session.query(NotificationChannel).filter(NotificationChannel.name == "must-fail").first() is None


def test_production_rejects_default_or_missing_key() -> None:
    with pytest.raises(PydanticValidationError, match="explicit"):
        Settings(_env_file=None, ENVIRONMENT="production")

    with pytest.raises(PydanticValidationError, match="explicit"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_ENCRYPTION_KEY="",
        )


def test_environment_api_encrypts_at_rest_and_never_leaks(
    client,
    db_session,
) -> None:
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "secure-env",
            "base_url": "https://secure.example.com",
            "db_config": {
                "db_type": "oracle",
                "username": "app",
                "password": "db-plain-secret",
            },
            "cookies": [
                {
                    "name": "session",
                    "value": "cookie-plain-secret",
                    "domain": "secure.example.com",
                    "path": "/",
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload_text = response.text
    data = response.json()["data"]
    assert "db-plain-secret" not in payload_text
    assert "cookie-plain-secret" not in payload_text
    assert data["db_config"]["password"] == "****"
    assert data["db_config"]["has_password"] is True
    assert data["cookies"][0]["value"] == "****"
    assert data["cookies"][0]["has_value"] is True

    environment = db_session.get(Environment, data["id"])
    assert environment is not None
    stored_password = environment.db_config["password"]
    stored_cookie = environment.cookies[0]["value"]
    assert is_encrypted_secret(stored_password)
    assert is_encrypted_secret(stored_cookie)
    assert decrypt_secret(stored_password) == "db-plain-secret"
    assert decrypt_secret(stored_cookie) == "cookie-plain-secret"

    detail = client.get(f"/api/v1/environments/{data['id']}")
    assert detail.status_code == 200
    assert "db-plain-secret" not in detail.text
    assert "cookie-plain-secret" not in detail.text

    masked_update = client.put(
        f"/api/v1/environments/{data['id']}",
        json={
            "db_config": data["db_config"],
            "cookies": data["cookies"],
        },
    )
    assert masked_update.status_code == 200, masked_update.text
    db_session.refresh(environment)
    assert environment.db_config["password"] == stored_password
    assert environment.cookies[0]["value"] == stored_cookie
    assert "has_password" not in environment.db_config
    assert "has_value" not in environment.cookies[0]


def test_notification_and_webhook_secrets_encrypt_and_sign_transparently(
    client,
    db_session,
) -> None:
    channel_response = client.post(
        "/api/v1/notifications/channels",
        json={
            "name": "secure-channel",
            "type": "feishu",
            "webhook_url": "https://example.com/notification",
            "secret": "notification-plain-secret",
        },
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_data = channel_response.json()["data"]
    assert "secret" not in channel_data
    assert channel_data["has_secret"] is True
    assert "notification-plain-secret" not in channel_response.text

    channel = db_session.get(NotificationChannel, channel_data["id"])
    assert channel is not None
    assert is_encrypted_secret(channel.secret)
    timestamp = "1700000000"
    expected_sign = base64.b64encode(
        hmac.new(
            b"notification-plain-secret",
            b"1700000000\nnotification-plain-secret",
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    assert gen_sign(channel.secret, timestamp) == expected_sign

    webhook_response = client.post(
        "/api/v1/ci/webhooks",
        json={
            "name": "secure-webhook",
            "url": "https://example.com/callback",
            "events": ["test_run.completed"],
            "secret": "webhook-plain-secret",
        },
    )
    assert webhook_response.status_code == 200, webhook_response.text
    webhook_data = webhook_response.json()["data"]
    assert "secret" not in webhook_data
    assert webhook_data["has_secret"] is True
    assert "webhook-plain-secret" not in webhook_response.text

    webhook = db_session.get(WebhookConfig, webhook_data["id"])
    assert webhook is not None
    assert is_encrypted_secret(webhook.secret)
    body = b'{"event":"test_run.completed"}'
    expected_webhook_sign = hmac.new(
        b"webhook-plain-secret",
        body,
        hashlib.sha256,
    ).hexdigest()
    assert sign_payload(webhook.secret, body) == expected_webhook_sign


def test_existing_secret_migration_is_dry_run_safe_and_idempotent(
    db_session,
) -> None:
    environment = Environment(
        name="legacy-env",
        base_url="https://legacy.example.com",
        variables={},
        db_config={"username": "legacy", "password": "legacy-db-password"},
        cookies=[{"name": "session", "value": "legacy-cookie"}],
    )
    channel = NotificationChannel(
        name="legacy-channel",
        type="feishu",
        webhook_url="https://example.com/notification",
        secret="legacy-notification-secret",
    )
    webhook = WebhookConfig(
        name="legacy-webhook",
        url="https://example.com/callback",
        events=["test_run.completed"],
        secret="legacy-webhook-secret",
    )
    db_session.add_all([environment, channel, webhook])
    db_session.commit()

    dry_run = encrypt_existing_secrets(db_session, dry_run=True)
    assert dry_run["encrypted"] == 4
    assert environment.db_config["password"] == "legacy-db-password"
    assert environment.cookies[0]["value"] == "legacy-cookie"
    assert channel.secret == "legacy-notification-secret"
    assert webhook.secret == "legacy-webhook-secret"

    first_run = encrypt_existing_secrets(db_session)
    assert first_run["encrypted"] == 4
    assert is_encrypted_secret(environment.db_config["password"])
    assert is_encrypted_secret(environment.cookies[0]["value"])
    assert is_encrypted_secret(channel.secret)
    assert is_encrypted_secret(webhook.secret)

    second_run = encrypt_existing_secrets(db_session)
    assert second_run["encrypted"] == 0
    assert second_run["already_encrypted"] == (
        first_run["encrypted"] + first_run["already_encrypted"]
    )
