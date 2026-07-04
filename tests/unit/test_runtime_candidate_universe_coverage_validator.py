from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_runtime_candidate_universe_coverage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_runtime_candidate_universe_coverage",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _complete_artifact() -> dict:
    rows = [
        _coverage_row("CPM-RO-001", "ETHUSDT", "long"),
        _coverage_row("SOR-001", "ETHUSDT", "short"),
    ]
    return {
        "status": "waiting_for_signal",
        "candidate_universe_coverage": {
            "status": "complete",
            "expected_row_count": len(rows),
            "active_matched_row_count": len(rows),
            "missing_row_count": 0,
            "rows": rows,
        },
    }


def _coverage_row(strategy_group_id: str, symbol: str, side: str) -> dict:
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "state": "active_watcher_scope",
        "blocker_class": "none",
        "active_runtime_instance_ids": [f"runtime-{strategy_group_id}-{symbol}-{side}"],
        "selected_runtime_instance_ids": [
            f"runtime-{strategy_group_id}-{symbol}-{side}"
        ],
        "authority_boundary": (
            "candidate_universe_coverage_is_read_only; "
            "no_finalgate_no_operation_layer_no_exchange_write"
        ),
    }


def test_runtime_candidate_universe_coverage_accepts_complete_scope():
    module = _load_module()

    assert module.validate_runtime_candidate_universe_coverage(_complete_artifact()) == []


def test_runtime_candidate_universe_coverage_rejects_missing_coverage():
    module = _load_module()

    errors = module.validate_runtime_candidate_universe_coverage(
        {"status": "waiting_for_signal"}
    )

    assert errors == ["candidate_universe_coverage is required"]


def test_runtime_candidate_universe_coverage_rejects_incomplete_scope():
    module = _load_module()
    artifact = _complete_artifact()
    coverage = artifact["candidate_universe_coverage"]
    expected_count = coverage["expected_row_count"]
    coverage["status"] = "incomplete"
    coverage["active_matched_row_count"] = expected_count - 1
    coverage["missing_row_count"] = 1
    coverage["rows"][0]["selected_runtime_instance_ids"] = []

    errors = module.validate_runtime_candidate_universe_coverage(artifact)

    assert "candidate_universe_coverage.status must be complete" in errors
    assert (
        f"candidate_universe_coverage.active_matched_row_count must be {expected_count}"
        in errors
    )
    assert "candidate_universe_coverage.missing_row_count must be 0" in errors
    assert any("selected_runtime_instance_ids must be non-empty" in error for error in errors)


def test_runtime_candidate_universe_coverage_cli_blocks_before_refresh(tmp_path: Path):
    artifact_path = tmp_path / "latest-status.json"
    artifact_path.write_text(json.dumps({"status": "waiting_for_signal"}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(artifact_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "candidate_universe_coverage is required" in result.stderr
    assert "runtime_candidate_universe_coverage_invalid" in result.stdout
