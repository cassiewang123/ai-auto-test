"""Local backup, restore and cleanup workflows."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.local_data import (
    BACKUP_PREFIX,
    LocalPaths,
    apply_cleanup,
    cleanup_candidates,
    create_backup,
    restore_backup,
    verify_backup,
)


def _paths(tmp_path: Path) -> LocalPaths:
    root = tmp_path / "project"
    return LocalPaths(
        project_root=root,
        database=root / "airetest-lite.db",
        artifact_root=root / ".uploads",
        legacy_artifact_root=root / "backend" / ".uploads",
        runtime_secret=root / ".runtime" / "initial-admin.txt",
        backup_root=root / ".backups",
    )


def _create_database(path: Path, value: str = "original") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))
        connection.commit()


def test_backup_verify_and_restore_round_trip(tmp_path) -> None:
    paths = _paths(tmp_path)
    _create_database(paths.database)
    (paths.artifact_root / "jobs" / "job-1").mkdir(parents=True)
    (paths.artifact_root / "jobs" / "job-1" / "report.json").write_text(
        '{"ok": true}', encoding="utf-8"
    )
    paths.legacy_artifact_root.mkdir(parents=True)
    (paths.legacy_artifact_root / "legacy.txt").write_text(
        "legacy", encoding="utf-8"
    )
    paths.runtime_secret.parent.mkdir(parents=True)
    paths.runtime_secret.write_text("admin-password", encoding="utf-8")

    backup = create_backup(paths)
    manifest = verify_backup(backup)
    assert {item["role"] for item in manifest["components"]} == {
        "database",
        "artifacts",
        "legacy-artifacts",
        "initial-admin",
    }

    paths.database.unlink()
    _create_database(paths.database, "changed")
    (paths.artifact_root / "jobs" / "job-1" / "report.json").write_text(
        "changed", encoding="utf-8"
    )
    paths.runtime_secret.write_text("changed", encoding="utf-8")

    restore_backup(paths, backup)

    with closing(sqlite3.connect(paths.database)) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "original"
    assert (
        paths.artifact_root / "jobs" / "job-1" / "report.json"
    ).read_text(encoding="utf-8") == '{"ok": true}'
    assert paths.runtime_secret.read_text(encoding="utf-8") == "admin-password"


def test_verify_rejects_tampered_backup(tmp_path) -> None:
    paths = _paths(tmp_path)
    _create_database(paths.database)
    backup = create_backup(paths)
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    database = backup / manifest["components"][0]["archive"]
    database.write_bytes(database.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="size mismatch"):
        verify_backup(backup)


def test_restore_rejects_manifest_destination_outside_component_role(
    tmp_path,
) -> None:
    paths = _paths(tmp_path)
    _create_database(paths.database)
    backup = create_backup(paths)
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"][0]["destination"] = "backend/app/config.py"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="restore destination"):
        restore_backup(paths, backup)


def test_cleanup_removes_only_expired_safe_candidates(tmp_path) -> None:
    paths = _paths(tmp_path)
    _create_database(paths.database)
    with closing(sqlite3.connect(paths.database)) as connection:
        connection.execute("CREATE TABLE execution_jobs (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO execution_jobs VALUES ('active-job')")
        connection.commit()

    old_backup = paths.backup_root / f"{BACKUP_PREFIX}old"
    recent_backup = paths.backup_root / f"{BACKUP_PREFIX}recent"
    old_orphan = paths.artifact_root / "jobs" / "orphan-job"
    active_job = paths.artifact_root / "jobs" / "active-job"
    for directory in (old_backup, recent_backup, old_orphan, active_job):
        directory.mkdir(parents=True, exist_ok=True)
    old_time = (datetime.now(UTC) - timedelta(days=60)).timestamp()
    os.utime(old_backup, (old_time, old_time))
    os.utime(old_orphan, (old_time, old_time))
    os.utime(active_job, (old_time, old_time))

    candidates = cleanup_candidates(paths, 30, include_artifacts=True)
    assert old_backup in candidates
    assert old_orphan in candidates
    assert recent_backup not in candidates
    assert active_job not in candidates

    apply_cleanup(paths, candidates)
    assert not old_backup.exists()
    assert not old_orphan.exists()
    assert recent_backup.exists()
    assert active_job.exists()
