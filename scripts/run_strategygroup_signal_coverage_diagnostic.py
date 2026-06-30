#!/usr/bin/env python3
"""Build a local read-only signal coverage diagnostic artifact.

This command compares the ACTIVE runtime watcher summary with the broader
StrategyGroup read-only preview shelf. It is meant for no-signal periods: show
whether the selected mainline is genuinely waiting, or whether broader
observe-only shelves are seeing would-enter signals that deserve review.

It does not start runtimes, create candidates, create ExecutionIntents, call
FinalGate, call Operation Layer, call OrderLifecycle, place orders, mutate
server files, or perform exchange writes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_boundary,
)


DEFAULT_RUNTIME_SUMMARY = Path(
    "output/strategygroup-runtime-pilot/current-run-tokyo-reports/latest-summary.json"
)
DEFAULT_EXPANSION_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-signal-coverage-expansion-policy.json"
)


FORBIDDEN_RUNTIME_FLAGS = (
    "creates_shadow_candidate",
    "creates_execution_intent",
    "executable_execution_intent_created",
    "order_created",
    "order_lifecycle_called",
    "calls_order_lifecycle",
    "exchange_write_called",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
)


FORBIDDEN_PREVIEW_FLAGS = (
    "database_connected",
    "pg_observation_written",
    "runtime_resolver_called",
    "shadow_candidate_created",
    "execution_intent_created",
    "order_created",
    "order_lifecycle_called",
    "exchange_write_called",
    "runtime_started",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
)


def build_signal_coverage_diagnostic_artifact(
    *,
    runtime_summary_artifact: dict[str, Any],
    broader_preview_artifact: dict[str, Any],
    source_name: str,
    expansion_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an execution-safe diagnostic artifact from already-built inputs."""

    policy_groups = _as_dict(_as_dict(expansion_policy).get("strategy_groups"))
    runtime_rows = _runtime_signal_rows(runtime_summary_artifact)
    broader_would_enter = [
        _with_policy(row, policy_groups)
        for row in _dict_rows(broader_preview_artifact.get("would_enter_signals"))
    ]
    broader_no_action = [
        _with_policy(row, policy_groups)
        for row in _dict_rows(broader_preview_artifact.get("no_action_signals"))
    ]
    broader_invalid = [
        _with_policy(row, policy_groups)
        for row in _dict_rows(broader_preview_artifact.get("invalid_signals"))
    ]
    runtime_forbidden = _runtime_forbidden_effects(runtime_summary_artifact)
    preview_forbidden = _preview_forbidden_effects(broader_preview_artifact)
    forbidden_effects = sorted(set(runtime_forbidden + preview_forbidden))

    runtime_ready_rows = [
        row for row in runtime_rows if _signal_type(row) in {"would_enter", "ready"}
    ]
    runtime_no_action_rows = [
        row for row in runtime_rows if _signal_type(row) == "no_action"
    ]
    actionable_broader_would_enter = [
        row for row in broader_would_enter if _row_needs_priority_review(row)
    ]
    low_priority_broader_would_enter = [
        row for row in broader_would_enter if not _row_needs_priority_review(row)
    ]
    high_priority_broader_no_action = [
        row for row in broader_no_action if _row_has_review_priority(row)
    ]
    coverage_gap = bool(actionable_broader_would_enter and not runtime_ready_rows)

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_state = "needs_intervention"
        next_step = "stop_and_review_signal_coverage_source_effects"
    elif runtime_ready_rows:
        status = "mainline_runtime_signal_ready"
        owner_state = "processing"
        next_step = "pause_lower_priority_work_and_continue_official_runtime_chain"
    elif coverage_gap:
        status = "mainline_no_signal_broader_would_enter"
        owner_state = "coverage_review_needed"
        next_step = "review_broader_observe_only_signals_before_runtime_scope_change"
    elif low_priority_broader_would_enter and not runtime_ready_rows:
        status = "mainline_no_signal_low_priority_broader_would_enter"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_mainline_and_keep_low_priority_observation_parked"
    elif broader_invalid:
        status = "broader_preview_invalid_needs_review"
        owner_state = "coverage_review_needed"
        next_step = "review_invalid_broader_preview_signals"
    else:
        status = "mainline_and_broader_no_signal"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_waiting_and_replay_rehearsal"

    runtime_summary = _summarize_runtime_rows(runtime_rows)
    broader_summary = _summarize_broader_rows(
        broader_would_enter + broader_no_action + broader_invalid
    )

    return {
        "scope": "strategygroup_signal_coverage_diagnostic",
        "status": status,
        "owner_state": owner_state,
        "source": {
            "runtime_summary_status": runtime_summary_artifact.get("status"),
            "runtime_summary_path_default": str(DEFAULT_RUNTIME_SUMMARY),
            "broader_preview_status": broader_preview_artifact.get("status"),
            "broader_source_requested": source_name,
            "broader_market_source": broader_preview_artifact.get("market_source"),
        },
        "interaction": {
            **non_executing_interaction("L0_local_signal_coverage"),
            "public_market_read_only": source_name == "live_market",
        },
        "checks": {
            "runtime_signal_summary_count": len(runtime_rows),
            "runtime_ready_signal_count": len(runtime_ready_rows),
            "runtime_no_action_signal_count": len(runtime_no_action_rows),
            "broader_candidate_count": _int(
                _as_dict(broader_preview_artifact.get("checks")).get("candidate_count")
            ),
            "broader_current_signal_count": _int(
                _as_dict(broader_preview_artifact.get("checks")).get(
                    "current_signal_count"
                )
            ),
            "broader_would_enter_signal_count": len(broader_would_enter),
            "broader_actionable_would_enter_signal_count": len(
                actionable_broader_would_enter
            ),
            "broader_low_priority_would_enter_signal_count": len(
                low_priority_broader_would_enter
            ),
            "broader_no_action_signal_count": len(broader_no_action),
            "broader_high_priority_no_action_signal_count": len(
                high_priority_broader_no_action
            ),
            "broader_invalid_signal_count": len(broader_invalid),
            "coverage_gap": coverage_gap,
            "forbidden_effects": forbidden_effects,
        },
        "mainline_runtime": {
            "strategy_group_counts": runtime_summary["strategy_group_counts"],
            "symbol_counts": runtime_summary["symbol_counts"],
            "side_counts": runtime_summary["side_counts"],
            "dominant_no_action_reasons": runtime_summary[
                "dominant_no_action_reasons"
            ],
            "ready_signals": [_compact_runtime_signal(row) for row in runtime_ready_rows],
            "no_action_sample": [
                _compact_runtime_signal(row) for row in runtime_no_action_rows[:8]
            ],
        },
        "broader_observation": {
            "strategy_group_counts": broader_summary["strategy_group_counts"],
            "symbol_counts": broader_summary["symbol_counts"],
            "side_counts": broader_summary["side_counts"],
            "dominant_no_action_reasons": broader_summary[
                "dominant_no_action_reasons"
            ],
            "would_enter_signals": [
                _compact_broader_signal(row) for row in broader_would_enter
            ],
            "high_priority_no_action_signals": [
                _compact_broader_signal(row)
                for row in high_priority_broader_no_action[:8]
            ],
            "no_action_sample": [
                _compact_broader_signal(row) for row in broader_no_action[:8]
            ],
            "invalid_signals": [
                _compact_broader_signal(row) for row in broader_invalid
            ],
        },
        "diagnosis": {
            "mainline_runtime_is_waiting": not runtime_ready_rows,
            "broader_observation_has_would_enter": bool(broader_would_enter),
            "broader_observation_has_actionable_would_enter": bool(
                actionable_broader_would_enter
            ),
            "broader_observation_has_low_priority_would_enter": bool(
                low_priority_broader_would_enter
            ),
            "broader_high_priority_no_action_review_available": bool(
                high_priority_broader_no_action
            ),
            "broader_signals_are_observe_only": True,
            "does_not_expand_runtime_scope": True,
            "does_not_authorize_real_order": True,
            "owner_summary": _owner_status_sentence(status),
            "next_step": next_step,
            "recommended_actions": _recommended_actions(status),
        },
        "safety_invariants": non_executing_safety_boundary(
            true_keys=(
                "local_diagnostic_only",
                "broader_signals_are_not_execution_authority",
                "synthetic_or_preview_signal_not_live_submit_authority",
            ),
            false_keys=(
                "server_interaction",
                "server_files_mutated",
                "runtime_started",
                "strategy_parameters_changed",
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
    checks = _as_dict(artifact.get("checks"))
    diagnosis = _as_dict(artifact.get("diagnosis"))
    source = _as_dict(artifact.get("source"))
    broader = _as_dict(artifact.get("broader_observation"))
    mainline = _as_dict(artifact.get("mainline_runtime"))
    status = str(artifact.get("status") or "unknown")

    lines = [
        "# 策略机会覆盖诊断",
        "",
        "## Owner 摘要",
        "",
        f"- Status: `{status}`",
        f"- Owner state: `{artifact.get('owner_state')}`",
        f"- 当前判断：{diagnosis.get('owner_summary')}",
        f"- Runtime source status: `{source.get('runtime_summary_status')}`",
        f"- Broader source: `{source.get('broader_source_requested')}` / `{source.get('broader_market_source')}`",
        f"- Mainline ready signals: `{checks.get('runtime_ready_signal_count', 0)}`",
        f"- Broader would-enter signals: `{checks.get('broader_would_enter_signal_count', 0)}`",
        f"- Broader actionable would-enter signals: `{checks.get('broader_actionable_would_enter_signal_count', 0)}`",
        f"- Broader low-priority would-enter signals: `{checks.get('broader_low_priority_would_enter_signal_count', 0)}`",
        f"- Broader high-priority no-action signals: `{checks.get('broader_high_priority_no_action_signal_count', 0)}`",
        f"- Coverage gap: `{checks.get('coverage_gap')}`",
        "",
        "## 判断",
        "",
        f"- Mainline runtime is waiting: `{diagnosis.get('mainline_runtime_is_waiting')}`",
        f"- Broader observe-only shelf has would-enter signals: `{diagnosis.get('broader_observation_has_would_enter')}`",
        f"- Broader actionable would-enter exists: `{diagnosis.get('broader_observation_has_actionable_would_enter')}`",
        f"- Broader high-priority no-action review available: `{diagnosis.get('broader_high_priority_no_action_review_available')}`",
        "- 宽观察信号只用于机会面诊断，不授权 candidate/auth/FinalGate/Operation Layer。",
        "",
        "## 主线未触发原因",
        "",
        _reason_table(mainline.get("dominant_no_action_reasons") or []),
        "",
        "## 宽观察 Would-Enter 信号",
        "",
        _signal_table(broader.get("would_enter_signals") or []),
        "",
        "## 高优先级 No-Action 信号",
        "",
        _signal_table(broader.get("high_priority_no_action_signals") or []),
        "",
        "## 安全边界",
        "",
        "- Server interaction: `false`",
        "- Server files mutated: `false`",
        "- FinalGate called: `false`",
        "- Operation Layer called: `false`",
        "- Exchange write called: `false`",
        "- Order created: `false`",
        "",
        "## 下一步",
        "",
        f"- `{diagnosis.get('next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _runtime_signal_rows(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _dict_rows(artifact.get("runtime_signal_summaries"))
    if rows:
        return rows
    rows = _dict_rows(artifact.get("runtime_signals"))
    if rows:
        return rows
    return _dict_rows(artifact.get("signal_summaries"))


def _summarize_runtime_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    strategy_counter: Counter[str] = Counter()
    symbol_counter: Counter[str] = Counter()
    side_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    for row in rows:
        strategy_counter[_strategy_id(row)] += 1
        symbol_counter[str(row.get("symbol") or "unknown")] += 1
        side_counter[str(row.get("side") or row.get("signal_side") or "unknown")] += 1
        if _signal_type(row) == "no_action":
            reason_counter.update(_reason_codes(row))
    return {
        "strategy_group_counts": _counter_dict(strategy_counter),
        "symbol_counts": _counter_dict(symbol_counter),
        "side_counts": _counter_dict(side_counter),
        "dominant_no_action_reasons": _top_reason_counts(reason_counter),
    }


def _summarize_broader_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    strategy_counter: Counter[str] = Counter()
    symbol_counter: Counter[str] = Counter()
    side_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    for row in rows:
        strategy_counter[str(row.get("strategy_group_id") or "unknown")] += 1
        symbol_counter[str(row.get("symbol") or "unknown")] += 1
        side_counter[str(row.get("side") or "unknown")] += 1
        if row.get("signal_type") == "no_action":
            reason_counter.update(_reason_codes(row))
    return {
        "strategy_group_counts": _counter_dict(strategy_counter),
        "symbol_counts": _counter_dict(symbol_counter),
        "side_counts": _counter_dict(side_counter),
        "dominant_no_action_reasons": _top_reason_counts(reason_counter),
    }


def _compact_runtime_signal(row: dict[str, Any]) -> dict[str, Any]:
    signal_summary = _as_dict(row.get("signal_summary"))
    return {
        "runtime_instance_id": row.get("runtime_instance_id"),
        "strategy_group_id": _strategy_id(row),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side") or row.get("signal_side"),
        "signal_type": _signal_type(row),
        "confidence": _confidence(row),
        "reason_codes": _reason_codes(row),
        "human_summary": row.get("human_summary") or signal_summary.get("human_summary"),
        "status": row.get("status"),
    }


def _compact_broader_signal(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "strategy_group_id": row.get("strategy_group_id"),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "signal_type": row.get("signal_type"),
        "confidence": row.get("confidence"),
        "reason_codes": _reason_codes(row),
        "human_summary": row.get("human_summary"),
        "coverage_review_priority": row.get("coverage_review_priority"),
        "policy_l2_readiness": row.get("policy_l2_readiness"),
        "policy_recommended_action": row.get("policy_recommended_action"),
        "not_order": row.get("not_order"),
        "not_execution_intent": row.get("not_execution_intent"),
        "no_execution_permission": row.get("no_execution_permission"),
        "no_order_permission": row.get("no_order_permission"),
        "no_runtime_start": row.get("no_runtime_start"),
    }


def _with_policy(row: dict[str, Any], policy_groups: dict[str, Any]) -> dict[str, Any]:
    strategy_group_id = str(row.get("strategy_group_id") or "")
    policy = _as_dict(policy_groups.get(strategy_group_id))
    if not policy:
        return dict(row)
    enriched = dict(row)
    enriched["coverage_review_priority"] = str(
        policy.get("coverage_review_priority") or "unknown"
    )
    enriched["policy_l2_readiness"] = str(policy.get("l2_readiness") or "unknown")
    enriched["policy_recommended_action"] = str(
        policy.get("recommended_action") or "require_policy_review"
    )
    return enriched


def _row_needs_priority_review(row: dict[str, Any]) -> bool:
    priority = str(row.get("coverage_review_priority") or "unknown")
    readiness = str(row.get("policy_l2_readiness") or "unknown")
    if priority in {"P2", "P2_low", "low"}:
        return False
    if readiness == "blocked_parked_negative_evidence":
        return False
    return True


def _row_has_review_priority(row: dict[str, Any]) -> bool:
    priority = str(row.get("coverage_review_priority") or "unknown")
    return priority in {"P0_5", "P1"}


def _signal_type(row: dict[str, Any]) -> str:
    summary = _as_dict(row.get("signal_summary"))
    return str(row.get("signal_type") or summary.get("signal_type") or "unknown")


def _confidence(row: dict[str, Any]) -> Any:
    summary = _as_dict(row.get("signal_summary"))
    return row.get("confidence") or summary.get("confidence")


def _reason_codes(row: dict[str, Any]) -> list[str]:
    summary = _as_dict(row.get("signal_summary"))
    values = row.get("reason_codes") or summary.get("reason_codes") or []
    return [str(value) for value in values if str(value or "").strip()]


def _strategy_id(row: dict[str, Any]) -> str:
    return str(
        row.get("strategy_group_id")
        or row.get("strategy_family_id")
        or row.get("strategy_id")
        or "unknown"
    )


def _runtime_forbidden_effects(artifact: dict[str, Any]) -> list[str]:
    effects = []
    for key in FORBIDDEN_RUNTIME_FLAGS:
        if artifact.get(key) is True:
            effects.append(f"runtime.{key}")
    for item in artifact.get("forbidden_effects") or []:
        effects.append(f"runtime.{item}")
    for item in _as_dict(artifact.get("checks")).get("forbidden_effects") or []:
        effects.append(f"runtime.checks.{item}")
    return sorted(set(str(item) for item in effects if item))


def _preview_forbidden_effects(artifact: dict[str, Any]) -> list[str]:
    effects = []
    checks = _as_dict(artifact.get("checks"))
    safety = _as_dict(artifact.get("safety_invariants"))
    interaction = _as_dict(artifact.get("interaction"))
    for item in checks.get("forbidden_effects") or []:
        effects.append(f"preview.checks.{item}")
    for key in FORBIDDEN_PREVIEW_FLAGS:
        if safety.get(key) is True:
            effects.append(f"preview.safety.{key}")
    for key in (
        "creates_shadow_candidate",
        "creates_execution_intent",
        "places_order",
        "calls_order_lifecycle",
        "withdrawal_or_transfer_requested",
    ):
        if interaction.get(key) is True:
            effects.append(f"preview.interaction.{key}")
    return sorted(set(str(item) for item in effects if item))


def _recommended_actions(status: str) -> list[str]:
    if status == "blocked_forbidden_effect":
        return ["stop_and_review_source_artifact_before_any_runtime_action"]
    if status == "mainline_runtime_signal_ready":
        return ["continue_official_runtime_chain", "pause_low_priority_diagnostics"]
    if status == "mainline_no_signal_broader_would_enter":
        return [
            "review_broader_signal_quality",
            "decide_future_strategygroup_scope_or_observe_only_promotion",
            "keep_current_live_submit_path_waiting_for_selected_runtime_signal",
        ]
    if status == "mainline_no_signal_low_priority_broader_would_enter":
        return [
            "keep_low_priority_observation_parked",
            "continue_waiting_for_selected_runtime_signal",
            "continue_replay_review_for_higher_priority_lanes",
        ]
    if status == "broader_preview_invalid_needs_review":
        return ["review_broader_preview_adapter_or_signal_contract"]
    return ["continue_monitoring", "run_replay_or_synthetic_rehearsal"]


def _owner_status_sentence(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "诊断来源出现禁止副作用标记，停止后续动作并检查来源。"
    if status == "mainline_runtime_signal_ready":
        return "主线已经出现可处理信号，应暂停低优先级任务并进入官方实盘链路。"
    if status == "mainline_no_signal_broader_would_enter":
        return "主线暂未触发，但宽观察面已有观察级机会，需要评估是否扩展策略覆盖。"
    if status == "mainline_no_signal_low_priority_broader_would_enter":
        return "主线暂未触发，宽观察面只有低优先级或已停放机会，继续等待更高质量机会。"
    if status == "broader_preview_invalid_needs_review":
        return "宽观察面出现无效信号，需要检查策略适配或信号契约。"
    return "主线和宽观察面都未触发，当前属于健康等待机会。"


def _reason_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Reason | Count |\n| --- | --- |\n| none | 0 |"
    output = ["| Reason | Count |", "| --- | --- |"]
    for row in rows:
        output.append(f"| `{row.get('reason_code')}` | {row.get('count')} |")
    return "\n".join(output)


def _signal_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Symbol | Side | Confidence | Reason |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| StrategyGroup | Symbol | Side | Confidence | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        reasons = ", ".join(str(value) for value in row.get("reason_codes") or [])
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("side"),
                row.get("confidence"),
                reasons,
            )
        )
    return "\n".join(output)


def _top_reason_counts(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"reason_code": reason, "count": count}
        for reason, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[
            :8
        ]
    ]


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_runtime_summary_or_missing(path: Path) -> dict[str, Any]:
    try:
        return _load_json_object(path)
    except FileNotFoundError:
        return {
            "status": "runtime_summary_missing",
            "runtime_signal_summaries": [],
            "source": {
                "missing_path": str(path),
                "missing_is_not_live_signal": True,
            },
            "safety_invariants": {
                "local_missing_runtime_summary_placeholder": True,
                "server_files_mutated": False,
                "runtime_started": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "order_created": False,
                "exchange_write_called": False,
                "withdrawal_or_transfer_created": False,
            },
        }


def _build_preview(source_name: str) -> dict[str, Any]:
    from scripts.preview_strategy_group_readonly_observation import build_preview_artifact

    return build_preview_artifact(source_name=source_name)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-summary-json",
        default=str(DEFAULT_RUNTIME_SUMMARY),
        help="Local runtime summary artifact to compare against broader preview.",
    )
    parser.add_argument(
        "--source",
        choices=["sample", "local_sqlite_read_only", "live_market"],
        default="local_sqlite_read_only",
        help="Read-only broader strategy preview source.",
    )
    parser.add_argument("--broader-preview-json")
    parser.add_argument(
        "--expansion-policy-json",
        default=str(DEFAULT_EXPANSION_POLICY_JSON),
    )
    parser.add_argument("--output-json")
    parser.add_argument("--output-owner-progress")
    args = parser.parse_args(argv)

    runtime_artifact = _load_runtime_summary_or_missing(
        Path(args.runtime_summary_json).expanduser()
    )
    if args.broader_preview_json:
        preview_artifact = _load_json_object(Path(args.broader_preview_json).expanduser())
    else:
        preview_artifact = _build_preview(args.source)

    artifact = build_signal_coverage_diagnostic_artifact(
        runtime_summary_artifact=runtime_artifact,
        broader_preview_artifact=preview_artifact,
        source_name=args.source,
        expansion_policy=_load_json_object(Path(args.expansion_policy_json).expanduser()),
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
