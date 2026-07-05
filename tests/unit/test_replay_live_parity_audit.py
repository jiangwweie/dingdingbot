from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_replay_live_parity_audit.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_replay_live_parity_audit",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _event(symbol: str, *, boundary: bool = True) -> dict:
    return {
        "strategy_group_id": "MPG-001",
        "symbol": symbol,
        "event_time_utc": "2026-06-27T00:00:00+00:00",
        "fresh_like_signal_seen": True,
        "counterfactual_fresh_signal_present": True,
        "gate_breakdown": {
            "required_facts_replay_shape_present": True,
            "would_reach_action_time_boundary": boundary,
        },
    }


def _sor_event(symbol: str, *, boundary: bool = True) -> dict:
    event = _event(symbol, boundary=boundary)
    event["strategy_group_id"] = "SOR-001"
    return event


def _cpm_event(symbol: str, *, replay_required_facts: list[str] | None = None) -> dict:
    event = _event(symbol)
    event["strategy_group_id"] = "CPM-RO-001"
    event["gate_breakdown"]["would_reach_action_time_boundary"] = True
    if replay_required_facts is not None:
        event["gate_breakdown"]["replay_required_facts"] = replay_required_facts
    return event


def _replay() -> dict:
    return {
        "strategy_rows": [
            {
                "strategy_group_id": "MPG-001",
                "path_id": "MPG-LONG",
                "window_results": [
                    {"window_days": 3, "counterfactual_events": [_event("ETHUSDT")]},
                    {
                        "window_days": 7,
                        "counterfactual_events": [_event("SOLUSDT")],
                    },
                    {
                        "window_days": 14,
                        "counterfactual_events": [_event("OPUSDT")],
                    },
                ],
            }
        ]
    }


def _cpm_replay(*events: dict) -> dict:
    return {
        "strategy_rows": [
            {
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "window_results": [
                    {
                        "window_days": 3,
                        "counterfactual_events": list(events),
                    }
                ],
            }
        ]
    }


def _mpg_watcher() -> dict:
    return {
        "status": "mpg_expanded_watcher_facts_ready",
        "watcher_scope": {
            "symbol_scope": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "primary_live_submit_symbol_scope": ["BTCUSDT", "ETHUSDT"],
            "expanded_readonly_watcher_symbols": ["SOLUSDT"],
            "source": "binance_usdm_public_facts_readonly",
        },
    }


def _mpg_watcher_with_op_scope_proposal() -> dict:
    watcher = _mpg_watcher()
    watcher["watcher_scope"]["scoped_live_observation_proposal_symbols"] = [
        "OPUSDT"
    ]
    watcher["symbol_public_fact_rows"] = [
        {
            "symbol": "OPUSDT",
            "scope_decision": "defer_primary_or_readonly_scope",
            "public_facts_ready": False,
            "strategy_fit": True,
            "liquidity": {
                "spread_ok": False,
                "min_notional_ok": False,
                "qty_step_ok": False,
            },
            "funding": {"funding_not_extreme": False},
            "rejection_reasons": [
                "binance_usdm_public_facts_missing_or_stale",
                "funding_not_extreme",
                "spread_ok",
                "min_notional_ok",
                "qty_step_ok",
            ],
        }
    ]
    return watcher


def _sor_evidence() -> dict:
    return {
        "status": "runtime_activation_evidence_ready",
        "runtime_artifact_ready": True,
        "candidate_evidence_shape_ready": True,
        "fresh_signal_rehearsal_ready": True,
        "watcher_scope": {
            "symbol_scope": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
            "primary_live_submit_symbol_scope": ["BTCUSDT", "ETHUSDT"],
            "expanded_readonly_watcher_symbols": ["SOLUSDT", "AVAXUSDT"],
            "source": "binance_usdm_public_facts_readonly",
        },
    }


def _sor_public_facts_unavailable_evidence() -> dict:
    evidence = _sor_evidence()
    evidence["status"] = "runtime_activation_evidence_public_facts_unavailable"
    evidence["runtime_artifact_ready"] = False
    evidence["candidate_evidence_shape_ready"] = False
    evidence["fresh_signal_rehearsal_ready"] = False
    return evidence


def _sor_detector_row(
    symbol: str,
    *,
    latest_candle: bool = True,
    fresh: bool = False,
    failed: list[str] | None = None,
) -> dict:
    failed = failed if failed is not None else ([] if fresh else ["breakout_level_crossed"])
    return {
        "symbol": symbol,
        "timeframe": "15m_closed",
        "public_facts_ready": True,
        "latest_candle_close_time_utc": (
            "2026-06-30T01:59:59+00:00" if latest_candle else None
        ),
        "fresh_session_range_signal": fresh,
        "missing_required_trigger_facts": failed,
    }


def _sor_detector(*rows: dict) -> dict:
    return {
        "status": "sor_session_detector_facts_ready",
        "detector_source_mode": "binance_usdm_public_closed_candles",
        "symbol_detector_rows": list(rows),
        "summary": {
            "fresh_session_signal_count": sum(
                1 for row in rows if row.get("fresh_session_range_signal") is True
            ),
            "first_blocker": "fresh_sor_session_range_signal_absent",
        },
    }


def _trigger_facts(*failed: str) -> dict:
    fact_names = [
        "funding_not_extreme",
        "htf_trend_intact",
        "invalidated_below_level",
        "liquidity_ok",
        "pullback_depth_normal",
        "reclaim_confirmed",
    ]
    return {
        fact_name: {
            "fresh": True,
            "status": "not_satisfied" if fact_name in failed else "satisfied",
            "value": fact_name not in failed,
        }
        for fact_name in fact_names
    }


def _cpm_symbol_row(symbol: str, failed: list[str]) -> dict:
    return {
        "symbol": symbol,
        "timeframe": "15m_closed",
        "candle_input_missing": False,
        "fresh_signal_present": False,
        "missing_required_trigger_facts": failed,
        "trigger_facts": _trigger_facts(*failed),
    }


def _cpm_ready_facts() -> dict:
    return {
        "status": "cpm_runtime_signal_facts_ready",
        "detector_source_mode": "binance_usdm_public_closed_candles",
        "watcher_tick_present": True,
        "fact_input_present": True,
        "watcher_scope": {
            "symbol_scope": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            "primary_live_submit_symbol_scope": ["ETHUSDT"],
            "expanded_readonly_symbol_scope": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
        },
        "live_detector": {
            "per_symbol_signal_facts": [
                _cpm_symbol_row(
                    "ETHUSDT", ["htf_trend_intact", "reclaim_confirmed"]
                ),
                _cpm_symbol_row("SOLUSDT", ["reclaim_confirmed"]),
                _cpm_symbol_row(
                    "AVAXUSDT", ["htf_trend_intact", "reclaim_confirmed"]
                ),
                _cpm_symbol_row(
                    "SUIUSDT", ["htf_trend_intact", "reclaim_confirmed"]
                ),
            ]
        },
    }


def test_replay_live_parity_counts_windows_and_symbol_mismatches():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay=_replay(),
        cpm_facts={},
        mpg_watcher=_mpg_watcher(),
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    row = artifact["strategy_rows"][0]
    assert [window["window_days"] for window in row["window_results"]] == [3, 7, 14]
    assert row["replay_signal_count"] == 3
    assert row["live_detector_reproduced_count"] == 2
    assert row["mismatch_count"] == 1
    assert artifact["summary"]["mismatch_count"] == 1
    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["symbol"] == "OPUSDT"
    assert symbol_row["blocker_class"] == "scope_not_attached"
    assert symbol_row["mismatch_reasons"] == ["scope_not_attached"]


def test_replay_live_parity_reclassifies_mpg_scope_proposal_without_public_tick():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay=_replay(),
        cpm_facts={},
        mpg_watcher=_mpg_watcher_with_op_scope_proposal(),
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    by_symbol = {
        item["symbol"]: item for item in artifact["per_symbol_mismatch_table"]
    }
    op_row = by_symbol["OPUSDT"]

    assert op_row["blocker_class"] == "scope_not_attached"
    assert op_row["watcher_tick_present"] is False
    assert op_row["computed"] is True
    assert "binance_usdm_public_facts_missing_or_stale" in op_row["failed_facts"]
    assert op_row["next_action"] == "produce_scoped_live_observation_or_scope_proposal"


def test_replay_live_parity_reclassifies_sor_missing_candles_as_watcher_tick_missing():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay={
            "strategy_rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "path_id": "SOR-SESSION-BREAKOUT",
                    "window_results": [
                        {
                            "window_days": 3,
                            "counterfactual_events": [_sor_event("SOLUSDT")],
                        }
                    ],
                }
            ]
        },
        cpm_facts={},
        mpg_watcher={},
        sor_evidence=_sor_evidence(),
        sor_detector=_sor_detector(
            _sor_detector_row(
                "SOLUSDT",
                latest_candle=False,
                failed=[
                    "opening_range_available",
                    "breakout_level_crossed",
                ],
            )
        ),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["strategy_group_id"] == "SOR-001"
    assert symbol_row["symbol"] == "SOLUSDT"
    assert symbol_row["blocker_class"] == "watcher_tick_missing"
    assert symbol_row["detector_attached"] is True
    assert symbol_row["watcher_tick_present"] is False
    assert symbol_row["computed"] is False
    assert symbol_row["next_action"] == "refresh_or_repair_watcher_public_fact_input"


def test_replay_live_parity_keeps_sor_detector_attached_when_public_facts_unavailable():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay={
            "strategy_rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "path_id": "SOR-SESSION-BREAKOUT",
                    "window_results": [
                        {
                            "window_days": 3,
                            "counterfactual_events": [_sor_event("SOLUSDT")],
                        }
                    ],
                }
            ]
        },
        cpm_facts={},
        mpg_watcher={},
        sor_evidence=_sor_public_facts_unavailable_evidence(),
        sor_detector=_sor_detector(
            _sor_detector_row(
                "SOLUSDT",
                latest_candle=False,
                failed=[
                    "public_facts_ready",
                    "opening_range_available",
                    "breakout_level_crossed",
                ],
            )
        ),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["strategy_group_id"] == "SOR-001"
    assert symbol_row["symbol"] == "SOLUSDT"
    assert symbol_row["blocker_class"] == "watcher_tick_missing"
    assert symbol_row["detector_attached"] is True
    assert symbol_row["watcher_tick_present"] is False
    assert symbol_row["computed"] is False


def test_replay_live_parity_reclassifies_sor_false_session_facts_as_computed_not_satisfied():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay={
            "strategy_rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "path_id": "SOR-SESSION-BREAKOUT",
                    "window_results": [
                        {
                            "window_days": 3,
                            "counterfactual_events": [_sor_event("SOLUSDT")],
                        }
                    ],
                }
            ]
        },
        cpm_facts={},
        mpg_watcher={},
        sor_evidence=_sor_evidence(),
        sor_detector=_sor_detector(
            _sor_detector_row(
                "SOLUSDT",
                failed=[
                    "breakout_level_crossed",
                    "follow_through_confirmed",
                ],
            )
        ),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["blocker_class"] == "computed_not_satisfied"
    assert symbol_row["detector_attached"] is True
    assert symbol_row["watcher_tick_present"] is True
    assert symbol_row["computed"] is True
    assert symbol_row["failed_facts"] == [
        "breakout_level_crossed",
        "follow_through_confirmed",
    ]


def test_replay_live_parity_requires_sor_per_symbol_detector_facts():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay={
            "strategy_rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "path_id": "SOR-SESSION-BREAKOUT",
                    "window_results": [
                        {
                            "window_days": 3,
                            "counterfactual_events": [_sor_event("AVAXUSDT")],
                        }
                    ],
                }
            ]
        },
        cpm_facts={},
        mpg_watcher={},
        sor_evidence=_sor_evidence(),
        sor_detector=_sor_detector(_sor_detector_row("SOLUSDT", fresh=True)),
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    row = artifact["strategy_rows"][0]
    assert row["live_detector_reproduced_count"] == 0
    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["symbol"] == "AVAXUSDT"
    assert symbol_row["blocker_class"] == "artifact_missing"


def test_replay_live_parity_never_marks_unreproduced_signal_as_market_wait():
    module = _load_module()
    replay = _replay()
    replay["strategy_rows"][0]["window_results"][0]["counterfactual_events"] = [
        _event("ETHUSDT", boundary=False)
    ]

    artifact = module.build_replay_live_parity_audit(
        replay=replay,
        cpm_facts={},
        mpg_watcher=_mpg_watcher(),
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    reasons = {
        mismatch["mismatch_reason"]
        for row in artifact["strategy_rows"]
        for mismatch in row["mismatch_table"]
    }
    assert "market_wait" not in " ".join(reasons)
    assert "action_time_boundary_not_reproduced" in reasons
    checks = artifact["checks"]
    assert checks["replay_treated_as_live_signal"] is False
    assert checks["finalgate_called"] is False
    assert checks["operation_layer_called"] is False
    assert checks["exchange_write_called"] is False
    assert checks["order_created"] is False


def test_cpm_ready_facts_classify_current_false_facts_as_computed_not_satisfied():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay=_cpm_replay(
            _cpm_event("ETHUSDT"),
            _cpm_event("SOLUSDT"),
            _cpm_event("AVAXUSDT"),
            _cpm_event("SUIUSDT"),
        ),
        cpm_facts=_cpm_ready_facts(),
        mpg_watcher={},
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    row = artifact["strategy_rows"][0]
    assert row["coverage"]["detector_attached"] is True
    assert row["coverage"]["watcher_tick_present"] is True
    assert row["coverage"]["computed"] is True
    assert row["coverage"]["detector_or_watcher_ready"] is True

    by_symbol = {
        item["symbol"]: item for item in artifact["per_symbol_mismatch_table"]
    }
    assert set(by_symbol) == {"ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"}
    for symbol in ("ETHUSDT", "AVAXUSDT", "SUIUSDT"):
        assert by_symbol[symbol]["detector_attached"] is True
        assert by_symbol[symbol]["watcher_tick_present"] is True
        assert by_symbol[symbol]["computed"] is True
        assert by_symbol[symbol]["blocker_class"] == "computed_not_satisfied"
        assert by_symbol[symbol]["failed_facts"] == [
            "htf_trend_intact",
            "reclaim_confirmed",
        ]
    assert by_symbol["SOLUSDT"]["blocker_class"] == "computed_not_satisfied"
    assert by_symbol["SOLUSDT"]["failed_facts"] == ["reclaim_confirmed"]


def test_cpm_replay_live_rule_mismatch_precedes_computed_fact_failure():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay=_cpm_replay(
            _cpm_event(
                "ETHUSDT",
                replay_required_facts=["legacy_reclaim_rule", "htf_trend_intact"],
            )
        ),
        cpm_facts=_cpm_ready_facts(),
        mpg_watcher={},
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    mismatch = artifact["strategy_rows"][0]["mismatch_table"][0]
    assert mismatch["detector_attached"] is True
    assert mismatch["watcher_tick_present"] is True
    assert mismatch["computed"] is True
    assert mismatch["failed_facts"] == ["htf_trend_intact", "reclaim_confirmed"]
    assert mismatch["blocker_class"] == "replay_live_rule_mismatch"
    assert mismatch["first_blocker_class"] == "replay_live_rule_mismatch"
    assert artifact["per_symbol_mismatch_table"][0]["blocker_class"] == (
        "replay_live_rule_mismatch"
    )


def test_per_symbol_blocker_priority_is_deterministic_for_mixed_cpm_mismatches():
    module = _load_module()

    artifact = module.build_replay_live_parity_audit(
        replay=_cpm_replay(
            _cpm_event("ETHUSDT"),
            _cpm_event(
                "ETHUSDT",
                replay_required_facts=["legacy_reclaim_rule", "htf_trend_intact"],
            ),
        ),
        cpm_facts=_cpm_ready_facts(),
        mpg_watcher={},
        sor_evidence={},
        generated_at_utc="2026-06-30T00:00:00+00:00",
    )

    symbol_row = artifact["per_symbol_mismatch_table"][0]
    assert symbol_row["symbol"] == "ETHUSDT"
    assert symbol_row["mismatch_reasons"] == [
        "computed_not_satisfied",
        "replay_live_rule_mismatch",
    ]
    assert symbol_row["blocker_class"] == "replay_live_rule_mismatch"
    assert symbol_row["next_action"] == (
        "normalize_replay_and_live_detector_fact_rules"
    )
    assert symbol_row["failed_facts"] == ["htf_trend_intact", "reclaim_confirmed"]
