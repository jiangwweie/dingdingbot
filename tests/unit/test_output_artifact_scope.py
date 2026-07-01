from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_output_artifact_scope.py"
MANIFEST_PATH = REPO_ROOT / "config" / "output_control_snapshots.json"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_output_artifact_scope",
        VALIDATOR_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_output_artifact_manifest_is_valid():
    module = _load_module()

    assert module.validate_manifest(_manifest()) == []


def test_output_artifact_scope_accepts_control_snapshot_pair():
    module = _load_module()
    manifest = _manifest()

    errors = module.validate_changed_output_paths(
        [
            "output/runtime-monitor/latest-daily-live-enablement-table.json",
            "output/runtime-monitor/latest-daily-live-enablement-table.md",
        ],
        manifest,
    )

    assert errors == []


def test_output_artifact_scope_rejects_volatile_public_facts():
    module = _load_module()
    manifest = _manifest()

    errors = module.validate_changed_output_paths(
        ["output/runtime-monitor/latest-binance-usdm-public-facts.json"],
        manifest,
    )

    assert any("volatile output" in error for error in errors)


def test_output_artifact_scope_rejects_unknown_output():
    module = _load_module()
    manifest = _manifest()

    errors = module.validate_changed_output_paths(
        ["output/runtime-monitor/latest-random-summary.json"],
        manifest,
    )

    assert any("not an approved control snapshot" in error for error in errors)


def test_output_artifact_scope_cli_path_round_trip():
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            "--path",
            "output/runtime-monitor/latest-single-lane-task-packet.json",
            "--path",
            "output/runtime-monitor/latest-single-lane-task-packet.md",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
