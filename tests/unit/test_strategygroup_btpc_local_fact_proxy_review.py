from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_strategygroup_btpc_local_fact_proxy_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_local_fact_proxy_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _btpc_fact_quality() -> dict:
    return {
        "status": "btpc_l2_shadow_fact_quality_review_ready",
        "fact_rows": [
            {
                "gap": "historical_open_interest_window_missing",
                "required_fact": "historical_open_interest_window",
                "boundary_effect": "blocks_promotion_beyond_l2_review",
            },
            {
                "gap": "historical_global_long_short_ratio_window_missing",
                "required_fact": "historical_global_long_short_ratio_window",
                "boundary_effect": "blocks_promotion_beyond_l2_review",
            },
            {
                "gap": "top_trader_position_ratio_window_missing",
                "required_fact": "top_trader_position_ratio_window",
                "boundary_effect": "blocks_promotion_beyond_l2_review",
            },
            {
                "gap": "real_exchange_margin_liquidation_model_missing",
                "required_fact": "real_exchange_margin_liquidation_model",
                "boundary_effect": "blocks_any_btpc_real_order_eligibility",
            },
            {
                "gap": "short_squeeze_risk_not_runtime_blocking",
                "required_fact": "short_squeeze_risk",
                "boundary_effect": "strategy_review_pending_not_runtime_blocking",
            },
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


def _btpc_handoff() -> dict:
    return {
        "status": "l2_intake_contract_observe_only",
        "execution_boundary": {
            "final_gate_input": False,
            "operation_layer_input": False,
            "real_submit_authorized": False,
        },
        "risk_defaults": {
            "risk_tier": "not_live_order_eligible",
            "max_notional_per_action_usdt": "0",
            "max_active_positions": 0,
            "research_leverage_context": ["1x", "2x", "3x", "5x"],
        },
    }


def _replay_corpus() -> dict:
    return {
        "schema_version": "brc.strategygroup.l2_shadow_replay_corpus.v1",
        "strategy_group_id": "BTPC-001",
        "scope": "l2_shadow_candidate_observation_only",
        "live_order_eligible": False,
        "replay_samples": [
            {
                "fixture_case": "bear_pullback_would_enter",
                "signal_status": "would_enter_observe_only",
                "not_execution_authority": True,
                "operation_layer_submit_allowed": False,
                "exchange_write_allowed": False,
                "real_order_allowed": False,
            },
            {
                "fixture_case": "missing_derivatives_context",
                "signal_status": "would_enter_missing_required_facts",
                "not_execution_authority": True,
                "operation_layer_submit_allowed": False,
                "exchange_write_allowed": False,
                "real_order_allowed": False,
            },
            {
                "fixture_case": "no_signal_bear_trend_not_ready",
                "signal_status": "no_signal",
                "not_execution_authority": True,
                "operation_layer_submit_allowed": False,
                "exchange_write_allowed": False,
                "real_order_allowed": False,
            },
        ],
    }


def test_btpc_local_fact_proxy_review_attaches_review_only_proxies() -> None:
    module = _load_module()

    artifact = module.build_btpc_local_fact_proxy_review(
        btpc_fact_quality_artifact=_btpc_fact_quality(),
        btpc_handoff=_btpc_handoff(),
        replay_corpus=_replay_corpus(),
    )

    assert artifact["status"] == "btpc_local_fact_proxy_review_ready"
    assert artifact["counts"]["expected_proxy_fact_count"] == 5
    assert artifact["counts"]["proxy_attached_count"] == 5
    assert artifact["counts"]["l2_quality_proxy_ready_count"] == 5
    assert artifact["counts"]["live_required_fact_satisfied_count"] == 0
    assert artifact["counts"]["live_required_fact_gap_count"] == 5
    assert artifact["counts"]["btpc_live_order_eligibility_blocker_count"] == 1
    assert artifact["counts"]["margin_leverage_case_count"] == 4
    assert "real_order_authorized_count" not in artifact["counts"]
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert review_outcome["source_role"] == "btpc_local_fact_proxy_review_provenance"
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["l2_shadow_quality_review_can_continue"] is True
    assert review_outcome["local_proxy_can_feed_replay_review"] is True
    assert (
        review_outcome["local_proxy_satisfies_live_required_facts"]
        is False
    )
    assert review_outcome["l4_scope_change_recommended"] is False
    assert review_outcome["real_order_scope_change_recommended"] is False
    assert "decision" not in artifact

    rows = {row["required_fact"]: row for row in artifact["proxy_rows"]}
    assert rows["historical_open_interest_window"]["proxy_coverage_status"] == (
        "local_proxy_attached"
    )
    assert rows["real_exchange_margin_liquidation_model"][
        "proxy_coverage_status"
    ] == "local_review_model_attached"
    assert rows["real_exchange_margin_liquidation_model"][
        "blocks_btpc_live_order_eligibility"
    ] is True
    assert all(row["live_required_fact_satisfied"] is False for row in rows.values())
    assert all(row["proxy_can_feed_finalgate"] is False for row in rows.values())
    assert all(row["proxy_can_feed_operation_layer"] is False for row in rows.values())
    assert all("real_order_authority" not in row for row in rows.values())

    model = artifact["margin_liquidation_review_model"]
    assert model["status"] == "local_review_model_attached"
    assert model["not_exchange_truth"] is True
    assert model["does_not_lower_owner_selected_leverage"] is True
    assert [case["leverage"] for case in model["leverage_cases"]] == [
        "1x",
        "2x",
        "3x",
        "5x",
    ]
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["approaches_real_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["proxy_is_not_live_required_fact"] is True
    assert artifact["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert artifact["safety_invariants"]["does_not_change_live_profile_or_sizing_defaults"] is True
    assert "operator_command_plan" not in artifact
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_btpc_local_fact_proxy_review_blocks_forbidden_replay_authority() -> None:
    module = _load_module()
    replay = _replay_corpus()
    replay["live_order_eligible"] = True
    replay["replay_samples"][0]["exchange_write_allowed"] = True

    artifact = module.build_btpc_local_fact_proxy_review(
        btpc_fact_quality_artifact=_btpc_fact_quality(),
        btpc_handoff=_btpc_handoff(),
        replay_corpus=replay,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    effects = artifact["safety_invariants"]["source_forbidden_effects"]
    assert "btpc_replay_corpus.live_order_eligible" in effects
    assert "btpc_replay_corpus.bear_pullback_would_enter.exchange_write_allowed" in effects
    assert artifact["review_outcome_state"]["default_next_step"] == (
        "stop_and_repair_btpc_local_fact_proxy_source_forbidden_effects"
    )
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_btpc_local_fact_proxy_review_rejects_source_legacy_authority_mirrors() -> None:
    module = _load_module()
    fact_quality = _btpc_fact_quality()
    fact_quality["safety_invariants"]["real_order_authority"] = False
    fact_quality["fact_rows"][0]["actionable_now"] = False
    handoff = _btpc_handoff()
    handoff["execution_boundary"]["real_order_authority"] = False
    replay = _replay_corpus()
    replay["actionable_now"] = False
    replay["replay_samples"][0]["real_order_authority"] = False

    artifact = module.build_btpc_local_fact_proxy_review(
        btpc_fact_quality_artifact=fact_quality,
        btpc_handoff=handoff,
        replay_corpus=replay,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    effects = artifact["safety_invariants"]["source_forbidden_effects"]
    assert (
        "btpc_fact_quality.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "btpc_fact_quality.fact_rows.historical_open_interest_window."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects
    assert (
        "btpc_handoff.execution_boundary."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert "btpc_replay_corpus.legacy_authority_mirror_present:actionable_now" in effects
    assert (
        "btpc_replay_corpus.bear_pullback_would_enter."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects


def test_btpc_local_fact_proxy_review_rejects_legacy_packet_kwarg() -> None:
    module = _load_module()

    with pytest.raises(TypeError):
        module.build_btpc_local_fact_proxy_review(
            btpc_fact_quality_packet=_btpc_fact_quality(),
            btpc_handoff=_btpc_handoff(),
            replay_corpus=_replay_corpus(),
        )


def test_btpc_local_fact_proxy_review_cli_writes_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    fact_path = tmp_path / "fact-quality.json"
    handoff_path = tmp_path / "handoff.json"
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "proxy-review.json"
    owner_path = tmp_path / "proxy-review.md"
    fact_path.write_text(json.dumps(_btpc_fact_quality()), encoding="utf-8")
    handoff_path.write_text(json.dumps(_btpc_handoff()), encoding="utf-8")
    replay_path.write_text(json.dumps(_replay_corpus()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-fact-quality-json",
            str(fact_path),
            "--btpc-handoff-json",
            str(handoff_path),
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
    assert file_payload["scope"] == "btpc_local_fact_proxy_review"
    assert file_payload["status"] == "btpc_local_fact_proxy_review_ready"
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC Local Fact Proxy Review" in owner_text
    assert "Live RequiredFacts satisfied by proxy: `false`" in owner_text
    assert "Real order authority" not in owner_text
    assert "| Fact | Proxy | L2 review | Live fact | Operation layer |" in owner_text
    assert "| Fact | Proxy | L2 review | Live fact | Real order |" not in owner_text


def test_btpc_local_fact_proxy_cli_omitted_fact_quality_does_not_read_default(
    tmp_path: Path,
) -> None:
    module = _load_module()
    handoff_path = tmp_path / "handoff.json"
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "proxy-review.json"
    owner_path = tmp_path / "proxy-review.md"
    handoff_path.write_text(json.dumps(_btpc_handoff()), encoding="utf-8")
    replay_path.write_text(json.dumps(_replay_corpus()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-handoff-json",
            str(handoff_path),
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
    assert artifact["source_status"]["btpc_fact_quality_review"] is None
    assert (
        artifact["review_outcome_state"]["local_proxy_satisfies_live_required_facts"]
        is False
    )
