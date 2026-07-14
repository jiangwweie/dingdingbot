#!/usr/bin/env python3
"""Run a deterministic research-only exit-policy sensitivity rehearsal.

The command intentionally writes no runtime files.  Its built-in paths certify
bar ordering, costs, long/short symmetry, and policy sensitivity; they are not
historical market evidence and cannot grant production authority.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.domain.exit_policy_replay import (
    ExitPolicyCandidate,
    ReplayBar,
    ReplayTrade,
    aggregate_replay_results,
    replay_trade,
)


ACTIVE_POLICY_RECOMMENDATIONS: tuple[dict[str, Any], ...] = (
    {
        "strategy_group_id": "CPM-RO-001",
        "event_spec_id": "CPM-LONG",
        "side": "long",
        "timeframe": "1h",
        "structure_window_bars": 3,
        "atr_buffer_multiple": "0.5",
        "max_holding_bars": 24,
        "invalidation": "close_below_or_equal:reclaim_level",
    },
    {
        "strategy_group_id": "MPG-001",
        "event_spec_id": "MPG-LONG",
        "side": "long",
        "timeframe": "1h",
        "structure_window_bars": 3,
        "atr_buffer_multiple": "0.75",
        "max_holding_bars": 12,
        "invalidation": "close_below_or_equal:momentum_persistence_base",
    },
    {
        "strategy_group_id": "MI-001",
        "event_spec_id": "MI-LONG",
        "side": "long",
        "timeframe": "1h",
        "structure_window_bars": 2,
        "atr_buffer_multiple": "0.5",
        "max_holding_bars": 8,
        "invalidation": "close_below_or_equal:impulse_base",
    },
    {
        "strategy_group_id": "SOR-001",
        "event_spec_id": "SOR-LONG",
        "side": "long",
        "timeframe": "15m",
        "structure_window_bars": 4,
        "atr_buffer_multiple": "0.5",
        "max_holding_bars": 96,
        "invalidation": "close_below_or_equal:opening_range_high",
    },
    {
        "strategy_group_id": "SOR-001",
        "event_spec_id": "SOR-SHORT",
        "side": "short",
        "timeframe": "15m",
        "structure_window_bars": 4,
        "atr_buffer_multiple": "0.5",
        "max_holding_bars": 288,
        "invalidation": "close_above_or_equal:opening_range_low",
    },
    {
        "strategy_group_id": "BRF2-001",
        "event_spec_id": "BRF2-SHORT",
        "side": "short",
        "timeframe": "1h",
        "structure_window_bars": 3,
        "atr_buffer_multiple": "0.75",
        "max_holding_bars": 6,
        "invalidation": "close_above_or_equal:rebound_high",
    },
)


def build_decision_payload() -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for recommendation in ACTIVE_POLICY_RECOMMENDATIONS:
        candidates = _candidate_grid(recommendation)
        trades = _representative_paths(recommendation)
        comparisons = []
        for candidate in candidates:
            results = tuple(replay_trade(trade, candidate) for trade in trades)
            comparisons.append(
                {
                    "candidate": _jsonable(asdict(candidate)),
                    "aggregate": _jsonable(asdict(aggregate_replay_results(results))),
                    "trade_results": [_jsonable(asdict(item)) for item in results],
                }
            )
        decisions.append(
            {
                **recommendation,
                "recommended_candidate_id": candidates[0].candidate_id,
                "comparison": comparisons,
                "selection_basis": (
                    "strategy semantic horizon plus conservative representative-path "
                    "sensitivity; not historical profitability proof"
                ),
            }
        )
    payload: dict[str, Any] = {
        "schema": "brc.research.exit_policy_decision.v1",
        "status": "research_only",
        "as_of": "2026-07-15",
        "data_manifest": {
            "historical_sources": [
                "docs/strategy-research/strategygroup-release-rereview-20260714.md",
                "docs/strategy-research/sor-branch-eligibility-time-stop-20260616.md",
                "docs/strategy-research/mpg-member-drawdown-disable-addendum-20260616.md",
                "research/strategy-candidate-mining-replay-validation/packs/MI-ASIA-RS-IMPULSE-001-handoff-draft.json",
                "research/strategy-candidate-mining-replay-validation/packs/BRF2-QUALITY-BASKET-SHORT-001-handoff-draft.json",
            ],
            "path_data_kind": "deterministic_representative_scenarios",
            "historical_market_path_replay": False,
            "live_outcome_count_used_for_parameter_optimization": 0,
            "reason": "current n=3 SOR outcomes are insufficient for parameter rewrite",
        },
        "shared_contract": {
            "tp1_reward_multiple": "1",
            "tp1_quantity_fraction": "0.5",
            "tp1_execution_style": "limit_gtc",
            "market_fallback_allowed": False,
            "reward_basis": "actual_entry_r",
            "runner_floor": "runner_leg_cost_adjusted_break_even",
            "exit_fee_basis": "conservative_taker",
            "slippage_buffer_ticks": 2,
            "minimum_improvement_ticks": 2,
            "hard_tp2": False,
        },
        "decisions": decisions,
        "authority_boundary": {
            "runtime_registry_mutation": False,
            "owner_policy_mutation": False,
            "finalgate_input": False,
            "operation_layer_input": False,
            "exchange_write": False,
            "real_order_authority": False,
        },
    }
    payload["decision_hash"] = _payload_hash(payload)
    return payload


def _candidate_grid(recommendation: dict[str, Any]) -> tuple[ExitPolicyCandidate, ...]:
    base_window = int(recommendation["structure_window_bars"])
    base_buffer = Decimal(str(recommendation["atr_buffer_multiple"]))
    common = {
        "side": recommendation["side"],
        "tp1_reward_multiple": Decimal("1"),
        "tp1_quantity_fraction": Decimal("0.5"),
        "tp1_execution_style": "limit_gtc",
        "tp1_fill_fraction": Decimal("1"),
        "entry_fee_rate": Decimal("0.0004"),
        "maker_fee_rate": Decimal("0.0002"),
        "taker_fee_rate": Decimal("0.0005"),
        "slippage_ticks": 2,
        "minimum_improvement_ticks": 2,
        "max_holding_bars": int(recommendation["max_holding_bars"]),
    }
    prefix = f"{recommendation['strategy_group_id']}:{recommendation['event_spec_id']}"
    return (
        ExitPolicyCandidate(
            candidate_id=f"{prefix}:recommended-v1",
            structure_window_bars=base_window,
            atr_buffer_multiple=base_buffer,
            **common,
        ),
        ExitPolicyCandidate(
            candidate_id=f"{prefix}:tight-sensitivity",
            structure_window_bars=max(1, base_window - 1),
            atr_buffer_multiple=max(Decimal("0"), base_buffer - Decimal("0.25")),
            **common,
        ),
        ExitPolicyCandidate(
            candidate_id=f"{prefix}:loose-sensitivity",
            structure_window_bars=base_window + 1,
            atr_buffer_multiple=base_buffer + Decimal("0.25"),
            **common,
        ),
    )


def _representative_paths(recommendation: dict[str, Any]) -> tuple[ReplayTrade, ...]:
    side = recommendation["side"]
    is_long = side == "long"
    entry = Decimal("100")
    stop = Decimal("95") if is_long else Decimal("105")
    strategy = recommendation["strategy_group_id"]
    event = recommendation["event_spec_id"]

    def bar(
        index: int,
        open_: str,
        high: str,
        low: str,
        close: str,
        *,
        invalidation: bool = False,
    ) -> ReplayBar:
        return ReplayBar(
            close_time_ms=1_700_000_000_000 + index * 3_600_000,
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            atr=Decimal("1.5"),
            funding_quote=Decimal("0.005"),
            invalidation_hit=invalidation,
        )

    if is_long:
        paths = (
            (bar(1, "100", "105.2", "99", "104.8"), bar(2, "104.8", "112", "103", "111")),
            (bar(1, "100", "101", "94.8", "95"),),
            (bar(1, "100", "102", "98", "99", invalidation=True),),
        )
    else:
        paths = (
            (bar(1, "100", "101", "94.8", "95.2"), bar(2, "95.2", "97", "88", "89")),
            (bar(1, "100", "105.2", "99", "105"),),
            (bar(1, "100", "102", "98", "101", invalidation=True),),
        )
    return tuple(
        ReplayTrade(
            trade_id=f"{strategy}:{event}:representative-{index}",
            strategy_group_id=strategy,
            event_spec_id=event,
            exchange_instrument_id="ETHUSDT" if index != 1 else "SOLUSDT",
            side=side,
            entry_price=entry,
            initial_stop_price=stop,
            quantity=Decimal("2"),
            price_tick=Decimal("0.1"),
            bars=tuple(path),
        )
        for index, path in enumerate(paths)
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    first = build_decision_payload()
    second = build_decision_payload()
    if first != second:
        raise RuntimeError("exit_policy_replay_not_deterministic")
    print(json.dumps(first, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
