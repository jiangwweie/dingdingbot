from __future__ import annotations

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path

from scripts.build_strategygroup_handoff_boundary_closure import (
    REQUIRED_EXPLICIT_MISSING_GROUPS,
    build_handoff_boundary_closure,
    validate_packet,
)


QUALITY_WAVE_PATH = Path(
    "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)


def _quality_wave() -> dict:
    return json.loads(QUALITY_WAVE_PATH.read_text(encoding="utf-8"))


def test_handoff_boundary_closure_records_vcb_lsr_brf_explicit_boundaries() -> None:
    packet = build_handoff_boundary_closure(_quality_wave())

    rows = {row["strategy_group_id"]: row for row in packet["rows"]}
    assert packet["status"] == "handoff_boundary_closure_ready"
    assert validate_packet(packet) == []
    for group in REQUIRED_EXPLICIT_MISSING_GROUPS:
        assert rows[group]["boundary_state"] == "explicit_missing_handoff_boundary_accepted"
        assert rows[group]["handoff_pack_present"] is False
        assert rows[group]["actionable_now"] is False
        assert rows[group]["real_order_authority"] is False


def test_negative_missing_required_boundary_is_rejected() -> None:
    packet = build_handoff_boundary_closure(_quality_wave())
    packet["rows"] = [
        row for row in packet["rows"] if row["strategy_group_id"] != "VCB-001"
    ]

    errors = validate_packet(packet)

    assert "VCB-001.missing_boundary_row" in errors


def test_negative_actionable_now_true_is_rejected() -> None:
    packet = build_handoff_boundary_closure(_quality_wave())
    row = next(row for row in packet["rows"] if row["strategy_group_id"] == "LSR-001")
    row["actionable_now"] = True

    errors = validate_packet(packet)

    assert "LSR-001.actionable_now_true" in errors


def test_source_rows_follow_quality_wave_boundary_state() -> None:
    quality_wave = deepcopy(_quality_wave())
    for row in quality_wave["rows"]:
        if row["strategy_group_id"] == "BRF-001":
            row["source_coverage"]["handoff_pack"] = True

    packet = build_handoff_boundary_closure(quality_wave)

    errors = validate_packet(packet)
    assert "BRF-001.handoff_pack_unexpectedly_present" in errors


def test_check_mode_passes_against_generated_file() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_strategygroup_handoff_boundary_closure.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "scripts/build_strategygroup_handoff_boundary_closure.py",
            "--check",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert check.returncode == 0, check.stdout + check.stderr
    assert json.loads(check.stdout)["status"] == "passed"
