import json
import subprocess
import sys

import pytest

from scripts.verify_runtime_ready_shadow_candidate_boundary import (
    build_boundary_report,
)


@pytest.mark.asyncio
async def test_ready_shadow_candidate_boundary_report_covers_pass_and_block_paths():
    report = await build_boundary_report()

    assert report["status"] == "rtf047_ready_shadow_candidate_boundary_passed"
    assert report["scenario_count"] == 5
    assert report["safety_summary"] == {
        "local_in_memory_only": True,
        "database_connected": False,
        "http_network_called": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
    }

    scenarios = {item["scenario_id"]: item for item in report["scenarios"]}
    assert set(scenarios) == {
        "cpm-long-eth",
        "brf-short-btc",
        "cpm-short-mismatch",
        "rmr-classifier-no-trade",
        "fco-data-backlog-no-trade",
    }

    for scenario_id in ("cpm-long-eth", "brf-short-btc"):
        item = scenarios[scenario_id]
        assert item["status"] == "passed"
        assert item["planning_status"] == "shadow_candidate_created"
        checks = item["checks"]
        assert checks["entry_present"] is True
        assert checks["stop_present"] is True
        assert checks["protection_required"] is True
        assert checks["tp1_partial_present"] is True
        assert checks["runner_present"] is True
        assert checks["notional_present"] is True
        assert checks["quantity_present"] is True
        assert checks["max_loss_present"] is True
        assert checks["leverage_present"] is True
        assert checks["margin_present"] is True
        assert checks["liquidation_reference_present"] is True
        assert checks["liquidation_stop_buffer_present"] is True
        assert item["safety_invariants"]["execution_intent_created"] is False
        assert item["safety_invariants"]["order_created"] is False
        assert item["safety_invariants"]["order_lifecycle_called"] is False
        assert item["safety_invariants"]["exchange_called"] is False

    assert scenarios["cpm-long-eth"]["side"] == "long"
    assert scenarios["cpm-long-eth"]["symbol"] == "ETH/USDT:USDT"
    assert scenarios["brf-short-btc"]["side"] == "short"
    assert scenarios["brf-short-btc"]["symbol"] == "BTC/USDT:USDT"

    for scenario_id in (
        "cpm-short-mismatch",
        "rmr-classifier-no-trade",
        "fco-data-backlog-no-trade",
    ):
        item = scenarios[scenario_id]
        assert item["status"] == "passed"
        assert item["planning_status"] != "shadow_candidate_created"
        checks = item["checks"]
        assert checks["candidate_not_created"] is True
        assert checks["proposal_not_created"] is True
        assert checks["order_candidate_not_created"] is True
        assert checks["execution_intent_not_created"] is True
        assert checks["order_lifecycle_not_called"] is True
        assert checks["exchange_not_called"] is True


def test_ready_shadow_candidate_boundary_script_writes_json(tmp_path):
    output_path = tmp_path / "rtf047-ready-shadow-candidate-boundary.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_runtime_ready_shadow_candidate_boundary.py",
            "--output-json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "rtf047_ready_shadow_candidate_boundary_passed"
    assert file_payload["status"] == stdout_payload["status"]
    assert file_payload["scenario_count"] == 5
