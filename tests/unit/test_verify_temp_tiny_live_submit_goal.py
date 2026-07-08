from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_exit_protection_materializer import _submitted_attempt
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_temp_tiny_live_submit_goal.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_temp_tiny_live_submit_goal",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_temp_tiny_live_goal_verifier_passes_entry_sl_tp1_evidence(
    pg_control_connection,
):
    module = _load_module()
    _, prepared = _submitted_attempt(
        pg_control_connection,
        submit_mode="temp_tiny_live_protected_submit",
    )
    protection = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    assert protection["status"] == "position_protected"

    report = module.build_temp_tiny_live_submit_goal_report(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
    )

    assert report["status"] == "temp_tiny_live_submit_goal_verified"
    assert report["goal_verified"] is True
    assert report["blockers"] == []
    assert report["submit_mode"] == "temp_tiny_live_protected_submit"
    assert report["exchange_write_called"] is True
    assert report["order_created"] is True
    assert report["order_lifecycle_called"] is True
    assert report["exit_protection_complete"] is True
    assert {"SL", "TP1"}.issubset(set(report["exit_protection_order_roles"]))
    assert all(value is False for value in report["safety_invariants"].values())


def test_temp_tiny_live_goal_verifier_blocks_without_attempt(pg_control_connection):
    module = _load_module()

    report = module.build_temp_tiny_live_submit_goal_report(
        pg_control_connection,
        protected_submit_attempt_id="missing-attempt",
    )

    assert report["status"] == "blocked"
    assert report["goal_verified"] is False
    assert report["blockers"] == ["temp_tiny_live_submitted_attempt_missing"]
