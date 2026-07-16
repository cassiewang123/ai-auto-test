"""Filesystem isolation for UI test artifacts."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from app.config import get_settings

_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


def get_artifact_root() -> Path:
    settings = get_settings()
    root = Path(settings.ARTIFACT_ROOT)
    if not root.is_absolute():
        root = settings.BASE_DIR / root
    return root.resolve()


def _allowed_roots() -> tuple[Path, ...]:
    return (
        get_artifact_root(),
        (Path(tempfile.gettempdir()) / "airetest").resolve(),
    )


# Backward-compatible export used by older integrations.
ALLOWED_UPLOAD_DIRS = [str(path) for path in _allowed_roots()]


def _resolve_inside(candidate: Path, root: Path) -> Path:
    root = root.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("文件路径超出允许的产物目录") from exc
    return resolved


def _resolve_direct_path(file_path: str) -> Path:
    settings = get_settings()
    if not settings.ALLOW_DIRECT_FILE_PATHS:
        raise ValueError("直接文件路径已禁用，请使用 artifact_id")
    if not file_path or "\x00" in file_path:
        raise ValueError("文件路径无效")

    raw = Path(file_path)
    if not raw.is_absolute():
        return _resolve_inside(get_artifact_root() / raw, get_artifact_root())

    for root in _allowed_roots():
        try:
            return _resolve_inside(raw, root)
        except ValueError:
            continue
    raise ValueError("绝对路径不在允许的产物目录内")


def validate_file_path(file_path: str, *, for_write: bool = False) -> bool:
    """Return whether a direct path is allowed and usable."""
    try:
        path = _resolve_direct_path(file_path)
        if for_write:
            _resolve_inside(path.parent, next(
                root for root in _allowed_roots()
                if path == root or root in path.parents
            ))
            return not path.exists() or path.is_file()
        return path.is_file()
    except (OSError, ValueError, StopIteration):
        return False


def resolve_artifact_path(
    artifact_id: str | None,
    file_path: str | None,
    *,
    for_write: bool = False,
) -> str:
    """Resolve a read/write path while keeping it inside an allowed root."""
    if artifact_id:
        if not _ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise ValueError("artifact_id 格式不合法")
        root = get_artifact_root()
        path = _resolve_inside(root / artifact_id, root)
    elif file_path:
        path = _resolve_direct_path(file_path)
    else:
        raise ValueError("必须提供 artifact_id 或 file_path")

    if for_write:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not path.is_file():
            raise ValueError("产物保存路径不是文件")
    elif not path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact_id or file_path}")

    return str(path)
