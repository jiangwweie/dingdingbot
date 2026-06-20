from __future__ import annotations

import json
import subprocess
import sys

from scripts.build_strategygroup_lifecycle_rehearsal import (
    REQUIRED_SCENARIOS,
    build_lifecycle_rehearsal,
    validate_packet,
)


def test_lifecycle_rehearsal_covers_major_non_live_branches() -> None:
    packet = build_lifecycle_rehearsal()

    assert packet["status"] == "lifecycle_rehearsal_ready"
    assert validate_packet(packet) == []
    assert [row["scenario"] for row in packet["scenario_rows"]] == REQUIRED_SCENARIOS
    assert packet["cost_pnl_review"]["review_shape_ready"] is True


def test_negative_missing_scenario_is_rejected() -> None:
    packet = build_lifecycle_rehearsal()
    packet["scenario_rows"] = packet["scenario_rows"][:-1]

    errors = validate_packet(packet)

    assert "missing_scenario:rough_cost_pnl_review" in errors


def test_negative_exchange_write_is_rejected() -> None:
    packet = build_lifecycle_rehearsal()
    packet["scenario_rows"][0]["exchange_write"] = True

    errors = validate_packet(packet)

    assert "submit_accepted.exchange_write_not_false" in errors


def test_check_mode_passes_against_generated_lifecycle_rehearsal() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_lifecycle_rehearsal.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_lifecycle_rehearsal.py", "--check"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
