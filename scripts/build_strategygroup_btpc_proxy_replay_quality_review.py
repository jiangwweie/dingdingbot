#!/usr/bin/env python3
"""Build the BTPC L2 proxy-aware replay quality review outcome.

This command consumes local BTPC fact-proxy review plus the BTPC L2 replay
corpus and produces Review Outcome State provenance. It can make
would-enter/no-action/stale/conflict replay outcomes easier to compare, but it
cannot satisfy live RequiredFacts, change tiers, call FinalGate, call Operation
Layer, or place orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    SOURCE_SAFETY_TRUE_KEYS,
    artifact_source_forbidden_effects,
    legacy_authority_mirror_effects_for_artifacts,
    legacy_authority_mirror_present_errors,
    non_executing_interaction,
    non_executing_safety_boundary,
    review_outcome_default_next_step,
    review_outcome_flag,
    review_outcome_state_boundary,
)

DEFAULT_BTPC_REPLAY_CORPUS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/BTPC-001/replay/btpc-001-l2-replay-corpus.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.md"
)


def build_btpc_proxy_replay_quality_review(
    *,
    btpc_local_fact_proxy_artifact: dict[str, Any],
    replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(
        btpc_local_fact_proxy_artifact,
        replay_corpus,
    )
    proxy_ready = _proxy_ready(btpc_local_fact_proxy_artifact)
    replay_boundary_ok = _replay_boundary_ok(replay_corpus)
    case_rows = _case_rows(
        replay_corpus=replay_corpus,
        btpc_local_fact_proxy_artifact=btpc_local_fact_proxy_artifact,
        proxy_ready=proxy_ready,
    )
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif not proxy_ready or not replay_boundary_ok:
        status = "btpc_proxy_replay_quality_review_incomplete"
    elif case_rows:
        status = "btpc_proxy_replay_quality_review_ready"
    else:
        status = "btpc_proxy_replay_quality_review_no_cases"

    proxy_replay_quality_review_outcome_counts: dict[str, int] = {}
    for row in case_rows:
        decision = str(row.get("proxy_replay_quality_review_outcome") or "unknown")
        proxy_replay_quality_review_outcome_counts[decision] = (
            proxy_replay_quality_review_outcome_counts.get(decision, 0) + 1
        )

    review_outcome_state = review_outcome_state_boundary(
        source_role="btpc_proxy_replay_quality_review_provenance",
        review_scope="proxy_replay_quality_review",
        extra={
            "strategy_group_id": "BTPC-001",
            "proxy_replay_quality_review_ready": (
                status == "btpc_proxy_replay_quality_review_ready"
            ),
            "btpc_l2_shadow_observation_can_continue": (
                status == "btpc_proxy_replay_quality_review_ready"
            ),
            "proxy_replay_can_feed_l2_quality_review": (
                status == "btpc_proxy_replay_quality_review_ready"
            ),
            "proxy_replay_satisfies_live_required_facts": False,
            "tier_policy_change_recommended_now": False,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
            "default_next_step": _default_next_step(status),
        },
    )

    return {
        "schema": "brc.btpc_proxy_replay_quality_review.v1",
        "scope": "btpc_proxy_replay_quality_review",
        "status": status,
        "source_status": {
            "btpc_local_fact_proxy_review": btpc_local_fact_proxy_artifact.get("status"),
            "replay_corpus": replay_corpus.get("schema_version"),
        },
        "interaction": non_executing_interaction(
            "L0_local_btpc_proxy_replay_quality_review"
        ),
        "counts": {
            "replay_case_count": len(case_rows),
            "would_enter_case_count": sum(
                1 for row in case_rows if row.get("would_enter") is True
            ),
            "proxy_reviewable_would_enter_count": sum(
                1
                for row in case_rows
                if row.get("proxy_review_status")
                == "proxy_context_sufficient_for_l2_shadow_review"
            ),
            "proxy_resolved_missing_derivatives_context_count": sum(
                1
                for row in case_rows
                if row.get("proxy_effect")
                == "l2_proxy_resolves_missing_derivatives_context_for_review_only"
            ),
            "freshness_or_conflict_revision_count": sum(
                1
                for row in case_rows
                if row.get("proxy_replay_quality_review_outcome")
                in {
                    "revise_freshness_or_classifier_before_l2_promotion",
                    "revise_conflict_disable_before_l2_promotion",
                }
            ),
            "keep_observing_count": sum(
                1
                for row in case_rows
                if row.get("proxy_replay_quality_review_outcome")
                in {
                    "keep_observing_l2_shadow_with_proxy_context",
                    "keep_waiting_for_market_no_action_baseline",
                }
            ),
            "live_required_fact_satisfied_count": 0,
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "proxy_replay_quality_review_outcome_counts": dict(
            sorted(proxy_replay_quality_review_outcome_counts.items())
        ),
        "case_rows": case_rows,
        "review_outcome_state": review_outcome_state,
        "safety_invariants": non_executing_safety_boundary(
            true_keys=(
                "local_btpc_proxy_replay_quality_review_only",
                "proxy_replay_is_not_live_required_fact",
                "input_is_not_execution_authority",
                "does_not_lower_owner_selected_leverage",
                "does_not_change_live_profile_or_sizing_defaults",
            ),
            false_keys=(
                "server_interaction",
                "server_files_mutated",
                "runtime_started",
                "strategy_parameters_changed",
                "tier_policy_changed",
                "l2_promotion_authorized",
                "l4_real_order_scope_expanded",
                "shadow_candidate_created",
                "final_gate_called",
                "operation_layer_called",
                "order_created",
                "order_lifecycle_called",
                "exchange_write_called",
                "withdrawal_or_transfer_created",
            ),
            source_forbidden_effects=forbidden_effects,
        ),
    }


def render_owner_progress_markdown(artifact: dict[str, Any]) -> str:
    counts = _as_dict(artifact.get("counts"))
    lines = [
        "# BTPC Proxy Replay Quality Review",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Replay cases: `{counts.get('replay_case_count', 0)}`",
        f"- Proxy-reviewable would-enter: `{counts.get('proxy_reviewable_would_enter_count', 0)}`",
        f"- Missing-derivatives cases resolved for L2 review only: `{counts.get('proxy_resolved_missing_derivatives_context_count', 0)}`",
        "- Live RequiredFacts satisfied by proxy replay: `false`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "",
        "## Case Rows",
        "",
        _case_table(_dict_rows(artifact.get("case_rows"))),
        "",
        "## Next",
        "",
        f"- `{review_outcome_default_next_step(artifact)}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _case_rows(
    *,
    replay_corpus: dict[str, Any],
    btpc_local_fact_proxy_artifact: dict[str, Any],
    proxy_ready: bool,
) -> list[dict[str, Any]]:
    proxy_facts = [
        str(row.get("required_fact"))
        for row in _dict_rows(btpc_local_fact_proxy_artifact.get("proxy_rows"))
        if row.get("l2_quality_proxy_ready") is True
    ]
    rows: list[dict[str, Any]] = []
    for sample in _dict_rows(replay_corpus.get("replay_samples")):
        fixture_case = str(sample.get("fixture_case") or "unknown")
        signal_status = str(sample.get("signal_status") or "unknown")
        decision, proxy_status, proxy_effect = _case_review_outcome(
            fixture_case=fixture_case,
            signal_status=signal_status,
            blocker_class=str(sample.get("blocker_class") or ""),
            proxy_ready=proxy_ready,
        )
        would_enter = "would_enter" in signal_status
        rows.append(
            {
                "event_id": sample.get("event_id"),
                "fixture_case": fixture_case,
                "symbol": sample.get("symbol"),
                "side": sample.get("side"),
                "signal_status": signal_status,
                "blocker_class": sample.get("blocker_class"),
                "expected_owner_state": sample.get("expected_owner_state"),
                "would_enter": would_enter,
                "original_review_recommendation": sample.get("review_recommendation"),
                "proxy_review_status": proxy_status,
                "proxy_effect": proxy_effect,
                "proxy_facts_used": proxy_facts,
                "cost_review_present": isinstance(sample.get("cost_review"), dict),
                "proxy_replay_quality_review_outcome": decision,
                "l2_shadow_observation_can_continue": proxy_ready,
                "l2_promotion_authority": False,
                "l4_scope_change_recommended": False,
                "live_required_facts_satisfied": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            }
        )
    return rows


def _case_review_outcome(
    *,
    fixture_case: str,
    signal_status: str,
    blocker_class: str,
    proxy_ready: bool,
) -> tuple[str, str, str]:
    if not proxy_ready:
        return (
            "repair_proxy_inputs_before_replay_quality_review",
            "proxy_context_missing",
            "no_proxy_quality_effect",
        )
    if fixture_case == "missing_derivatives_context":
        return (
            "revise_live_fact_collection_but_l2_proxy_reviewable",
            "proxy_context_sufficient_for_l2_shadow_review",
            "l2_proxy_resolves_missing_derivatives_context_for_review_only",
        )
    if signal_status == "would_enter_observe_only":
        return (
            "keep_observing_l2_shadow_with_proxy_context",
            "proxy_context_sufficient_for_l2_shadow_review",
            "l2_proxy_preserves_would_enter_observation_without_live_authority",
        )
    if signal_status == "no_signal" or blocker_class == "waiting_for_market":
        return (
            "keep_waiting_for_market_no_action_baseline",
            "proxy_context_not_required_for_no_action",
            "no_action_baseline_preserved",
        )
    if fixture_case == "strong_uptrend_conflict":
        return (
            "revise_conflict_disable_before_l2_promotion",
            "proxy_context_available_but_conflict_rule_dominates",
            "conflict_still_blocks_promotion_review",
        )
    if signal_status == "stale_signal":
        return (
            "revise_freshness_or_classifier_before_l2_promotion",
            "proxy_context_available_but_freshness_rule_dominates",
            "freshness_still_blocks_promotion_review",
        )
    return (
        "continue_l2_shadow_quality_review",
        "proxy_context_available",
        "continue_review",
    )


def _proxy_ready(artifact: dict[str, Any]) -> bool:
    counts = _as_dict(artifact.get("counts"))
    expected = _int(counts.get("expected_proxy_fact_count"))
    attached = _int(counts.get("proxy_attached_count"))
    return (
        artifact.get("status") == "btpc_local_fact_proxy_review_ready"
        and expected > 0
        and attached == expected
        and review_outcome_flag(artifact, "local_proxy_can_feed_replay_review")
        and review_outcome_flag(artifact, "local_proxy_satisfies_live_required_facts")
        is False
    )


def _replay_boundary_ok(artifact: dict[str, Any]) -> bool:
    return (
        artifact.get("live_order_eligible") is not True
        and all(
            row.get("real_order_allowed") is not True
            and row.get("exchange_write_allowed") is not True
            and row.get("operation_layer_submit_allowed") is not True
            and row.get("not_execution_authority") is True
            for row in _dict_rows(artifact.get("replay_samples"))
        )
    )


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_proxy_replay_quality_source_forbidden_effects"
    if status == "btpc_proxy_replay_quality_review_incomplete":
        return "repair_btpc_proxy_or_replay_quality_inputs"
    if status == "btpc_proxy_replay_quality_review_no_cases":
        return "add_btpc_l2_replay_cases_before_proxy_quality_review"
    return "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_review"


def _forbidden_effects(*artifacts: dict[str, Any]) -> list[str]:
    effects = artifact_source_forbidden_effects(
        artifacts,
        true_keys=SOURCE_SAFETY_TRUE_KEYS,
    )
    proxy_artifact = artifacts[0] if artifacts else {}
    if review_outcome_flag(proxy_artifact, "local_proxy_satisfies_live_required_facts"):
        effects.append(
            "btpc_local_fact_proxy."
            "review_outcome_state.local_proxy_satisfies_live_required_facts"
        )
    replay = artifacts[1] if len(artifacts) > 1 else {}
    if replay.get("live_order_eligible") is True:
        effects.append("btpc_replay_corpus.live_order_eligible")
    for row in _dict_rows(replay.get("replay_samples")):
        fixture = str(row.get("fixture_case") or "unknown")
        if row.get("real_order_allowed") is True:
            effects.append(f"btpc_replay_corpus.{fixture}.real_order_allowed")
        if row.get("exchange_write_allowed") is True:
            effects.append(f"btpc_replay_corpus.{fixture}.exchange_write_allowed")
        if row.get("operation_layer_submit_allowed") is True:
            effects.append(
                f"btpc_replay_corpus.{fixture}.operation_layer_submit_allowed"
            )
    effects.extend(_legacy_authority_mirror_effects(proxy_artifact, replay))
    return sorted(set(effects))


def _legacy_authority_mirror_effects(
    proxy_artifact: dict[str, Any],
    replay_corpus: dict[str, Any],
) -> list[str]:
    effects = legacy_authority_mirror_effects_for_artifacts(
        (("btpc_local_fact_proxy", proxy_artifact),),
        section_names=("safety_invariants", "review_outcome_state", "btpc_state"),
        row_names=("proxy_rows", "action_rows", "source_rows"),
        row_id_keys=("required_fact", "action", "strategy_group_id"),
    )
    effects.extend(
        legacy_authority_mirror_present_errors(
            replay_corpus,
            label_prefix="btpc_replay_corpus.",
        )
    )
    effects.extend(
        legacy_authority_mirror_effects_for_artifacts(
            (("btpc_replay_corpus", replay_corpus),),
            row_names=("replay_samples",),
            row_id_keys=("fixture_case",),
            include_row_name_in_label=False,
        )
    )
    return effects


def _case_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Case | Signal | Proxy status | Decision | Exchange write |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| Case | Signal | Proxy status | Decision | Exchange write |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("fixture_case"),
                row.get("signal_status"),
                row.get("proxy_review_status"),
                row.get("proxy_replay_quality_review_outcome"),
                row.get("exchange_write_authority"),
            )
        )
    return "\n".join(output)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_optional_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_json_object(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btpc-local-fact-proxy-json")
    parser.add_argument(
        "--btpc-replay-corpus-json", default=str(DEFAULT_BTPC_REPLAY_CORPUS_JSON)
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_btpc_proxy_replay_quality_review(
        btpc_local_fact_proxy_artifact=_load_optional_json_object(
            Path(args.btpc_local_fact_proxy_json).expanduser()
        )
        if args.btpc_local_fact_proxy_json
        else {},
        replay_corpus=_load_json_object(Path(args.btpc_replay_corpus_json).expanduser()),
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(render_owner_progress_markdown(artifact), encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
