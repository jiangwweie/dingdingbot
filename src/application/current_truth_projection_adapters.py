"""Thin product-shape adapters for :mod:`current_truth_reducer`.

The functions here deliberately copy no blocker precedence.  They retain
existing read-model presentation fields while replacing every operational
decision field with the one shared bundle decision.
"""

from __future__ import annotations

from typing import Any

from src.application.current_truth_reducer import CurrentTruthBundle, LaneOperationalDecision


def adapt_candidate_pool(
    candidate_pool: dict[str, Any], *, bundle: CurrentTruthBundle
) -> dict[str, Any]:
    decisions = {
        item.lane_identity.key: item for item in bundle.lane_decisions
    }
    rows = [
        _adapt_lane_row(row, decisions.get(_lane_key(row)))
        for row in _rows(candidate_pool.get("symbol_readiness_rows"))
    ]
    candidate_rows: list[dict[str, Any]] = []
    for row in _rows(candidate_pool.get("candidate_rows")):
        key = (
            str(row.get("strategy_group_id") or ""),
            str(row.get("selected_symbol") or ""),
            str(row.get("side") or ""),
        )
        decision = decisions.get(key)
        candidate_rows.append(_adapt_candidate_row(row, decision))
    return {
        **candidate_pool,
        "symbol_readiness_rows": rows,
        "candidate_rows": candidate_rows,
        "current_truth_bundle": _bundle_lineage(bundle),
    }


def adapt_daily_table(
    table: dict[str, Any], *, bundle: CurrentTruthBundle
) -> dict[str, Any]:
    decisions = _best_decision_by_group(bundle)
    by_lane = {item.lane_identity.key: item for item in bundle.lane_decisions}
    return {
        **table,
        "rows": [
            _adapt_daily_row(
                row,
                by_lane.get(_lane_key(row))
                or decisions.get(str(row.get("strategy_group_id") or "")),
            )
            for row in _rows(table.get("rows"))
        ],
        "current_truth_bundle": _bundle_lineage(bundle),
    }


def adapt_tradeability(
    decision: dict[str, Any], *, bundle: CurrentTruthBundle
) -> dict[str, Any]:
    by_group = _best_decision_by_group(bundle)
    rows = [
        _adapt_tradeability_row(row, by_group.get(str(row.get("strategy_group_id") or "")))
        for row in _rows(decision.get("decision_rows"))
    ]
    return {
        **decision,
        "decision_rows": rows,
        "current_truth_bundle": _bundle_lineage(bundle),
    }


def adapt_goal_status(
    goal: dict[str, Any], *, bundle: CurrentTruthBundle
) -> dict[str, Any]:
    # A deliberately empty test/diagnostic snapshot has no operational scope
    # to reduce.  Preserve the caller's non-authority shape in that case.
    if not bundle.lane_decisions:
        return goal
    blockers = _blocker_counts(bundle)
    healthy_wait = bool(bundle.lane_decisions) and blockers == {"market_wait_validated": len(bundle.lane_decisions)}
    return {
        **goal,
        "status": "waiting_for_signal" if healthy_wait else "missing_fact",
        "plain_language_stage": "等待市场机会" if healthy_wait else "前置事实不完整",
        "evidence": {
            **_as_dict(goal.get("evidence")),
            "pg_blocker_counts": blockers,
            "current_truth_bundle": _bundle_lineage(bundle),
        },
        "current_truth_bundle": _bundle_lineage(bundle),
    }


def _adapt_lane_row(row: dict[str, Any], decision: LaneOperationalDecision | None) -> dict[str, Any]:
    if decision is None:
        return row
    return {
        **row,
        "first_blocker": decision.first_blocker,
        "next_action": decision.next_system_action,
        "owner_action_required": "yes" if decision.owner_action_required else "no",
        "current_truth_semantic_fingerprint": decision.semantic_fingerprint,
    }


def _adapt_candidate_row(row: dict[str, Any], decision: LaneOperationalDecision | None) -> dict[str, Any]:
    if decision is None:
        return row
    return {
        **row,
        "first_blocker": decision.first_blocker,
        "blocker_owner": decision.blocker_owner,
        "next_engineering_action": decision.next_system_action,
        "owner_action_required": "yes" if decision.owner_action_required else "no",
        "current_truth_semantic_fingerprint": decision.semantic_fingerprint,
    }


def _adapt_daily_row(row: dict[str, Any], decision: LaneOperationalDecision | None) -> dict[str, Any]:
    if decision is None:
        return row
    return {
        **row,
        "symbol": decision.lane_identity.symbol,
        "side": decision.lane_identity.side,
        "first_blocker": decision.first_blocker,
        "next_engineering_action": decision.next_system_action,
        "owner_action_required": "yes" if decision.owner_action_required else "no",
        "current_truth_semantic_fingerprint": decision.semantic_fingerprint,
    }


def _adapt_tradeability_row(row: dict[str, Any], decision: LaneOperationalDecision | None) -> dict[str, Any]:
    if decision is None:
        return row
    return {
        **row,
        "first_blocker_class": decision.first_blocker,
        "first_blocker_detail": "current_truth_bundle",
        "owner_action_required": decision.owner_action_required,
        "current_truth_semantic_fingerprint": decision.semantic_fingerprint,
    }


def _best_decision_by_group(bundle: CurrentTruthBundle) -> dict[str, LaneOperationalDecision]:
    result: dict[str, LaneOperationalDecision] = {}
    for item in bundle.lane_decisions:
        current = result.get(item.lane_identity.strategy_group_id)
        if current is None or (item.first_blocker, item.lane_identity.symbol, item.lane_identity.side) < (current.first_blocker, current.lane_identity.symbol, current.lane_identity.side):
            result[item.lane_identity.strategy_group_id] = item
    return result


def _blocker_counts(bundle: CurrentTruthBundle) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in bundle.lane_decisions:
        counts[item.first_blocker] = counts.get(item.first_blocker, 0) + 1
    return dict(sorted(counts.items()))


def _bundle_lineage(bundle: CurrentTruthBundle) -> dict[str, str]:
    return {
        "bundle_run_id": bundle.bundle_run_id,
        "input_watermark_digest": bundle.input_watermark_digest,
        "schema": bundle.schema_name,
    }


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row.get("strategy_group_id") or ""), str(row.get("symbol") or ""), str(row.get("side") or "")


def _rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
