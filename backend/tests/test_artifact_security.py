"""Artifact path isolation tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.services.ui.artifact_service import (
    resolve_artifact_path,
    validate_file_path,
)


@pytest.fixture
def artifact_settings(tmp_path):
    settings = get_settings()
    old_root = settings.ARTIFACT_ROOT
    old_direct = settings.ALLOW_DIRECT_FILE_PATHS
    settings.ARTIFACT_ROOT = tmp_path / "artifacts"
    settings.ALLOW_DIRECT_FILE_PATHS = False
    try:
        yield settings
    finally:
        settings.ARTIFACT_ROOT = old_root
        settings.ALLOW_DIRECT_FILE_PATHS = old_direct


def test_artifact_id_cannot_traverse(artifact_settings):
    with pytest.raises(ValueError):
        resolve_artifact_path("../secret.txt", None)
    with pytest.raises(ValueError):
        resolve_artifact_path("nested/secret.txt", None)


def test_artifact_read_and_write_stay_under_root(artifact_settings):
    write_path = Path(
        resolve_artifact_path("report.json", None, for_write=True)
    )
    assert write_path.parent == artifact_settings.ARTIFACT_ROOT.resolve()
    write_path.write_text("{}", encoding="utf-8")
    assert resolve_artifact_path("report.json", None) == str(write_path)


def test_direct_paths_are_disabled_by_default(artifact_settings, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    assert not validate_file_path(str(outside))
    with pytest.raises(ValueError):
        resolve_artifact_path(None, str(outside))


def test_enabled_relative_path_is_rooted(artifact_settings):
    artifact_settings.ALLOW_DIRECT_FILE_PATHS = True
    path = Path(
        resolve_artifact_path(None, "downloads/result.txt", for_write=True)
    )
    assert artifact_settings.ARTIFACT_ROOT.resolve() in path.parents
    assert path.name == "result.txt"
