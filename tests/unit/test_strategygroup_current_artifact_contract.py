from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def test_current_tradeability_artifact_matches_monitor_sequence_contract():
    verdict = _read_json(
        "output/runtime-monitor/latest-strategygroup-tradeability-verdict.json"
    )
    monitor = _read_json("output/runtime-monitor/latest-local-monitor-sequence.json")

    verdict_rows = verdict.get("verdict_rows") or []
    monitor_checks = monitor.get("checks") or {}
    verdict_row_count = verdict.get("summary", {}).get("row_count")

    assert verdict["schema"] == "brc.strategygroup_tradeability_verdict.v1"
    assert verdict["scope"] == "strategygroup_tradeability_verdict_read_model"
    assert verdict["generated_at_utc"]
    assert verdict["owner_summary"]
    assert verdict_row_count == len(verdict_rows)
    assert verdict.get("checks", {}).get("row_count_matches_verdict_rows") is True
    assert monitor_checks.get("tradeability_row_count") == verdict_row_count
    assert monitor_checks.get("tradeability_verdict_rows_count") == len(verdict_rows)
    assert monitor_checks.get("tradeability_row_count_matches_verdict_rows") is True


def test_current_trial_asset_admission_proposal_artifact_is_complete():
    proposal_packet = _read_json(
        "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
    )
    proposal = proposal_packet.get("proposal") or {}

    assert (
        proposal_packet["schema"]
        == "brc.strategygroup_trial_asset_admission_proposal.v1"
    )
    assert (
        proposal_packet["scope"]
        == "strategygroup_trial_asset_admission_proposal_non_applying"
    )
    assert proposal_packet["generated_at_utc"]
    assert proposal["owner_policy_defaults"]
    assert proposal["proposed_registry_row"]
    assert proposal["proposed_tier_policy_row"]
    assert proposal["runtime_admission_plan"]
    assert proposal["actionable_now"] is False
    assert proposal["real_order_authority"] is False
