#!/usr/bin/env python3
"""Build the BTPC L2 proxy-aware replay quality review packet.

This command consumes the local BTPC fact-proxy review plus the BTPC L2 replay
corpus and produces case-level quality decisions. It is a P0.5 review artifact:
it can make would-enter/no-action/stale/conflict replay outcomes easier to
compare, but it cannot satisfy live RequiredFacts, change tiers, call
FinalGate, call Operation Layer, or place orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BTPC_LOCAL_FACT_PROXY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-local-fact-proxy-review.json"
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
    btpc_local_fact_proxy_packet: dict[str, Any],
    replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(
        btpc_local_fact_proxy_packet,
        replay_corpus,
    )
    proxy_ready = _proxy_ready(btpc_local_fact_proxy_packet)
    replay_boundary_ok = _replay_boundary_ok(replay_corpus)
    case_rows = _case_rows(
        replay_corpus=replay_corpus,
        btpc_local_fact_proxy_packet=btpc_local_fact_proxy_packet,
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

    decision_counts: dict[str, int] = {}
    for row in case_rows:
        decision = str(row.get("proxy_replay_quality_decision") or "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

    return {
        "schema": "brc.btpc_proxy_replay_quality_review.v1",
        "scope": "btpc_proxy_replay_quality_review",
        "status": status,
        "source_status": {
            "btpc_local_fact_proxy_review": btpc_local_fact_proxy_packet.get("status"),
            "replay_corpus": replay_corpus.get("schema_version"),
        },
        "interaction": {
            "level": "L0_local_btpc_proxy_replay_quality_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
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
                if row.get("proxy_replay_quality_decision")
                in {
                    "revise_freshness_or_classifier_before_l2_promotion",
                    "revise_conflict_disable_before_l2_promotion",
                }
            ),
            "keep_observing_count": sum(
                1
                for row in case_rows
                if row.get("proxy_replay_quality_decision")
                in {
                    "keep_observing_l2_shadow_with_proxy_context",
                    "keep_waiting_for_market_no_action_baseline",
                }
            ),
            "live_required_fact_satisfied_count": 0,
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "decision_counts": dict(sorted(decision_counts.items())),
        "case_rows": case_rows,
        "decision": {
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
        "operator_command_plan": {
            "not_executed": True,
            "starts_runtime": False,
            "changes_strategy_parameters": False,
            "changes_tier_policy": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "calls_final_gate": False,
            "calls_operation_layer": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "local_btpc_proxy_replay_quality_review_only": True,
            "proxy_replay_is_not_live_required_fact": True,
            "input_is_not_execution_authority": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "l2_promotion_authorized": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
            "does_not_lower_owner_selected_leverage": True,
            "does_not_change_live_profile_or_sizing_defaults": True,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def build_owner_progress_markdown(packet: dict[str, Any]) -> str:
    counts = _as_dict(packet.get("counts"))
    decision = _as_dict(packet.get("decision"))
    lines = [
        "# BTPC Proxy Replay Quality Review",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Replay cases: `{counts.get('replay_case_count', 0)}`",
        f"- Proxy-reviewable would-enter: `{counts.get('proxy_reviewable_would_enter_count', 0)}`",
        f"- Missing-derivatives cases resolved for L2 review only: `{counts.get('proxy_resolved_missing_derivatives_context_count', 0)}`",
        "- Live RequiredFacts satisfied by proxy replay: `false`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Case Rows",
        "",
        _case_table(_dict_rows(packet.get("case_rows"))),
        "",
        "## Next",
        "",
        f"- `{decision.get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _case_rows(
    *,
    replay_corpus: dict[str, Any],
    btpc_local_fact_proxy_packet: dict[str, Any],
    proxy_ready: bool,
) -> list[dict[str, Any]]:
    proxy_facts = [
        str(row.get("required_fact"))
        for row in _dict_rows(btpc_local_fact_proxy_packet.get("proxy_rows"))
        if row.get("l2_quality_proxy_ready") is True
    ]
    rows: list[dict[str, Any]] = []
    for sample in _dict_rows(replay_corpus.get("replay_samples")):
        fixture_case = str(sample.get("fixture_case") or "unknown")
        signal_status = str(sample.get("signal_status") or "unknown")
        decision, proxy_status, proxy_effect = _case_decision(
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
                "proxy_replay_quality_decision": decision,
                "l2_shadow_observation_can_continue": proxy_ready,
                "l2_promotion_authority": False,
                "l4_scope_change_recommended": False,
                "live_required_facts_satisfied": False,
                "real_order_authority": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            }
        )
    return rows


def _case_decision(
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


def _proxy_ready(packet: dict[str, Any]) -> bool:
    counts = _as_dict(packet.get("counts"))
    decision = _as_dict(packet.get("decision"))
    expected = _int(counts.get("expected_proxy_fact_count"))
    attached = _int(counts.get("proxy_attached_count"))
    return (
        packet.get("status") == "btpc_local_fact_proxy_review_ready"
        and expected > 0
        and attached == expected
        and decision.get("local_proxy_can_feed_replay_review") is True
        and decision.get("local_proxy_satisfies_live_required_facts") is False
    )


def _replay_boundary_ok(packet: dict[str, Any]) -> bool:
    return (
        packet.get("live_order_eligible") is not True
        and all(
            row.get("real_order_allowed") is not True
            and row.get("exchange_write_allowed") is not True
            and row.get("operation_layer_submit_allowed") is not True
            and row.get("not_execution_authority") is True
            for row in _dict_rows(packet.get("replay_samples"))
        )
    )


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_proxy_replay_quality_source_forbidden_effects"
    if status == "btpc_proxy_replay_quality_review_incomplete":
        return "repair_btpc_proxy_or_replay_quality_inputs"
    if status == "btpc_proxy_replay_quality_review_no_cases":
        return "add_btpc_l2_replay_cases_before_proxy_quality_review"
    return "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision"


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for index, packet in enumerate(packets):
        safety = _as_dict(packet.get("safety_invariants"))
        for item in safety.get("source_forbidden_effects") or []:
            effects.append(f"packet_{index}.{item}")
        for key in (
            "server_files_mutated",
            "runtime_started",
            "strategy_parameters_changed",
            "tier_policy_changed",
            "shadow_candidate_created",
            "execution_intent_created",
            "final_gate_called",
            "operation_layer_called",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "withdrawal_or_transfer_created",
        ):
            if safety.get(key) is True:
                effects.append(f"packet_{index}.safety.{key}")
    proxy_packet = packets[0] if packets else {}
    proxy_decision = _as_dict(proxy_packet.get("decision"))
    if proxy_decision.get("local_proxy_satisfies_live_required_facts") is True:
        effects.append("btpc_local_fact_proxy.local_proxy_satisfies_live_required_facts")
    replay = packets[1] if len(packets) > 1 else {}
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
    return sorted(set(effects))


def _case_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Case | Signal | Proxy status | Decision | Real order |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| Case | Signal | Proxy status | Decision | Real order |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("fixture_case"),
                row.get("signal_status"),
                row.get("proxy_review_status"),
                row.get("proxy_replay_quality_decision"),
                row.get("real_order_authority"),
            )
        )
    return "\n".join(output)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


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
    parser.add_argument(
        "--btpc-local-fact-proxy-json",
        default=str(DEFAULT_BTPC_LOCAL_FACT_PROXY_JSON),
    )
    parser.add_argument(
        "--btpc-replay-corpus-json", default=str(DEFAULT_BTPC_REPLAY_CORPUS_JSON)
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_btpc_proxy_replay_quality_review(
        btpc_local_fact_proxy_packet=_load_json_object(
            Path(args.btpc_local_fact_proxy_json).expanduser()
        ),
        replay_corpus=_load_json_object(Path(args.btpc_replay_corpus_json).expanduser()),
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(build_owner_progress_markdown(packet), encoding="utf-8")
    print(payload)
    return 0 if packet["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
