from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_research_intake_review.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_research_intake_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _research_intake_artifact(*, forbidden: bool = False) -> dict:
    return {
        "schema": "brc.strategy_research_tiny_live_intake_candidates.v1",
        "scope": "strategy_research_only",
        "status": "tiny_live_intake_candidates_ready",
        "summary": {
            "objective_met": True,
            "candidate_count": 2,
            "intake_candidate_count": 2,
        },
        "authority_boundary": {
            "research_only": True,
            "exchange_write": forbidden,
            "execution_authority": False,
            "finalgate_input": False,
            "live_profile_change": False,
            "live_required_facts": False,
            "operation_layer_input": False,
            "order_created": False,
            "tier_policy_change": False,
        },
        "candidates": [
            {
                "strategy_id": "BRF2-001",
                "strategy_direction": "bear_rally_failure_right_tail_short",
                "intake_status": "tiny_live_intake_candidate",
                "recommended_runtime_stage": (
                    "tiny_live_intake_candidate_with_path_risk"
                ),
                "paper_observation_ready": True,
                "tiny_live_ready": False,
                "required_facts_draft": [
                    "closed_1h_ohlcv",
                    "closed_4h_trend",
                    "ema_20",
                    "ema_48",
                    "rally_depth_24h",
                    "squeeze_risk_state",
                ],
                "disable_or_review_facts_draft": [
                    "disable_strong_reclaim_proxy",
                    "disable_low_structure_loss_atr_lt_0_15",
                ],
                "risk_envelope": {
                    "attempt_cap_per_review_cycle": 3,
                    "max_consecutive_losses": 2,
                },
                "evidence": {
                    "accepted_event_count": 11,
                    "path_safe_rate": 0.7273,
                    "stop_hit_count": 3,
                },
                "known_risks": ["3_of_11_cap4_events_hit_5m_stop"],
                "source_reports": ["brf2-right-tail-trial-envelope.json"],
            },
            {
                "strategy_id": "RBR2-001",
                "strategy_direction": "range_upper_boundary_mean_reversion_short",
                "intake_status": "tiny_live_intake_candidate",
                "recommended_runtime_stage": (
                    "tiny_live_intake_candidate_with_path_risk"
                ),
                "paper_observation_ready": True,
                "tiny_live_ready": False,
                "required_facts_draft": [
                    "closed_1h_ohlcv",
                    "range_width_72h",
                    "boundary_position",
                ],
                "disable_or_review_facts_draft": [
                    "range_regime_detector_v0",
                    "failed_upside_expansion_classifier_branch",
                ],
                "risk_envelope": {
                    "attempt_cap_per_review_cycle": 3,
                    "max_consecutive_losses": 2,
                },
                "evidence": {
                    "accepted_events": 78,
                    "path_stop_rate_5m": 0.5897,
                    "sample_event_count": 669,
                },
                "known_risks": ["5m_stop_hit_rate_is_high"],
                "source_reports": ["rbr2-mean-reversion-role-validation.json"],
            },
        ],
    }


def test_research_intake_review_maps_real_fields_without_authority():
    module = _load_module()

    review_artifact = module.build_research_intake_review(
        research_intake_artifact=_research_intake_artifact(),
        source_path=Path("/tmp/tiny-live-intake-candidates.json"),
        generated_at_utc="2026-06-22T00:00:00Z",
    )

    assert review_artifact["status"] == "research_intake_review_ready"
    assert review_artifact["source_status"]["summary_objective_met"] is True
    assert review_artifact["summary"]["candidate_count"] == 2
    assert review_artifact["summary"]["paper_observation_admission_candidate_count"] == 1
    assert review_artifact["summary"]["role_only_intake_candidate_count"] == 1
    assert "tiny_live_ready_count" not in review_artifact["summary"]
    assert "source_tiny_live_ready_count" not in review_artifact["summary"]
    assert review_artifact["summary"]["source_non_executing_trial_readiness_count"] == 0
    assert "actionable_now_count" not in review_artifact["summary"]
    assert "real_order_authority_count" not in review_artifact["summary"]
    assert "actionable_now" not in review_artifact["safety_invariants"]
    assert "real_order_authority" not in review_artifact["safety_invariants"]

    rows = {row["strategy_group_id"]: row for row in review_artifact["candidate_rows"]}
    assert rows["BRF2-001"]["strategy_direction"] == (
        "bear_rally_failure_right_tail_short"
    )
    assert rows["BRF2-001"]["main_control_intake_position"] == (
        "paper_observation_admission_candidate"
    )
    assert rows["BRF2-001"]["promotion_scope"] == "intake_only"
    assert rows["BRF2-001"]["promotion_target"] == (
        "paper_observation_or_experiment_evidence"
    )
    assert rows["BRF2-001"]["paper_observation_ready"] is True
    assert rows["BRF2-001"]["source_non_executing_trial_readiness"] is False
    assert "source_tiny_live_ready" not in rows["BRF2-001"]
    assert "tiny_live_ready" not in rows["BRF2-001"]
    assert rows["BRF2-001"]["finalgate_input"] is False
    assert rows["BRF2-001"]["operation_layer_input"] is False
    assert "FinalGate" in rows["BRF2-001"]["paper_observation_evidence_shape"][
        "must_not_feed"
    ]
    assert "Tradeability Decision authority" in rows["BRF2-001"][
        "paper_observation_evidence_shape"
    ]["must_not_feed"]
    assert "Runtime Safety State authority" in rows["BRF2-001"][
        "paper_observation_evidence_shape"
    ]["must_not_feed"]
    assert "actionable_now" not in rows["BRF2-001"][
        "paper_observation_evidence_shape"
    ]["must_not_feed"]
    assert "review_outcome" in rows["BRF2-001"]["paper_observation_evidence_shape"][
        "must_record"
    ]
    assert "review_ledger_decision" not in rows["BRF2-001"][
        "paper_observation_evidence_shape"
    ]["must_record"]
    assert rows["BRF2-001"]["source_reports"] == [
        "brf2-right-tail-trial-envelope.json"
    ]
    assert rows["RBR2-001"]["main_control_intake_position"] == (
        "role_only_intake_candidate"
    )
    assert rows["RBR2-001"]["promotion_scope"] == "not_applicable"

    provenance_rows = {
        row["strategy_group_id"]: row
        for row in review_artifact["strategy_decision_provenance_rows"]
    }
    assert provenance_rows["BRF2-001"]["current_decision"] == "promote"
    assert provenance_rows["BRF2-001"]["strategy_asset_seed_source"] == (
        "curated_research_intake_strategy_asset_seed"
    )
    assert "decision_source" not in provenance_rows["BRF2-001"]
    assert "decision" not in provenance_rows["BRF2-001"]
    assert provenance_rows["BRF2-001"]["promotion_scope"] == "intake_only"
    assert provenance_rows["BRF2-001"]["promotion_target"] == (
        "paper_observation_or_experiment_evidence"
    )
    assert provenance_rows["RBR2-001"]["current_decision"] == "keep_observing"
    assert provenance_rows["RBR2-001"]["strategy_asset_seed_source"] == (
        "curated_research_intake_strategy_asset_seed"
    )
    assert "decision_source" not in provenance_rows["RBR2-001"]
    assert "decision" not in provenance_rows["RBR2-001"]
    assert provenance_rows["RBR2-001"]["promotion_scope"] == "not_applicable"
    assert "no_official_live_order_authority" in provenance_rows["BRF2-001"][
        "authority_boundary"
    ]
    assert "promotion_scope=intake_only" in provenance_rows["BRF2-001"][
        "authority_boundary"
    ]
    legacy_rows_key = "decision" + "_ledger_rows"
    assert legacy_rows_key not in review_artifact
    assert review_artifact["owner_progress_projection"]["signal_observation_state"] == (
        "research_intake_review_active"
    )
    assert review_artifact["interaction"]["calls_finalgate"] is False
    assert review_artifact["interaction"]["calls_operation_layer"] is False
    assert review_artifact["interaction"]["calls_exchange_write"] is False
    assert review_artifact["safety_invariants"]["tier_policy_changed"] is False


def test_unconfigured_research_intake_candidate_does_not_fabricate_asset_decision():
    module = _load_module()
    source_artifact = _research_intake_artifact()
    source_artifact["candidates"].append(
        {
            "strategy_id": "CPM-RO-001",
            "strategy_direction": "crypto_pair_momentum_rotation_observe_only",
            "intake_status": "research_intake_candidate",
            "recommended_runtime_stage": "observe_only_candidate",
            "paper_observation_ready": True,
            "tiny_live_ready": False,
            "required_facts_draft": ["closed_1h_ohlcv", "relative_strength_rank"],
            "disable_or_review_facts_draft": ["momentum_regime_confirmation"],
            "risk_envelope": {
                "attempt_cap_per_review_cycle": 0,
                "max_consecutive_losses": 0,
            },
            "evidence": {"sample_event_count": 12},
            "known_risks": ["research_candidate_not_strategy_asset_state_authority"],
            "source_reports": ["cpm-observe-only-candidate.json"],
        }
    )

    review_artifact = module.build_research_intake_review(
        research_intake_artifact=source_artifact,
        source_path=Path("/tmp/tiny-live-intake-candidates.json"),
        generated_at_utc="2026-06-22T00:00:00Z",
    )

    rows = {row["strategy_group_id"]: row for row in review_artifact["candidate_rows"]}
    provenance_rows = {
        row["strategy_group_id"]: row
        for row in review_artifact["strategy_decision_provenance_rows"]
    }
    assert rows["CPM-RO-001"]["main_control_intake_position"] == (
        "research_intake_candidate_review"
    )
    assert rows["CPM-RO-001"]["promotion_scope"] == "not_applicable"
    assert rows["CPM-RO-001"]["promotion_target"] == "not_applicable"
    assert "actionable_now" not in rows["CPM-RO-001"]
    assert "real_order_authority" not in rows["CPM-RO-001"]
    assert rows["CPM-RO-001"]["finalgate_input"] is False
    assert rows["CPM-RO-001"]["operation_layer_input"] is False
    assert rows["CPM-RO-001"]["exchange_write"] is False
    assert provenance_rows["CPM-RO-001"]["current_decision"] == "unknown"
    assert provenance_rows["CPM-RO-001"]["strategy_asset_seed_source"] == (
        "missing_strategy_asset_seed"
    )
    assert "decision_source" not in provenance_rows["CPM-RO-001"]
    assert "decision" not in provenance_rows["CPM-RO-001"]
    assert provenance_rows["CPM-RO-001"]["promotion_scope"] == "not_applicable"
    assert provenance_rows["CPM-RO-001"]["promotion_target"] == "not_applicable"
    assert provenance_rows["CPM-RO-001"]["next_checkpoint"] == (
        "CPM-RO-001_main_control_research_intake_review"
    )
    assert "no_official_live_order_authority" in provenance_rows["CPM-RO-001"][
        "authority_boundary"
    ]
    assert review_artifact["interaction"]["calls_finalgate"] is False
    assert review_artifact["interaction"]["calls_operation_layer"] is False
    assert review_artifact["interaction"]["calls_exchange_write"] is False


def test_research_intake_review_blocks_forbidden_source_authority():
    module = _load_module()

    review_artifact = module.build_research_intake_review(
        research_intake_artifact=_research_intake_artifact(forbidden=True)
    )

    assert review_artifact["status"] == "blocked_forbidden_source_authority"
    assert "authority_boundary.exchange_write=true" in review_artifact["source_status"][
        "source_forbidden_effects"
    ]
    assert review_artifact["interaction"]["calls_exchange_write"] is False
    assert review_artifact["safety_invariants"]["exchange_write_called"] is False


def test_research_intake_review_blocks_legacy_authority_mirror():
    module = _load_module()
    source = _research_intake_artifact()
    source["authority_boundary"]["actionable_now"] = True
    source["candidates"][0]["real_order_authority"] = True

    review_artifact = module.build_research_intake_review(
        research_intake_artifact=source
    )

    assert review_artifact["status"] == "blocked_forbidden_source_authority"
    assert (
        "legacy_authority_mirror_present:authority_boundary.actionable_now=true"
        in review_artifact["source_status"]["source_forbidden_effects"]
    )
    assert (
        "legacy_authority_mirror_present:candidates[0].real_order_authority=true"
        in review_artifact["source_status"]["source_forbidden_effects"]
    )


def test_research_intake_review_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    input_path = tmp_path / "tiny-live-intake-candidates.json"
    output_path = tmp_path / "review.json"
    md_path = tmp_path / "review.md"
    input_path.write_text(
        json.dumps(_research_intake_artifact(), ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = module.main(
        [
            "--research-intake-json",
            str(input_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(md_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["status"] == "research_intake_review_ready"
    assert "StrategyGroup Research Intake Review" in md_path.read_text(
        encoding="utf-8"
    )


def test_research_intake_review_default_input_is_final_owned_snapshot():
    module = _load_module()

    default_path = module.DEFAULT_RESEARCH_INTAKE_JSON

    assert str(default_path).startswith(str(module.REPO_ROOT))
    assert "final-strategy-research" not in str(default_path)
    assert default_path.name == "tiny-live-intake-candidates.json"
