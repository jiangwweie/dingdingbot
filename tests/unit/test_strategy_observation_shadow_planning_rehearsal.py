from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "verify_strategy_observation_shadow_planning_rehearsal.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_strategy_observation_shadow_planning_rehearsal",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_shadow_planning_rehearsal_uses_real_planner_without_execution():
    module = _load_module()

    report = await module.build_rehearsal_report()

    assert report["status"] == "rehearsal_passed"
    assert report["checks"]["rehearsal_passed"] is True
    assert report["checks"]["shadow_candidate_created_count"] == 1
    assert report["checks"]["signal_evaluation_records"] == 1
    assert report["checks"]["order_candidate_records"] == 1
    assert report["checks"]["forbidden_execution_flags"] == []
    assert all(value is False for value in report["safety_invariants"].values())

    created = [
        item
        for item in report["result"]["candidate_results"]
        if item["shadow_planning_action"] == "shadow_candidate_created"
    ]
    assert len(created) == 1
    assert created[0]["candidate_id"] == "CPM-RO-001"
    assert created[0]["runtime_instance_id"] == "rehearsal-runtime-cpm-long"
    assert created[0]["execution_intent_created"] is False
    assert created[0]["order_created"] is False
    assert created[0]["order_lifecycle_called"] is False
    assert created[0]["exchange_called"] is False
