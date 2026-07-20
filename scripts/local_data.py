"""Backup, verify, restore and clean AIRETEST local data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


BACKUP_PREFIX = "airetest-backup-"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class LocalPaths:
    project_root: Path
    database: Path
    artifact_root: Path
    legacy_artifact_root: Path
    runtime_secret: Path
    backup_root: Path


def _inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def _project_relative(path: Path, project_root: Path) -> str:
    return _inside(path, project_root).relative_to(project_root.resolve()).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_files(path: Path) -> bool:
    return path.is_dir() and any(item.is_file() for item in path.rglob("*"))


def resolve_local_paths(
    project_root: Path,
    backup_root: Path | None = None,
) -> LocalPaths:
    root = project_root.resolve()
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    try:
        from sqlalchemy.engine import make_url

        from app.config import get_settings

        settings = get_settings()
        database_url = make_url(settings.DATABASE_URL)
        if not database_url.drivername.startswith("sqlite"):
            raise RuntimeError(
                f"Local data tools require SQLite, got {database_url.drivername}"
            )
        if not database_url.database or database_url.database == ":memory:":
            raise RuntimeError("Local data tools require a file-backed SQLite database")

        database = Path(database_url.database)
        if not database.is_absolute():
            database = root / database
        artifact_root = Path(settings.ARTIFACT_ROOT)
        if not artifact_root.is_absolute():
            artifact_root = root / artifact_root
    finally:
        sys.path.remove(str(backend))

    resolved_backup_root = backup_root or Path(".backups")
    if not resolved_backup_root.is_absolute():
        resolved_backup_root = root / resolved_backup_root

    return LocalPaths(
        project_root=root,
        database=_inside(database, root),
        artifact_root=_inside(artifact_root, root),
        legacy_artifact_root=_inside(root / "backend" / ".uploads", root),
        runtime_secret=_inside(root / ".runtime" / "initial-admin.txt", root),
        backup_root=_inside(resolved_backup_root, root),
    )


def _backup_sqlite(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as source_db, closing(
        sqlite3.connect(destination)
    ) as target_db:
        source_db.backup(target_db)
        target_db.commit()
        integrity = target_db.execute("PRAGMA integrity_check").fetchone()[0]
        violations = target_db.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok":
        raise RuntimeError(f"Backup database integrity check failed: {integrity}")
    if violations:
        raise RuntimeError(
            f"Backup database has {len(violations)} foreign key violation(s)"
        )


def _copy_directory(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _manifest_files(backup_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted((backup_dir / "data").rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(backup_dir).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return files


def create_backup(paths: LocalPaths) -> Path:
    paths.backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_dir = paths.backup_root / f"{BACKUP_PREFIX}{timestamp}"
    if backup_dir.exists():
        backup_dir = paths.backup_root / (
            f"{BACKUP_PREFIX}{timestamp}-{uuid.uuid4().hex[:8]}"
        )
    temporary = paths.backup_root / f".{backup_dir.name}.tmp-{uuid.uuid4().hex}"
    components: list[dict[str, str]] = []

    try:
        data_dir = temporary / "data"
        database_archive = data_dir / "airetest-lite.db"
        _backup_sqlite(paths.database, database_archive)
        components.append(
            {
                "role": "database",
                "kind": "file",
                "archive": database_archive.relative_to(temporary).as_posix(),
                "destination": _project_relative(
                    paths.database, paths.project_root
                ),
            }
        )

        artifact_archive = data_dir / "artifacts"
        _copy_directory(paths.artifact_root, artifact_archive)
        components.append(
            {
                "role": "artifacts",
                "kind": "directory",
                "archive": artifact_archive.relative_to(temporary).as_posix(),
                "destination": _project_relative(
                    paths.artifact_root, paths.project_root
                ),
            }
        )

        if (
            paths.legacy_artifact_root != paths.artifact_root
            and _has_files(paths.legacy_artifact_root)
        ):
            legacy_archive = data_dir / "legacy-artifacts"
            _copy_directory(paths.legacy_artifact_root, legacy_archive)
            components.append(
                {
                    "role": "legacy-artifacts",
                    "kind": "directory",
                    "archive": legacy_archive.relative_to(temporary).as_posix(),
                    "destination": _project_relative(
                        paths.legacy_artifact_root, paths.project_root
                    ),
                }
            )

        if paths.runtime_secret.is_file():
            secret_archive = data_dir / "runtime" / "initial-admin.txt"
            secret_archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(paths.runtime_secret, secret_archive)
            components.append(
                {
                    "role": "initial-admin",
                    "kind": "file",
                    "archive": secret_archive.relative_to(temporary).as_posix(),
                    "destination": _project_relative(
                        paths.runtime_secret, paths.project_root
                    ),
                }
            )

        manifest = {
            "format_version": FORMAT_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "components": components,
            "files": _manifest_files(temporary),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.rename(backup_dir)
        return backup_dir
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _safe_archive_path(backup_dir: Path, value: str) -> Path:
    if not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError(f"Unsafe archive path: {value!r}")
    return _inside(backup_dir / value, backup_dir)


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    root = backup_dir.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Backup manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("Unsupported backup format version")

    for file_info in manifest.get("files", []):
        path = _safe_archive_path(root, str(file_info["path"]))
        if not path.is_file():
            raise FileNotFoundError(f"Backup file is missing: {path}")
        if path.stat().st_size != int(file_info["size"]):
            raise ValueError(f"Backup size mismatch: {path}")
        if _sha256(path) != file_info["sha256"]:
            raise ValueError(f"Backup checksum mismatch: {path}")

    databases = [
        item
        for item in manifest.get("components", [])
        if item.get("role") == "database"
    ]
    if len(databases) != 1:
        raise ValueError("Backup must contain exactly one database component")
    database = _safe_archive_path(root, databases[0]["archive"])
    with closing(sqlite3.connect(database)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok":
        raise ValueError(f"Backup database integrity check failed: {integrity}")
    if violations:
        raise ValueError(
            f"Backup database has {len(violations)} foreign key violation(s)"
        )
    return manifest


def restore_backup(paths: LocalPaths, backup_dir: Path) -> None:
    manifest = verify_backup(backup_dir)
    operation_id = uuid.uuid4().hex
    staged: list[tuple[Path, Path, str]] = []
    installed: list[tuple[Path, Path | None, str]] = []
    allowed_components = {
        "database": ("file", paths.database),
        "artifacts": ("directory", paths.artifact_root),
        "legacy-artifacts": ("directory", paths.legacy_artifact_root),
        "initial-admin": ("file", paths.runtime_secret),
    }
    seen_roles: set[str] = set()

    try:
        for component in manifest["components"]:
            role = str(component.get("role"))
            if role in seen_roles or role not in allowed_components:
                raise ValueError(f"Unsupported or duplicate backup component: {role}")
            seen_roles.add(role)
            expected_kind, expected_destination = allowed_components[role]
            if component.get("kind") != expected_kind:
                raise ValueError(f"Unexpected component kind for {role}")
            archive = _safe_archive_path(backup_dir.resolve(), component["archive"])
            destination = _inside(
                paths.project_root / component["destination"],
                paths.project_root,
            )
            if destination != expected_destination.resolve():
                raise ValueError(f"Unexpected restore destination for {role}")
            stage = destination.with_name(
                f".{destination.name}.restore-{operation_id}"
            )
            if stage.exists():
                shutil.rmtree(stage) if stage.is_dir() else stage.unlink()
            stage.parent.mkdir(parents=True, exist_ok=True)
            if component["kind"] == "directory":
                shutil.copytree(archive, stage)
            else:
                shutil.copy2(archive, stage)
            staged.append((stage, destination, component["kind"]))

        for stage, destination, kind in staged:
            rollback: Path | None = None
            if destination.exists():
                rollback = destination.with_name(
                    f".{destination.name}.rollback-{operation_id}"
                )
                destination.rename(rollback)
            stage.rename(destination)
            installed.append((destination, rollback, kind))

        for _destination, rollback, kind in installed:
            if rollback is not None:
                shutil.rmtree(rollback) if kind == "directory" else rollback.unlink()
    except Exception:
        for destination, rollback, kind in reversed(installed):
            if destination.exists():
                shutil.rmtree(destination) if kind == "directory" else destination.unlink()
            if rollback is not None and rollback.exists():
                rollback.rename(destination)
        for stage, _destination, kind in staged:
            if stage.exists():
                shutil.rmtree(stage) if kind == "directory" else stage.unlink()
        raise


def cleanup_candidates(
    paths: LocalPaths,
    retention_days: int,
    *,
    include_artifacts: bool,
    now: datetime | None = None,
) -> list[Path]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    candidates: list[Path] = []

    if paths.backup_root.is_dir():
        for item in paths.backup_root.iterdir():
            modified = datetime.fromtimestamp(item.stat().st_mtime, UTC)
            if (
                item.is_dir()
                and item.name.startswith(BACKUP_PREFIX)
                and modified < cutoff
            ):
                candidates.append(item)

    runtime = paths.project_root / ".runtime"
    current_logs = {
        "backend.out.log",
        "backend.err.log",
        "frontend.out.log",
        "frontend.err.log",
    }
    for directory in (runtime / "logs", runtime / "screenshots"):
        if not directory.is_dir():
            continue
        for item in directory.rglob("*"):
            modified = datetime.fromtimestamp(item.stat().st_mtime, UTC)
            if (
                item.is_file()
                and item.name not in current_logs
                and modified < cutoff
            ):
                candidates.append(item)

    if include_artifacts and paths.database.is_file():
        with closing(sqlite3.connect(paths.database)) as connection:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='execution_jobs'"
            ).fetchone()
            job_ids = (
                {
                    str(row[0])
                    for row in connection.execute("SELECT id FROM execution_jobs")
                }
                if table_exists
                else set()
            )
        for root in {paths.artifact_root, paths.legacy_artifact_root}:
            jobs_root = root / "jobs"
            if not jobs_root.is_dir():
                continue
            for item in jobs_root.iterdir():
                modified = datetime.fromtimestamp(item.stat().st_mtime, UTC)
                if item.is_dir() and item.name not in job_ids and modified < cutoff:
                    candidates.append(item)

    return sorted(set(candidates))


def apply_cleanup(paths: LocalPaths, candidates: list[Path]) -> None:
    allowed_roots = {
        paths.backup_root.resolve(),
        (paths.project_root / ".runtime").resolve(),
        paths.artifact_root.resolve(),
        paths.legacy_artifact_root.resolve(),
    }
    for candidate in candidates:
        resolved = candidate.resolve()
        if not any(
            resolved == root or root in resolved.parents for root in allowed_roots
        ):
            raise ValueError(f"Refusing to clean path outside local data roots: {resolved}")
        if resolved.is_dir():
            shutil.rmtree(resolved)
        elif resolved.exists():
            resolved.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument("--backup-root", type=Path, default=Path(".backups"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("paths")
    subparsers.add_parser("backup")
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("backup", type=Path)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--retention-days", type=int, default=30)
    cleanup.add_argument("--include-artifacts", action="store_true")
    cleanup.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    paths = resolve_local_paths(args.project_root, args.backup_root)
    if args.command == "paths":
        print(
            json.dumps(
                {
                    "database": str(paths.database),
                    "artifact_root": str(paths.artifact_root),
                    "legacy_artifact_root": str(paths.legacy_artifact_root),
                    "runtime_secret": str(paths.runtime_secret),
                    "backup_root": str(paths.backup_root),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "backup":
        print(create_backup(paths))
        return 0
    if args.command == "verify":
        verify_backup(args.backup)
        print(f"Backup verified: {args.backup.resolve()}")
        return 0
    if args.command == "restore":
        restore_backup(paths, args.backup)
        print(f"Backup restored: {args.backup.resolve()}")
        return 0
    if args.retention_days < 1:
        raise ValueError("Retention days must be at least 1")
    candidates = cleanup_candidates(
        paths,
        args.retention_days,
        include_artifacts=args.include_artifacts,
    )
    for candidate in candidates:
        print(candidate)
    if args.apply:
        apply_cleanup(paths, candidates)
        print(f"Removed {len(candidates)} item(s)")
    else:
        print(f"Preview: {len(candidates)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
