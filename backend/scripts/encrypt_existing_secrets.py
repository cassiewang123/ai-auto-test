"""Encrypt legacy plaintext secrets in-place without changing the database schema."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Encrypt existing AIRETEST plaintext secrets in-place.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="SQLAlchemy database URL; defaults to DATABASE_URL/application config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would change without updating the database.",
    )
    return parser.parse_args()


def _encrypt_value(
    value: str | None,
    *,
    max_ciphertext_length: int | None = None,
) -> tuple[str | None, bool]:
    from app.services.security.secret_crypto import encrypt_secret

    if value is None or value == "":
        return value, False
    encrypted = encrypt_secret(
        value,
        max_ciphertext_length=max_ciphertext_length,
    )
    return encrypted, encrypted != value


def encrypt_existing_secrets(
    db: Session,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Encrypt supported legacy fields and return migration counters.

    Existing ciphertext is authenticated and left unchanged, so repeated runs
    are idempotent. No ORM value is assigned during a dry run.
    """
    from app.models.environment import Environment
    from app.models.notification_channel import NotificationChannel
    from app.models.webhook_config import WebhookConfig
    from app.services.security.secret_crypto import is_encrypted_secret

    stats = {
        "environment_passwords": 0,
        "cookie_values": 0,
        "notification_urls": 0,
        "notification_secrets": 0,
        "webhook_urls": 0,
        "webhook_secrets": 0,
        "urls_encrypted": 0,
        "urls_already_encrypted": 0,
        "encrypted": 0,
        "already_encrypted": 0,
        "total_encrypted": 0,
        "total_already_encrypted": 0,
    }

    try:
        environments = list(db.scalars(select(Environment)))
        for environment in environments:
            config = dict(environment.db_config or {})
            config_changed = False
            password = config.get("password")
            if password:
                stats["environment_passwords"] += 1
                was_encrypted = is_encrypted_secret(password)
                encrypted, changed = _encrypt_value(password)
                if changed:
                    config["password"] = encrypted
                    config_changed = True
                    stats["encrypted"] += 1
                    stats["total_encrypted"] += 1
                elif was_encrypted:
                    stats["already_encrypted"] += 1
                    stats["total_already_encrypted"] += 1

            cookies: list[dict[str, Any]] = []
            cookies_changed = False
            for source_cookie in environment.cookies or []:
                cookie = dict(source_cookie)
                value = cookie.get("value")
                if value:
                    stats["cookie_values"] += 1
                    was_encrypted = is_encrypted_secret(value)
                    encrypted, changed = _encrypt_value(value)
                    if changed:
                        cookie["value"] = encrypted
                        cookies_changed = True
                        stats["encrypted"] += 1
                        stats["total_encrypted"] += 1
                    elif was_encrypted:
                        stats["already_encrypted"] += 1
                        stats["total_already_encrypted"] += 1
                cookies.append(cookie)

            if not dry_run:
                if config_changed:
                    environment.db_config = config
                if cookies_changed:
                    environment.cookies = cookies

        channels = list(db.scalars(select(NotificationChannel)))
        for channel in channels:
            if channel.webhook_url:
                stats["notification_urls"] += 1
                was_encrypted = is_encrypted_secret(channel.webhook_url)
                encrypted, changed = _encrypt_value(channel.webhook_url)
                if changed:
                    stats["urls_encrypted"] += 1
                    stats["total_encrypted"] += 1
                    if not dry_run:
                        channel.webhook_url = encrypted or ""
                elif was_encrypted:
                    stats["urls_already_encrypted"] += 1
                    stats["total_already_encrypted"] += 1

            if not channel.secret:
                continue
            stats["notification_secrets"] += 1
            was_encrypted = is_encrypted_secret(channel.secret)
            encrypted, changed = _encrypt_value(channel.secret)
            if changed:
                stats["encrypted"] += 1
                stats["total_encrypted"] += 1
                if not dry_run:
                    channel.secret = encrypted
            elif was_encrypted:
                stats["already_encrypted"] += 1
                stats["total_already_encrypted"] += 1

        webhooks = list(db.scalars(select(WebhookConfig)))
        for webhook in webhooks:
            if webhook.url:
                stats["webhook_urls"] += 1
                was_encrypted = is_encrypted_secret(webhook.url)
                encrypted, changed = _encrypt_value(
                    webhook.url,
                    max_ciphertext_length=2048,
                )
                if changed:
                    stats["urls_encrypted"] += 1
                    stats["total_encrypted"] += 1
                    if not dry_run:
                        webhook.url = encrypted or ""
                elif was_encrypted:
                    stats["urls_already_encrypted"] += 1
                    stats["total_already_encrypted"] += 1

            if not webhook.secret:
                continue
            stats["webhook_secrets"] += 1
            was_encrypted = is_encrypted_secret(webhook.secret)
            encrypted, changed = _encrypt_value(
                webhook.secret,
                max_ciphertext_length=256,
            )
            if changed:
                stats["encrypted"] += 1
                stats["total_encrypted"] += 1
                if not dry_run:
                    webhook.secret = encrypted
            elif was_encrypted:
                stats["already_encrypted"] += 1
                stats["total_already_encrypted"] += 1

        if not dry_run:
            db.commit()
    except Exception:
        db.rollback()
        raise

    return stats


def main() -> None:
    args = parse_args()
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            stats = encrypt_existing_secrets(db, dry_run=args.dry_run)
    finally:
        engine.dispose()

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                **stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
