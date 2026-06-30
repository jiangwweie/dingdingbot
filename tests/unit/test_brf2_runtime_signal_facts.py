from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_runtime_signal_facts.py"
)
CAPTURE_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_brf2_runtime_signal_capture.py"
)


def _load_script_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_module():
    return _load_script_module(
        SCRIPT_PATH,
        "build_brf2_runtime_signal_facts",
    )


def _load_capture_module():
    return _load_script_module(
        CAPTURE_SCRIPT_PATH,
        "build_brf2_runtime_signal_capture",
    )


def _fresh_fact_artifact() -> dict:
    return {
        "strategy_group_id": "BRF2-001",
        "signal_context": {
            "signal_observation_id": "brf2-signal-001",
            "runtime_instance_id": "runtime-brf2-001",
            "symbol": "ADA/USDT:USDT",
            "timeframe": "5m_closed",
            "closed_at_utc": "2026-06-23T00:00:00+00:00",
        },
        "facts": {
            "closed_1h_ohlcv": {"status": "ready"},
            "closed_5m_ohlcv": {"status": "ready"},
            "rally_context": {"status": "bear_or_weak_reclaim"},
            "rally_failure_trigger_state": {"status": "confirmed"},
        },
    }


def _required_facts_mapping() -> dict:
    return {
        "status": "brf2_required_facts_mapping_ready",
        "strategy_group_id": "BRF2-001",
        "required_facts_mapping_ready": True,
        "required_fact_observation_specs": [
            {
                "fact_key": "closed_1h_ohlcv",
                "accepted_statuses": ["fresh", "present", "ready"],
            },
            {
                "fact_key": "closed_5m_ohlcv",
                "accepted_statuses": ["fresh", "present", "ready"],
            },
            {
                "fact_key": "rally_context",
                "accepted_statuses": [
                    "bear_or_weak_reclaim",
                    "ready",
                    "weak_rally",
                ],
            },
            {
                "fact_key": "rally_failure_trigger_state",
                "accepted_statuses": ["active", "confirmed", "ready"],
            },
        ],
        "disable_fact_observation_specs": [
            {
                "fact_key": "short_squeeze_risk_state",
                "active_statuses": ["red", "unbounded", "unknown"],
                "blocker": "squeeze_risk_not_clear",
            },
            {
                "fact_key": "strong_reclaim_disable_state",
                "active_statuses": ["active", "true"],
                "blocker": "strong_reclaim_disable_active",
            },
        ],
        "fresh_signal_rule": {
            "signal_id": "brf2_short_failure_signal",
            "timeframes": ["1h_closed", "5m_closed"],
            "freshness_window_ms": 300_000,
        },
    }


def _brf_reference_preview_artifact(*, would_enter: bool = False) -> dict:
    return {
        "status": "preview_built",
        "preview": {
            "current_signals": [
                {
                    "record_id": "BRF-001-BTC-SHORT:brf-signal:1782097200000",
                    "candidate_id": "BRF-001-BTC-SHORT",
                    "strategy_group_id": "BRF-001",
                    "strategy_family_version_id": "BRF-001-v0",
                    "symbol": "BTC/USDT:USDT",
                    "side": "short" if would_enter else "none",
                    "signal_type": "would_enter" if would_enter else "no_action",
                    "confidence": "0.64" if would_enter else "0.25",
                    "market_bar_timestamp_ms": 1782097200000,
                    "reason_codes": (
                        [
                            "brf_bear_rally_extended",
                            "brf_rally_high_rejected",
                            "brf_short_squeeze_risk_reviewed",
                        ]
                        if would_enter
                        else ["brf_no_action_no_rally_extension"]
                    ),
                    "evidence_payload": {
                        "htf_context": "trend_down",
                        "rally_extension_confirmed": would_enter,
                        "rejection_confirmed": would_enter,
                        "price_action_structure": {
                            "bear_rally_failure": would_enter,
                            "closed_bar": True,
                            "rally_pct": "2.4802" if would_enter else "1.1053",
                            "rejection_upper_wick_ratio": (
                                "0.3603" if would_enter else "0.0539"
                            ),
                            "close_reversal_pct": (
                                "0.7752" if would_enter else "0.0125"
                            ),
                            "rally_high_reference": "64788.00",
                            "rally_low_reference": "63220.00",
                        },
                        "short_squeeze_risk": {
                            "status": "reviewed",
                            "squeeze_warning": False,
                            "squeeze_risk_level": "bounded_review",
                        },
                    },
                    "signal_input_snapshot": {
                        "market_snapshot": {
                            "candle_context": {
                                "closed_bar": True,
                                "windows": {
                                    "1h": [
                                        {
                                            "open_time_ms": 1782097200000,
                                            "open": "64226.50",
                                            "high": "64788.00",
                                            "low": "63888.00",
                                            "close": "63935.10",
                                            "volume": "1234.5",
                                        }
                                    ]
                                },
                            }
                        }
                    },
                }
            ]
        },
    }


def _assert_checks_do_not_mirror_execution_authority(artifact: dict) -> None:
    for key in (
        "actionable_now",
        "real_order_authority",
        "action_time_required_facts_satisfied",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
    ):
        assert key not in artifact["checks"]


def _assert_safety_does_not_mirror_execution_intent(artifact: dict) -> None:
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_brf2_runtime_signal_facts_exposes_missing_watcher_input():
    module = _load_module()

    artifact = module.build_brf2_runtime_signal_facts(
        source_artifact={},
        source_path=Path("missing.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["schema"] == module.SCHEMA
    assert artifact["status"] == module.MISSING_STATUS
    assert artifact["strategy_group_id"] == "BRF2-001"
    assert artifact["fact_input_present"] is False
    assert artifact["watcher_tick_present"] is False
    assert artifact["first_blocker"]["class"] == "brf2_watcher_fact_input_missing"
    assert artifact["first_blocker"]["owner"] == "engineering"
    assert "next_action" not in artifact
    assert "next_action" not in artifact["first_blocker"]
    assert artifact["fact_input_checkpoint"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    assert artifact["first_blocker"]["repair_checkpoint"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["authorization_evidence_created"] is False
    _assert_safety_does_not_mirror_execution_intent(artifact)
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["interaction"]["places_order"] is False


def test_brf2_runtime_signal_facts_derives_from_brf_reference_watcher_row():
    module = _load_module()

    artifact = module.build_brf2_runtime_signal_facts(
        source_artifact=_brf_reference_preview_artifact(would_enter=False),
        source_path=Path("preview.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    facts = artifact["facts"]
    assert artifact["status"] == module.READY_STATUS
    assert artifact["strategy_group_id"] == "BRF2-001"
    assert artifact["fact_input_present"] is True
    assert artifact["watcher_tick_present"] is True
    assert artifact["fact_authority"] == module.READONLY_PROXY_FACT_AUTHORITY
    assert artifact["fact_authority_boundary"]["usable_for_armed_observation"] is True
    assert artifact["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert artifact["fact_authority_boundary"]["usable_for_finalgate"] is False
    assert artifact["fact_authority_boundary"]["usable_for_operation_layer"] is False
    assert artifact["source_signal_context"]["source_strategy_group_id"] == "BRF-001"
    assert artifact["source_signal_context"]["symbol"] == "BTC/USDT:USDT"
    assert artifact["signal_context"] == artifact["source_signal_context"]
    assert facts["closed_1h_ohlcv"]["status"] == "ready"
    assert facts["closed_5m_ohlcv"]["status"] == "ready"
    assert facts["closed_5m_ohlcv"]["detail"]["authority"] == (
        module.READONLY_PROXY_FACT_AUTHORITY
    )
    assert facts["closed_5m_ohlcv"]["detail"][
        "proxy_is_not_action_time_live_required_fact"
    ] is True
    assert facts["rally_context"]["status"] == "not_satisfied"
    assert facts["rally_failure_trigger_state"]["status"] == "not_confirmed"
    assert facts["short_squeeze_risk_state"]["status"] == "bounded"
    assert facts["strong_reclaim_disable_state"]["status"] == "false"
    assert artifact["first_blocker"]["class"] == "none"
    assert artifact["checks"]["source_is_brf_reference_row"] is True
    assert artifact["checks"]["derived_proxy_not_action_time_authority"] is True
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    _assert_safety_does_not_mirror_execution_intent(artifact)


def test_brf2_runtime_signal_facts_accepts_explicit_brf2_fact_artifact():
    module = _load_module()

    artifact = module.build_brf2_runtime_signal_facts(
        source_artifact=_fresh_fact_artifact(),
        source_path=Path("facts.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["status"] == module.READY_STATUS
    assert artifact["fact_input_present"] is True
    assert artifact["watcher_tick_present"] is True
    assert artifact["fact_authority"] == module.RUNTIME_READONLY_FACT_AUTHORITY
    assert artifact["fact_authority_boundary"][
        "action_time_required_facts_satisfied"
    ] is False
    assert artifact["source_signal_context"]["signal_observation_id"] == "brf2-signal-001"
    assert artifact["source_signal_context"]["symbol"] == "ADA/USDT:USDT"
    assert artifact["facts"]["closed_1h_ohlcv"]["status"] == "ready"
    assert artifact["first_blocker"]["class"] == "none"
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]
    _assert_safety_does_not_mirror_execution_intent(artifact)


def test_brf2_runtime_signal_facts_default_fallback_builds_preview_input():
    module = _load_module()

    source_artifact, source_path = module._load_source_artifact(
        source_json=None,
        strategy_source="sample",
    )
    artifact = module.build_brf2_runtime_signal_facts(
        source_artifact=source_artifact,
        source_path=source_path,
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    assert artifact["status"] == module.READY_STATUS
    assert artifact["source_path"] == "generated:sample:strategy_group_preview"
    assert artifact["checks"]["fact_input_present"] is True
    assert artifact["checks"]["brf2_source_row_present"] is True
    _assert_checks_do_not_mirror_execution_authority(artifact)


def test_brf2_runtime_signal_capture_blocks_missing_and_stale_required_facts():
    signal_module = _load_module()
    capture_module = _load_capture_module()
    source_artifact = _fresh_fact_artifact()
    del source_artifact["facts"]["closed_5m_ohlcv"]
    source_artifact["facts"]["rally_failure_trigger_state"] = {
        "status": "confirmed",
        "fresh": False,
        "stale": True,
    }

    fact_input = signal_module.build_brf2_runtime_signal_facts(
        source_artifact=source_artifact,
        source_path=Path("facts.json"),
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )
    artifact = capture_module.build_brf2_runtime_signal_capture(
        required_facts_mapping=_required_facts_mapping(),
        fact_input=fact_input,
        generated_at_utc="2026-06-23T00:00:00+00:00",
    )

    preview = artifact["signal_detector_preview"]
    assert artifact["status"] == "brf2_runtime_signal_capture_ready"
    assert artifact["fact_input_present"] is True
    assert artifact["checks"]["fresh_signal_present"] is False
    assert preview["current_signal_state"] == "fresh_signal_absent"
    assert preview["first_blocker_class"] == "fresh_brf2_short_signal_absent"
    assert preview["missing_required_fact_keys"] == [
        "closed_5m_ohlcv",
        "rally_failure_trigger_state",
    ]
    assert artifact["no_action_attribution"]["blocked_fact_count"] == 2
    assert artifact["shadow_candidate_shape"]["shadow_candidate_ready"] is False
    _assert_checks_do_not_mirror_execution_authority(artifact)
    assert artifact["safety_invariants"]["candidate_created"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_brf2_runtime_signal_facts_cli_writes_artifacts(tmp_path: Path):
    module = _load_module()
    source_json = tmp_path / "facts.json"
    output_json = tmp_path / "latest-brf2-runtime-signal-facts.json"
    output_md = tmp_path / "latest-brf2-runtime-signal-facts.md"
    source_json.write_text(json.dumps(_fresh_fact_artifact()), encoding="utf-8")

    exit_code = module.main(
        [
            "--source-json",
            str(source_json),
            "--output-json",
            str(output_json),
            "--output-owner-progress",
            str(output_md),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == module.READY_STATUS
    assert artifact["fact_input_present"] is True
    _assert_safety_does_not_mirror_execution_intent(artifact)
    markdown = output_md.read_text(encoding="utf-8")
    assert "BRF2 Runtime Signal Facts" in markdown
    assert "This packet" not in markdown
    assert "This artifact" in markdown
