from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.atomic_switch_release_pointer import switch_release_pointer


def _release(path: Path, sha: str) -> Path:
    path.mkdir()
    (path / ".brc-release-manifest.json").write_text(
        json.dumps({"git_deploy": {"target_commit": sha}}),
        encoding="utf-8",
    )
    return path


def test_switch_replaces_symlink_and_rereads_exact_sha(tmp_path):
    old = _release(tmp_path / "old", "b" * 40)
    new = _release(tmp_path / "new", "a" * 40)
    app = tmp_path / "app"
    app.mkdir()
    current = app / "current"
    current.symlink_to(old)

    result = switch_release_pointer(current, new, expected_sha="a" * 40)

    assert result["status"] == "release_pointer_switched"
    assert current.resolve() == new.resolve()
    assert result["target_runtime_head"] == "a" * 40
    assert result["parent_fsynced"] is True


def test_switch_rejects_manifest_mismatch_without_changing_pointer(tmp_path):
    old = _release(tmp_path / "old", "b" * 40)
    new = _release(tmp_path / "new", "c" * 40)
    app = tmp_path / "app"
    app.mkdir()
    current = app / "current"
    current.symlink_to(old)

    with pytest.raises(ValueError, match="release_manifest_sha_mismatch"):
        switch_release_pointer(current, new, expected_sha="a" * 40)

    assert current.resolve() == old.resolve()
