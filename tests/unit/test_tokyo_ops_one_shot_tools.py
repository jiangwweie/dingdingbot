from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _touch(path: Path, *, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(path.name, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_report_cleanup_dry_run_protects_latest_and_only_targets_allowlist(tmp_path: Path):
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "cleanup_tokyo_runtime_reports_once.py",
        "cleanup_tokyo_runtime_reports_once",
    )
    root = tmp_path / "reports"
    target = root / "runtime-signal-watcher"
    now = 1_800_000_000
    _touch(target / "latest-strategy-live-candidate-pool.json", mtime=now - 10_000)
    _touch(target / "dry-run-audit-chain" / "old.json", mtime=now - 80 * 3600)
    _touch(target / "replay-debug-old.json", mtime=now - 80 * 3600)
    _touch(target / "ordinary-old.json", mtime=now - 80 * 3600)
    _touch(target / "dry-run-audit-chain" / "fresh.json", mtime=now - 3600)

    manifest = module.build_manifest(
        root=root,
        target=target,
        keep_hours=72,
        now=now,
        archive_recent=False,
        apply=False,
    )

    candidates = {row["relative_path"] for row in manifest["delete_candidates"]}
    protected = {row["relative_path"] for row in manifest["protected_entries"]}
    assert candidates == {
        "runtime-signal-watcher/dry-run-audit-chain/old.json",
        "runtime-signal-watcher/replay-debug-old.json",
    }
    assert "runtime-signal-watcher/latest-strategy-live-candidate-pool.json" in protected
    assert "runtime-signal-watcher/dry-run-audit-chain/fresh.json" in protected
    assert manifest["checks"]["no_pg_runtime_truth_write"] is True


def test_report_cleanup_apply_deletes_candidates_and_keeps_latest(tmp_path: Path):
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "cleanup_tokyo_runtime_reports_once.py",
        "cleanup_tokyo_runtime_reports_once_apply",
    )
    root = tmp_path / "reports"
    target = root / "runtime-signal-watcher"
    now = 1_800_000_000
    latest = target / "latest-strategy-live-candidate-pool.json"
    old = target / "dry-run-audit-chain" / "old.json"
    _touch(latest, mtime=now - 80 * 3600)
    _touch(old, mtime=now - 80 * 3600)

    manifest = module.build_manifest(
        root=root,
        target=target,
        keep_hours=72,
        now=now,
        archive_recent=True,
        apply=True,
    )
    module.apply_cleanup(manifest, root=root, archive_recent=True)

    assert manifest["status"] == "applied"
    assert not old.exists()
    assert latest.exists()
    assert Path(manifest["archive_path"]).exists()


def test_release_prune_keeps_current_previous_and_recent(tmp_path: Path):
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "prune_tokyo_releases_once.py",
        "prune_tokyo_releases_once",
    )
    root = tmp_path / "releases"
    app = tmp_path / "app"
    app.mkdir()
    releases = []
    for idx in range(7):
        path = root / f"brc-runtime-governance-{idx}"
        path.mkdir(parents=True)
        os.utime(path, (1_800_000_000 + idx, 1_800_000_000 + idx))
        releases.append(path)
    current_link = app / "current"
    current_link.symlink_to(releases[4])

    manifest = module.build_manifest(
        root=root,
        current_symlink=current_link,
        keep_count=3,
        apply=False,
    )

    candidates = {row["relative_path"] for row in manifest["delete_candidates"]}
    protected = {row["relative_path"] for row in manifest["protected_entries"]}
    assert "brc-runtime-governance-4" in protected
    assert "brc-runtime-governance-3" in protected
    assert candidates == {
        "brc-runtime-governance-0",
        "brc-runtime-governance-1",
        "brc-runtime-governance-2",
    }


def test_backup_prune_keeps_only_latest_backup(tmp_path: Path):
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "prune_tokyo_backups_latest_only.py",
        "prune_tokyo_backups_latest_only",
    )
    root = tmp_path / "backups"
    root.mkdir()
    for idx in range(3):
        path = root / f"backup-{idx}.pgdump"
        path.write_text("backup", encoding="utf-8")
        os.utime(path, (1_800_000_000 + idx, 1_800_000_000 + idx))

    manifest = module.build_manifest(root=root, apply=True)
    module.apply_prune(manifest, root=root)

    assert manifest["status"] == "applied"
    assert {path.name for path in root.iterdir()} == {"backup-2.pgdump"}
    assert manifest["checks"]["no_new_backup_created"] is True


def test_ops_health_defaults_to_plan_only():
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "check_tokyo_runtime_ops_health_once.py",
        "check_tokyo_runtime_ops_health_once",
    )

    payload = module.build_payload(execute_local=False)

    assert payload["status"] == "ok"
    assert payload["mode"] == "plan_only"
    assert all(row["status"] == "planned" for row in payload["results"])
    assert payload["checks"]["readonly_commands_only"] is True


def test_ops_health_wraps_du_with_timeout_and_low_priority():
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "check_tokyo_runtime_ops_health_once.py",
        "check_tokyo_runtime_ops_health_once_priority",
    )

    payload = module.build_payload(execute_local=False)
    du_rows = [
        row
        for row in payload["results"]
        if row["name"] in {"reports_du", "releases_du", "backups_du"}
    ]

    assert du_rows
    for row in du_rows:
        command = row["command"]
        assert command[:7] == ["timeout", "3s", "ionice", "-c3", "nice", "-n", "19"]
        assert "du" in command


def test_report_cleanup_apply_honors_delete_budget(tmp_path: Path):
    module = _load(
        REPO_ROOT / "scripts" / "ops" / "cleanup_tokyo_runtime_reports_once.py",
        "cleanup_tokyo_runtime_reports_once_budget",
    )
    root = tmp_path / "reports"
    target = root / "runtime-signal-watcher"
    now = 1_800_000_000
    old_files = [
        target / "dry-run-audit-chain" / f"old-{idx}.json"
        for idx in range(3)
    ]
    for path in old_files:
        _touch(path, mtime=now - 80 * 3600)

    manifest = module.build_manifest(
        root=root,
        target=target,
        keep_hours=72,
        now=now,
        archive_recent=False,
        apply=True,
        max_delete_count=2,
    )
    module.apply_cleanup(
        manifest,
        root=root,
        archive_recent=False,
        max_delete_count=2,
    )

    assert manifest["status"] == "applied"
    assert manifest["deleted_count"] == 2
    assert "delete_budget_exhausted" in manifest["checks"]["warnings"]
    assert sum(path.exists() for path in old_files) == 1
