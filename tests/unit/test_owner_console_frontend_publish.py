from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISH_SCRIPT_PATH = REPO_ROOT / "scripts" / "publish_owner_console_frontend.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "publish_owner_console_frontend",
        PUBLISH_SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module._git = lambda repo_root, *args: (
        "codex/owner-runtime-console-v1"
        if args == ("rev-parse", "--abbrev-ref", "HEAD")
        else "f" * 40
    )
    return module


def _dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>")
    (dist / "assets" / "app.js").write_text("console.log('ok')")
    return dist


def test_owner_console_frontend_publish_dry_run_does_not_execute_remote_command(
    tmp_path: Path,
):
    module = _load_module()
    calls = []
    dist = _dist_dir(tmp_path)

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.publish_owner_console_frontend(
        repo_root=REPO_ROOT,
        dist_dir=dist,
        host="tokyo",
        frontend_root="/var/www/brc-owner-console",
        apply=False,
        runner=runner,
    )

    assert report["status"] == "dry_run_ready"
    assert calls == []
    assert report["interaction"]["level"] == "L1_publish_plan_only"
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["effects"]["frontend_static_site_published"] is False
    assert report["effects"]["exchange_write_called"] is False


def test_owner_console_frontend_publish_apply_streams_one_remote_command(
    tmp_path: Path,
):
    module = _load_module()
    calls = []
    dist = _dist_dir(tmp_path)

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "published", "", 0)

    report = module.publish_owner_console_frontend(
        repo_root=REPO_ROOT,
        dist_dir=dist,
        host="tokyo",
        frontend_root="/var/www/brc-owner-console",
        apply=True,
        runner=runner,
    )

    assert report["status"] == "applied"
    assert len(calls) == 1
    assert "tar -czf - ." in calls[0]
    assert "ssh tokyo" in calls[0]
    assert "/var/www/brc-owner-console" in calls[0]
    assert report["interaction"]["level"] == "L3_frontend_static_publish"
    assert report["interaction"]["mutates_remote_files"] is True
    assert report["interaction"]["approaches_real_order"] is False
    assert report["effects"]["frontend_static_site_published"] is True
    assert report["effects"]["frontend_release_marker_written"] is True
    assert report["effects"]["backend_service_restarted"] is False
    assert report["effects"]["order_created"] is False
    assert report["effects"]["exchange_write_called"] is False


def test_owner_console_frontend_publish_blocks_when_dist_index_missing(
    tmp_path: Path,
):
    module = _load_module()
    dist = tmp_path / "dist"
    dist.mkdir()

    report = module.publish_owner_console_frontend(
        repo_root=REPO_ROOT,
        dist_dir=dist,
        host="tokyo",
        frontend_root="/var/www/brc-owner-console",
        apply=True,
        runner=lambda command: module.ShellResult(command, "published", "", 0),
    )

    assert report["status"] == "blocked"
    assert "owner_console_dist_index_missing" in report["checks"]["blockers"]
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["effects"]["frontend_static_site_published"] is False
