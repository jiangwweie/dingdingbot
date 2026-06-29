from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_strategygroup_btpc_proxy_replay_quality_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_proxy_replay_quality_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _proxy_artifact() -> dict:
    return {
        "status": "btpc_local_fact_proxy_review_ready",
        "counts": {
            "expected_proxy_fact_count": 5,
            "proxy_attached_count": 5,
        },
        "review_outcome_state": {
            "local_proxy_can_feed_replay_review": True,
            "local_proxy_satisfies_live_required_facts": False,
        },
        "proxy_rows": [
            _proxy_row("historical_open_interest_window"),
            _proxy_row("historical_global_long_short_ratio_window"),
            _proxy_row("top_trader_position_ratio_window"),
            _proxy_row("real_exchange_margin_liquidation_model"),
            _proxy_row("short_squeeze_risk"),
        ],
        "interaction": {
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
        },
        "safety_invariants": {
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _proxy_row(required_fact: str) -> dict:
    return {
        "required_fact": required_fact,
        "l2_quality_proxy_ready": True,
        "live_required_fact_satisfied": False,
    }


def _replay_corpus() -> dict:
    return {
        "schema_version": "brc.strategygroup.l2_shadow_replay_corpus.v1",
        "strategy_group_id": "BTPC-001",
        "scope": "l2_shadow_candidate_observation_only",
        "live_order_eligible": False,
        "replay_samples": [
            _sample(
                "btpc-001-l2-bear-pullback-would-enter",
                "bear_pullback_would_enter",
                "SOLUSDT",
                "short",
                "would_enter_observe_only",
                "review_only_warning",
                "running",
                "keep_observing",
            ),
            _sample(
                "btpc-001-l2-no-signal-bear-trend-not-ready",
                "no_signal_bear_trend_not_ready",
                "ETHUSDT",
                "none",
                "no_signal",
                "waiting_for_market",
                "waiting_for_opportunity",
                "keep_observing",
            ),
            _sample(
                "btpc-001-l2-strong-uptrend-conflict",
                "strong_uptrend_conflict",
                "BTCUSDT",
                "short",
                "signal_conflict",
                "review_only_warning",
                "running",
                "revise",
            ),
            _sample(
                "btpc-001-l2-missing-derivatives-context",
                "missing_derivatives_context",
                "AVAXUSDT",
                "short",
                "would_enter_missing_required_facts",
                "missing_fact",
                "temporarily_unavailable",
                "revise",
            ),
            _sample(
                "btpc-001-l2-stale-signal",
                "stale_signal",
                "SOLUSDT",
                "short",
                "stale_signal",
                "missing_fact",
                "temporarily_unavailable",
                "revise",
            ),
        ],
    }


def _sample(
    event_id: str,
    fixture_case: str,
    symbol: str,
    side: str,
    signal_status: str,
    blocker_class: str,
    expected_owner_state: str,
    review_recommendation: str,
) -> dict:
    return {
        "event_id": event_id,
        "fixture_case": fixture_case,
        "symbol": symbol,
        "side": side,
        "signal_status": signal_status,
        "blocker_class": blocker_class,
        "expected_owner_state": expected_owner_state,
        "review_recommendation": review_recommendation,
        "cost_review": {"not_submit_authority": True},
        "not_execution_authority": True,
        "operation_layer_submit_allowed": False,
        "exchange_write_allowed": False,
        "real_order_allowed": False,
    }


def test_btpc_proxy_replay_quality_review_classifies_case_level_outcomes() -> None:
    module = _load_module()

    artifact = module.build_btpc_proxy_replay_quality_review(
        btpc_local_fact_proxy_artifact=_proxy_artifact(),
        replay_corpus=_replay_corpus(),
    )

    assert artifact["status"] == "btpc_proxy_replay_quality_review_ready"
    assert artifact["counts"]["replay_case_count"] == 5
    assert artifact["counts"]["would_enter_case_count"] == 2
    assert artifact["counts"]["proxy_reviewable_would_enter_count"] == 2
    assert artifact["counts"]["proxy_resolved_missing_derivatives_context_count"] == 1
    assert artifact["counts"]["freshness_or_conflict_revision_count"] == 2
    assert artifact["counts"]["keep_observing_count"] == 2
    assert artifact["counts"]["live_required_fact_satisfied_count"] == 0
    assert "real_order_authorized_count" not in artifact["counts"]
    assert artifact["counts"]["l4_scope_change_recommended_count"] == 0
    assert "decision_counts" not in artifact
    assert artifact["proxy_replay_quality_review_outcome_counts"] == {
        "keep_observing_l2_shadow_with_proxy_context": 1,
        "keep_waiting_for_market_no_action_baseline": 1,
        "revise_conflict_disable_before_l2_promotion": 1,
        "revise_freshness_or_classifier_before_l2_promotion": 1,
        "revise_live_fact_collection_but_l2_proxy_reviewable": 1,
    }

    rows = {row["fixture_case"]: row for row in artifact["case_rows"]}
    assert rows["bear_pullback_would_enter"][
        "proxy_replay_quality_review_outcome"
    ] == "keep_observing_l2_shadow_with_proxy_context"
    assert rows["missing_derivatives_context"]["proxy_effect"] == (
        "l2_proxy_resolves_missing_derivatives_context_for_review_only"
    )
    assert rows["missing_derivatives_context"][
        "live_required_facts_satisfied"
    ] is False
    assert rows["strong_uptrend_conflict"][
        "proxy_replay_quality_review_outcome"
    ] == "revise_conflict_disable_before_l2_promotion"
    assert rows["stale_signal"][
        "proxy_replay_quality_review_outcome"
    ] == "revise_freshness_or_classifier_before_l2_promotion"
    assert all("real_order_authority" not in row for row in rows.values())
    assert all(row["operation_layer_authority"] is False for row in rows.values())
    assert all(row["exchange_write_authority"] is False for row in rows.values())
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert (
        review_outcome["source_role"]
        == "btpc_proxy_replay_quality_review_provenance"
    )
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["proxy_replay_quality_review_ready"] is True
    assert (
        review_outcome["proxy_replay_satisfies_live_required_facts"]
        is False
    )
    assert review_outcome["l4_scope_change_recommended"] is False
    assert "decision" not in artifact
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["approaches_real_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["interaction"]["places_order"] is False
    assert "operator_command_plan" not in artifact
    assert artifact["safety_invariants"]["proxy_replay_is_not_live_required_fact"] is True
    assert artifact["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_btpc_proxy_replay_quality_review_blocks_live_replay_authority() -> None:
    module = _load_module()
    corpus = _replay_corpus()
    corpus["replay_samples"][0]["operation_layer_submit_allowed"] = True

    artifact = module.build_btpc_proxy_replay_quality_review(
        btpc_local_fact_proxy_artifact=_proxy_artifact(),
        replay_corpus=corpus,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert (
        "btpc_replay_corpus.bear_pullback_would_enter.operation_layer_submit_allowed"
        in artifact["safety_invariants"]["source_forbidden_effects"]
    )
    assert artifact["review_outcome_state"]["default_next_step"] == (
        "stop_and_repair_btpc_proxy_replay_quality_source_forbidden_effects"
    )
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_btpc_proxy_replay_quality_review_rejects_source_legacy_authority_mirrors() -> None:
    module = _load_module()
    proxy = _proxy_artifact()
    proxy["safety_invariants"]["real_order_authority"] = False
    proxy["review_outcome_state"]["actionable_now"] = False
    proxy["proxy_rows"][0]["real_order_authority"] = False
    corpus = _replay_corpus()
    corpus["actionable_now"] = False
    corpus["replay_samples"][0]["real_order_authority"] = False

    artifact = module.build_btpc_proxy_replay_quality_review(
        btpc_local_fact_proxy_artifact=proxy,
        replay_corpus=corpus,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    effects = artifact["safety_invariants"]["source_forbidden_effects"]
    assert (
        "btpc_local_fact_proxy.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "btpc_local_fact_proxy.review_outcome_state."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects
    assert (
        "btpc_local_fact_proxy.proxy_rows.historical_open_interest_window."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert "btpc_replay_corpus.legacy_authority_mirror_present:actionable_now" in effects
    assert (
        "btpc_replay_corpus.bear_pullback_would_enter."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects


def test_btpc_proxy_replay_quality_review_rejects_legacy_packet_kwarg() -> None:
    module = _load_module()

    with pytest.raises(TypeError):
        module.build_btpc_proxy_replay_quality_review(
            btpc_local_fact_proxy_packet=_proxy_artifact(),
            replay_corpus=_replay_corpus(),
        )


def test_btpc_proxy_replay_quality_review_cli_writes_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    proxy_path = tmp_path / "proxy.json"
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "proxy-replay.json"
    owner_path = tmp_path / "proxy-replay.md"
    proxy_path.write_text(json.dumps(_proxy_artifact()), encoding="utf-8")
    replay_path.write_text(json.dumps(_replay_corpus()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-local-fact-proxy-json",
            str(proxy_path),
            "--btpc-replay-corpus-json",
            str(replay_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "btpc_proxy_replay_quality_review"
    assert file_payload["status"] == "btpc_proxy_replay_quality_review_ready"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC Proxy Replay Quality Review" in owner_text
    assert "Real order authority" not in owner_text
    assert "| Case | Signal | Proxy status | Decision | Exchange write |" in owner_text
    assert "| Case | Signal | Proxy status | Decision | Real order |" not in owner_text


def test_btpc_proxy_replay_cli_omitted_local_proxy_does_not_read_default(
    tmp_path: Path,
) -> None:
    module = _load_module()
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "proxy-replay.json"
    owner_path = tmp_path / "proxy-replay.md"
    replay_path.write_text(json.dumps(_replay_corpus()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-replay-corpus-json",
            str(replay_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["status"] == "btpc_proxy_replay_quality_review_incomplete"
    assert artifact["source_status"]["btpc_local_fact_proxy_review"] is None
