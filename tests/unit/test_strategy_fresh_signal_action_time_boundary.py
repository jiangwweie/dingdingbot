from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategy_fresh_signal_action_time_boundary.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategy_fresh_signal_action_time_boundary",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _cpm_capture(*, fresh: bool) -> dict:
    return {
        "status": "cpm_runtime_signal_capture_ready",
        "signal_detector_preview": {
            "fresh_signal_present": fresh,
            "current_signal_state": (
                "fresh_signal_present" if fresh else "fresh_signal_absent"
            ),
            "first_blocker_class": (
                "cpm_candidate_authorization_evidence_not_created"
                if fresh
                else "fresh_cpm_long_signal_absent"
            ),
            "first_blocker_owner": "runtime" if fresh else "market",
        },
        "shadow_candidate_shape": {"shadow_candidate_ready": fresh},
    }


def _cpm_rehearsal() -> dict:
    return {"submit_rehearsal_shape_ready": True}


def _cpm_facts() -> dict:
    return {
        "status": "cpm_runtime_signal_facts_ready",
        "watcher_tick_present": True,
        "live_detector": {
            "per_symbol_signal_facts": [
                {
                    "symbol": "ETHUSDT",
                    "fresh_signal_present": True,
                    "candle_input_missing": False,
                    "first_blocker_class": "private_action_time_facts_required",
                    "first_blocker_owner": "runtime",
                },
                {
                    "symbol": "AVAXUSDT",
                    "fresh_signal_present": True,
                    "candle_input_missing": False,
                    "first_blocker_class": "private_action_time_facts_required",
                    "first_blocker_owner": "runtime",
                },
                {
                    "symbol": "SOLUSDT",
                    "fresh_signal_present": False,
                    "candle_input_missing": False,
                    "first_blocker_class": "fresh_cpm_long_signal_absent",
                    "first_blocker_owner": "market",
                },
            ]
        },
    }


def _mpg_readiness() -> dict:
    return {
        "checks": {"public_facts_ready_for_readonly_symbols": True},
        "first_blocker": "fresh_mpg_signal_or_private_action_time_facts",
        "blocker_owner": "market",
    }


def _mpg_readiness_public_gap() -> dict:
    return {
        "checks": {"public_facts_ready_for_readonly_symbols": False},
        "first_blocker": "mpg_high_beta_public_facts_gap",
        "blocker_owner": "runtime",
    }


def _evidence(strategy_group_id: str) -> dict:
    return {
        "strategy_group_id": strategy_group_id,
        "runtime_artifact_ready": True,
        "candidate_evidence_shape_ready": True,
        "fresh_signal_rehearsal_ready": True,
        "next_blocker": "fresh_signal_or_private_action_time_facts",
    }


def _sor_detector(
    *,
    latest_candle: bool = True,
    missing_required_trigger_facts: list[str] | None = None,
) -> dict:
    missing_required_trigger_facts = (
        missing_required_trigger_facts
        if missing_required_trigger_facts is not None
        else ["breakout_level_crossed"]
    )
    return {
        "status": "sor_session_detector_facts_ready",
        "summary": {
            "fresh_session_signal_count": 0,
            "first_blocker": "fresh_sor_session_range_signal_absent",
        },
        "symbol_detector_rows": [
            {
                "symbol": "SOLUSDT",
                "fresh_session_range_signal": False,
                "public_facts_ready": True,
                "latest_candle_close_time_utc": (
                    "2026-06-30T01:59:59+00:00" if latest_candle else None
                ),
                "missing_required_trigger_facts": missing_required_trigger_facts,
            },
            {
                "symbol": "AVAXUSDT",
                "fresh_session_range_signal": False,
                "public_facts_ready": True,
                "latest_candle_close_time_utc": "2026-06-30T01:59:59+00:00",
                "missing_required_trigger_facts": ["breakout_level_crossed"],
            },
        ],
    }


def test_fresh_signal_boundary_stops_before_finalgate_and_orders():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_cpm_capture(fresh=True),
        cpm_rehearsal=_cpm_rehearsal(),
        mpg_readiness=_mpg_readiness(),
        mpg_evidence=_evidence("MPG-001"),
        sor_evidence=_evidence("SOR-001"),
        sor_detector=_sor_detector(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    cpm = artifact["strategy_rows"][0]
    assert cpm["symbol"] == "ETHUSDT"
    assert cpm["fresh_signal_present"] is True
    assert cpm["first_blocker"] == "private_action_time_facts_required"
    assert cpm["action_time_path_ready"] is True
    assert cpm["would_enter_finalgate_if_private_facts_ready"] is True
    assert cpm["post_action_expected_state"] == "action_time_finalgate_boundary_ready"
    checks = artifact["checks"]
    assert checks["calls_finalgate"] is False
    assert checks["calls_operation_layer"] is False
    assert checks["calls_exchange_write"] is False
    assert checks["places_order"] is False
    assert checks["order_created"] is False
    for row in artifact["strategy_rows"]:
        assert row["calls_finalgate"] is False
        assert row["calls_operation_layer"] is False
        assert row["calls_exchange_write"] is False
        assert row["order_created"] is False
        assert row["live_submit_allowed"] is False


def test_absent_signal_keeps_exact_first_blocker():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_cpm_capture(fresh=False),
        cpm_rehearsal=_cpm_rehearsal(),
        mpg_readiness=_mpg_readiness(),
        mpg_evidence=_evidence("MPG-001"),
        sor_evidence=_evidence("SOR-001"),
        sor_detector=_sor_detector(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    cpm = artifact["strategy_rows"][0]
    assert cpm["fresh_signal_present"] is False
    assert cpm["first_blocker"] == "fresh_cpm_long_signal_absent"
    assert cpm["blocker_owner"] == "market"
    assert cpm["next_action"] == "wait_for_fresh_signal_then_refresh_private_action_time_facts"


def test_cpm_boundary_emits_per_symbol_action_time_rows_from_detector_facts():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_cpm_capture(fresh=True),
        cpm_facts=_cpm_facts(),
        cpm_rehearsal=_cpm_rehearsal(),
        mpg_readiness=_mpg_readiness(),
        mpg_evidence=_evidence("MPG-001"),
        sor_evidence=_evidence("SOR-001"),
        sor_detector=_sor_detector(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    cpm_rows = [
        row
        for row in artifact["strategy_rows"]
        if row["strategy_group_id"] == "CPM-RO-001"
    ]
    rows = {row["symbol"]: row for row in cpm_rows}
    assert set(rows) == {"ETHUSDT", "AVAXUSDT", "SOLUSDT"}
    assert rows["AVAXUSDT"]["fresh_signal_present"] is True
    assert rows["AVAXUSDT"]["first_blocker"] == "private_action_time_facts_required"
    assert rows["AVAXUSDT"]["action_time_path_ready"] is True
    assert rows["SOLUSDT"]["fresh_signal_present"] is False
    assert rows["SOLUSDT"]["first_blocker"] == "fresh_cpm_long_signal_absent"


def test_sor_boundary_uses_session_detector_first_blocker():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_cpm_capture(fresh=False),
        cpm_rehearsal=_cpm_rehearsal(),
        mpg_readiness=_mpg_readiness(),
        mpg_evidence=_evidence("MPG-001"),
        sor_evidence=_evidence("SOR-001"),
        sor_detector=_sor_detector(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    sor = next(row for row in artifact["strategy_rows"] if row["strategy_group_id"] == "SOR-001")
    assert sor["symbol"] == "SOLUSDT"
    assert sor["fresh_signal_present"] is False
    assert sor["first_blocker"] == "fresh_sor_session_range_signal_absent"
    assert sor["blocker_owner"] == "market"
    assert sor["action_time_path_ready"] is True


def test_sor_boundary_requires_selected_detector_public_facts_and_candle_tick():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_cpm_capture(fresh=False),
        cpm_rehearsal=_cpm_rehearsal(),
        mpg_readiness=_mpg_readiness(),
        mpg_evidence=_evidence("MPG-001"),
        sor_evidence=_evidence("SOR-001"),
        sor_detector=_sor_detector(
            latest_candle=False,
            missing_required_trigger_facts=[
                "opening_range_available",
                "breakout_level_crossed",
            ],
        ),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    sor = next(row for row in artifact["strategy_rows"] if row["strategy_group_id"] == "SOR-001")
    assert sor["symbol"] == "SOLUSDT"
    assert sor["required_facts_readiness"]["public_facts_ready"] is False
    assert sor["action_time_path_ready"] is False
    assert sor["would_enter_finalgate_if_private_facts_ready"] is False
    assert sor["first_blocker"] == "watcher_tick_missing"
    assert sor["blocker_owner"] == "runtime"
    assert sor["next_action"] == "refresh_or_repair_watcher_public_fact_input"


def test_mpg_boundary_maps_public_facts_gap_to_watcher_tick_missing():
    module = _load_module()

    artifact = module.build_strategy_fresh_signal_action_time_boundary(
        cpm_capture=_cpm_capture(fresh=False),
        cpm_rehearsal=_cpm_rehearsal(),
        mpg_readiness=_mpg_readiness_public_gap(),
        mpg_evidence={
            **_evidence("MPG-001"),
            "runtime_artifact_ready": False,
            "candidate_evidence_shape_ready": False,
            "fresh_signal_rehearsal_ready": False,
        },
        sor_evidence=_evidence("SOR-001"),
        sor_detector=_sor_detector(),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    mpg = next(row for row in artifact["strategy_rows"] if row["strategy_group_id"] == "MPG-001")
    assert mpg["symbol"] == "SOLUSDT"
    assert mpg["required_facts_readiness"]["public_facts_ready"] is False
    assert mpg["action_time_path_ready"] is False
    assert mpg["first_blocker"] == "watcher_tick_missing"
    assert mpg["blocker_owner"] == "runtime"
    assert mpg["next_action"] == "refresh_or_repair_watcher_public_fact_input"
