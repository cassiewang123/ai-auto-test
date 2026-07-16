"""Encrypted webhook URL storage, masking, migration, and runtime-use tests."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.environment import Environment
from app.models.notification_channel import NotificationChannel
from app.models.test_case import TestCase as CaseModel
from app.models.test_run_summary import TestRunSummary as RunSummaryModel
from app.models.webhook_config import WebhookConfig
from app.services.ci_cd_service import send_webhook, trigger_execution
from app.services.security.secret_crypto import (
    MASKED_URL,
    decrypt_secret,
    encrypt_secret,
    is_encrypted_secret,
)
from scripts.encrypt_existing_secrets import encrypt_existing_secrets


def _async_client_mock() -> tuple[MagicMock, AsyncMock]:
    response = MagicMock(status_code=200, text='{"ok":true}')
    response.raise_for_status = MagicMock()
    post = AsyncMock(return_value=response)
    client = MagicMock(post=post)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return context, post


def test_notification_url_is_encrypted_masked_and_preserved(
    client,
    db_session,
):
    plaintext_url = "https://notify.example.test/hooks/private-token"
    created = client.post(
        "/api/v1/notifications/channels",
        json={
            "name": "encrypted notification",
            "type": "slack",
            "webhook_url": plaintext_url,
        },
    )

    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["webhook_url"] == MASKED_URL
    assert data["has_url"] is True
    assert plaintext_url not in created.text

    channel = db_session.get(NotificationChannel, data["id"])
    assert channel is not None
    stored_url = channel.webhook_url
    assert is_encrypted_secret(stored_url)
    assert decrypt_secret(stored_url) == plaintext_url

    updated = client.put(
        f"/api/v1/notifications/channels/{channel.id}",
        json={"name": "renamed", "webhook_url": MASKED_URL},
    )
    assert updated.status_code == 200, updated.text
    db_session.refresh(channel)
    assert channel.webhook_url == stored_url

    context, post = _async_client_mock()
    with patch(
        "app.services.notification_service.httpx.AsyncClient",
        return_value=context,
    ):
        tested = client.post(
            f"/api/v1/notifications/channels/{channel.id}/test"
        )
    assert tested.status_code == 200
    assert post.call_args.args[0] == plaintext_url
    assert not post.call_args.args[0].startswith("enc:v1:")
    assert plaintext_url not in tested.text
    assert stored_url not in tested.text


def test_ci_webhook_url_is_encrypted_and_send_results_are_masked(
    client,
    db_session,
):
    plaintext_url = "https://ci.example.test/callback/private-token"
    created = client.post(
        "/api/v1/ci/webhooks",
        json={
            "name": "encrypted callback",
            "url": plaintext_url,
            "events": ["test_run.completed"],
        },
    )

    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["url"] == MASKED_URL
    assert data["has_url"] is True
    assert plaintext_url not in created.text

    webhook = db_session.get(WebhookConfig, data["id"])
    assert webhook is not None
    stored_url = webhook.url
    assert is_encrypted_secret(stored_url)
    assert decrypt_secret(stored_url) == plaintext_url

    updated = client.put(
        f"/api/v1/ci/webhooks/{webhook.id}",
        json={"name": "renamed callback", "url": MASKED_URL},
    )
    assert updated.status_code == 200, updated.text
    db_session.refresh(webhook)
    assert webhook.url == stored_url

    response = MagicMock(status_code=200, is_success=True)
    with patch(
        "app.services.ci_cd_service.httpx.post",
        return_value=response,
    ) as post:
        results = send_webhook(
            db_session,
            "test_run.completed",
            {"status": "passed"},
        )

    assert post.call_args.args[0] == plaintext_url
    assert results[0]["url"] == MASKED_URL
    assert results[0]["has_url"] is True
    serialized = json.dumps(results, ensure_ascii=False)
    assert plaintext_url not in serialized
    assert stored_url not in serialized


def test_webhook_request_errors_redact_plaintext_and_ciphertext(
    db_session,
):
    plaintext_url = "https://ci.example.test/callback/error-token"
    webhook = WebhookConfig(
        name="error callback",
        url=encrypt_secret(plaintext_url),
        events=["test_run.completed"],
        is_active=True,
    )
    db_session.add(webhook)
    db_session.commit()

    with patch(
        "app.services.ci_cd_service.httpx.post",
        side_effect=RuntimeError(f"failed to call {plaintext_url}"),
    ):
        results = send_webhook(
            db_session,
            "test_run.completed",
            {"status": "failed"},
        )

    serialized = json.dumps(results, ensure_ascii=False)
    assert results[0]["success"] is False
    assert results[0]["url"] == MASKED_URL
    assert plaintext_url not in serialized
    assert webhook.url not in serialized
    assert MASKED_URL in results[0]["error"]


def test_direct_orm_url_writes_are_encrypted(db_session):
    notification_url = "https://orm.example.test/notification"
    webhook_url = "https://orm.example.test/callback"
    channel = NotificationChannel(
        name="ORM notification",
        type="slack",
        webhook_url=notification_url,
    )
    webhook = WebhookConfig(
        name="ORM callback",
        url=webhook_url,
        events=[],
    )
    db_session.add_all([channel, webhook])
    db_session.commit()

    assert is_encrypted_secret(channel.webhook_url)
    assert is_encrypted_secret(webhook.url)
    assert decrypt_secret(channel.webhook_url) == notification_url
    assert decrypt_secret(webhook.url) == webhook_url


def test_url_migration_is_dry_run_safe_and_idempotent(db_session):
    channel_id = str(uuid.uuid4())
    webhook_id = str(uuid.uuid4())
    db_session.execute(
        NotificationChannel.__table__.insert().values(
            id=channel_id,
            name="legacy notification",
            type="slack",
            webhook_url="https://legacy.example.test/notification",
            is_active=True,
        )
    )
    db_session.execute(
        WebhookConfig.__table__.insert().values(
            id=webhook_id,
            name="legacy callback",
            url="https://legacy.example.test/callback",
            events=["test_run.completed"],
            is_active=True,
        )
    )
    db_session.commit()
    channel = db_session.get(NotificationChannel, channel_id)
    webhook = db_session.get(WebhookConfig, webhook_id)
    assert channel is not None
    assert webhook is not None

    dry_run = encrypt_existing_secrets(db_session, dry_run=True)
    assert dry_run["notification_urls"] == 1
    assert dry_run["webhook_urls"] == 1
    assert dry_run["urls_encrypted"] == 2
    assert dry_run["encrypted"] == 0
    assert dry_run["total_encrypted"] == 2
    assert not is_encrypted_secret(channel.webhook_url)
    assert not is_encrypted_secret(webhook.url)

    first_run = encrypt_existing_secrets(db_session)
    assert first_run["urls_encrypted"] == 2
    assert first_run["encrypted"] == 0
    assert first_run["total_encrypted"] == 2
    assert is_encrypted_secret(channel.webhook_url)
    assert is_encrypted_secret(webhook.url)

    second_run = encrypt_existing_secrets(db_session)
    assert second_run["encrypted"] == 0
    assert second_run["urls_encrypted"] == 0
    assert second_run["urls_already_encrypted"] == 2
    assert second_run["already_encrypted"] == 0
    assert second_run["total_already_encrypted"] == 2


def test_ci_execution_uses_decrypted_environment_cookie_without_leaking(
    db_session,
):
    plaintext_cookie = "ci-session-private"
    encrypted_cookie = encrypt_secret(plaintext_cookie)
    environment = Environment(
        name="CI encrypted cookie",
        base_url="https://api.example.test",
        variables={"tenant": "ci"},
        cookies=[
            {
                "name": "session",
                "value": encrypted_cookie,
                "domain": "api.example.test",
                "path": "/",
            }
        ],
    )
    case = CaseModel(
        title="CI cookie case",
        method="GET",
        url="/health",
        headers={"X-Test": "true"},
    )
    db_session.add_all([environment, case])
    db_session.commit()

    execution_result = SimpleNamespace(
        status="passed",
        duration=0.01,
        response=SimpleNamespace(status_code=200),
        error_message=None,
    )
    with patch("app.services.ci_cd_service._ci_executor") as executor:
        executor.execute.return_value = execution_result
        result = trigger_execution(
            db_session,
            case_ids=[case.id],
            environment_id=environment.id,
            source="ci",
        )

    request_def = executor.execute.call_args.kwargs["request_def"]
    assert request_def.headers["Cookie"] == f"session={plaintext_cookie}"
    assert "enc:v1:" not in request_def.headers["Cookie"]

    serialized_result = json.dumps(result, ensure_ascii=False)
    assert plaintext_cookie not in serialized_result
    assert encrypted_cookie not in serialized_result

    summary = (
        db_session.query(RunSummaryModel)
        .filter(RunSummaryModel.run_id == result["run_id"])
        .one()
    )
    serialized_summary = json.dumps(summary.summary, ensure_ascii=False)
    assert plaintext_cookie not in serialized_summary
    assert encrypted_cookie not in serialized_summary
