"""Thin product-shape adapters for :mod:`current_truth_reducer`.

The functions here deliberately copy no blocker precedence.  They retain
existing read-model presentation fields while replacing every operational
decision field with the one shared bundle decision.
"""

from __future__ import annotations

from typing import Any

from src.application.current_truth_reducer import (
    CurrentTruthBundle,
    LaneOperationalDecision,
    TradeOperationalDecision,
)
from src.domain.runtime_semantic_kernel import RuntimeState


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
    by_lane = {item.lane_identity.key: item for item in bundle.lane_decisions}
    trades_by_lane = _trade_decision_by_lane(bundle)
    return {
        **table,
        "rows": [
            _adapt_daily_row(
                row,
                trades_by_lane.get(_lane_key(row)) or by_lane.get(_lane_key(row)),
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
    trade = _highest_priority_trade(bundle)
    if trade is not None:
        return {
            **goal,
            "status": trade.owner_state,
            "plain_language_stage": trade.owner_message,
            "first_blocker": trade.first_blocker,
            "next_action": trade.next_system_action,
            "owner_action_required": trade.owner_action_required,
            "owner_state": {
                **_as_dict(goal.get("owner_state")),
                "status": trade.owner_state,
                "message": trade.owner_message,
            },
            "evidence": {
                **_as_dict(goal.get("evidence")),
                "trade_ticket_id": trade.ticket_id,
                "current_truth_bundle": _bundle_lineage(bundle),
            },
            "current_truth_bundle": _bundle_lineage(bundle),
        }
    # A deliberately empty test/diagnostic snapshot has no operational scope.
    if not bundle.lane_decisions:
        return goal
    blockers = _blocker_counts(bundle)
    healthy_wait = bool(bundle.lane_decisions) and blockers == {"market_wait_validated": len(bundle.lane_decisions)}
    lane = _highest_priority_lane(bundle)
    assert lane is not None
    return {
        **goal,
        "status": "waiting_for_signal" if healthy_wait else "missing_fact",
        "plain_language_stage": "等待市场机会" if healthy_wait else "前置事实不完整",
        "first_blocker": lane.first_blocker,
        "next_action": lane.next_system_action,
        "owner_action_required": lane.owner_action_required,
        "evidence": {
            **_as_dict(goal.get("evidence")),
            "pg_blocker_counts": blockers,
            "current_truth_bundle": _bundle_lineage(bundle),
        },
        "current_truth_bundle": _bundle_lineage(bundle),
    }


def adapt_monitor_status(
    status: dict[str, Any], *, bundle: CurrentTruthBundle
) -> dict[str, Any]:
    trade = _highest_priority_trade(bundle)
    if trade is not None:
        return {
            **status,
            "status": trade.owner_state,
            "owner_message": trade.owner_message,
            "first_blocker": trade.first_blocker,
            "next_action": trade.next_system_action,
            "owner_action_required": trade.owner_action_required,
            "ticket_id": trade.ticket_id,
            "current_truth_semantic_fingerprint": trade.semantic_fingerprint,
            "current_truth_bundle": _bundle_lineage(bundle),
        }
    if not bundle.lane_decisions:
        return status
    lane = _highest_priority_lane(bundle)
    assert lane is not None
    healthy_wait = all(
        item.first_blocker == "market_wait_validated"
        for item in bundle.lane_decisions
    )
    return {
        **status,
        "status": (
            "waiting_for_opportunity" if healthy_wait else "temporarily_unavailable"
        ),
        "first_blocker": lane.first_blocker,
        "next_action": lane.next_system_action,
        "owner_action_required": lane.owner_action_required,
        "current_truth_semantic_fingerprint": lane.semantic_fingerprint,
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


def _adapt_daily_row(
    row: dict[str, Any],
    decision: LaneOperationalDecision | TradeOperationalDecision | None,
) -> dict[str, Any]:
    if decision is None:
        return row
    if isinstance(decision, TradeOperationalDecision):
        return {
            **row,
            "first_blocker": decision.first_blocker,
            "next_engineering_action": decision.next_system_action,
            "owner_state": decision.owner_state,
            "owner_message": decision.owner_message,
            "owner_action_required": (
                "yes" if decision.owner_action_required else "no"
            ),
            "ticket_id": decision.ticket_id,
            "current_truth_semantic_fingerprint": decision.semantic_fingerprint,
        }
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


def _trade_decision_by_lane(
    bundle: CurrentTruthBundle,
) -> dict[tuple[str, str, str], TradeOperationalDecision]:
    result: dict[tuple[str, str, str], TradeOperationalDecision] = {}
    for item in bundle.trade_decisions:
        key = (item.strategy_group_id, item.symbol, item.side)
        current = result.get(key)
        if current is None or _trade_priority(item) < _trade_priority(current):
            result[key] = item
    return result


def _highest_priority_trade(
    bundle: CurrentTruthBundle,
) -> TradeOperationalDecision | None:
    active = [
        item for item in bundle.trade_decisions if item.owner_state != "completed"
    ]
    if active:
        return min(active, key=_trade_priority)
    if bundle.lane_decisions:
        return None
    return min(bundle.trade_decisions, key=_trade_priority, default=None)


def _highest_priority_lane(
    bundle: CurrentTruthBundle,
) -> LaneOperationalDecision | None:
    return min(bundle.lane_decisions, key=_lane_priority, default=None)


def _trade_priority(item: TradeOperationalDecision) -> tuple[int, str]:
    if item.owner_state == "needs_intervention":
        rank = 0
    elif item.state is RuntimeState.OUTCOME_UNKNOWN:
        rank = 1
    elif item.protection_state == "initial_stop_pending":
        rank = 2
    elif item.owner_state == "running":
        rank = 3
    elif item.owner_state == "completed":
        rank = 4
    else:
        rank = 2
    return rank, item.ticket_id


def _lane_priority(
    item: LaneOperationalDecision,
) -> tuple[int, str, tuple[str, str, str]]:
    if item.owner_action_required:
        rank = 0
    elif item.current_issue:
        rank = 1
    elif item.first_blocker == "action_time_preflight_ready":
        rank = 2
    elif item.first_blocker == "market_wait_validated":
        rank = 4
    else:
        rank = 3
    return rank, item.first_blocker, item.lane_identity.key


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
