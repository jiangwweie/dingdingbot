"""Materialize PG comparative-strength facts from aligned closed candles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

import sqlalchemy as sa

from src.domain.comparative_strength import (
    ComparativeStrengthError,
    ComparativeStrengthSnapshot,
    compute_comparative_strength,
)


FACT_SURFACE = "strategy_comparative"
SOURCE_KIND = "live_market"
FACT_KEYS = {"leader_strength_confirmed", "relative_strength_confirmed"}


@dataclass(frozen=True)
class ComparativeStrengthGroupPlan:
    strategy_group_id: str
    symbols: tuple[str, ...]
    side: str
    fact_key: str
    timeframe: str
    lookback_bars: int
    max_rank: int
    require_positive_return: bool


@dataclass(frozen=True)
class ComparativeStrengthFactPlan:
    groups: tuple[ComparativeStrengthGroupPlan, ...]
    required_symbols: tuple[str, ...]


def load_comparative_strength_fact_plan(
    conn: sa.engine.Connection,
) -> ComparativeStrengthFactPlan:
    rows = list(
        conn.execute(
            sa.text(
                """
                SELECT
                  c.strategy_group_id,
                  c.symbol,
                  c.side,
                  r.fact_key,
                  r.definition_payload
                FROM brc_strategy_group_candidate_scope AS c
                JOIN brc_candidate_scope_event_bindings AS b
                  ON b.candidate_scope_id = c.candidate_scope_id
                 AND b.status = 'active'
                JOIN brc_strategy_side_event_specs AS e
                  ON e.event_spec_id = b.event_spec_id
                 AND e.status = 'current'
                JOIN brc_required_fact_contracts AS r
                  ON r.strategy_group_version_id = e.strategy_group_version_id
                WHERE c.status = 'active'
                  AND r.fact_key IN (
                    'leader_strength_confirmed',
                    'relative_strength_confirmed'
                  )
                ORDER BY c.strategy_group_id, c.priority_rank, c.symbol
                """
            )
        ).mappings()
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        payload = _json_dict(row.get("definition_payload"))
        policy = _json_dict(payload.get("comparative_strength"))
        if not policy:
            continue
        key = (str(row["strategy_group_id"]), str(row["fact_key"]))
        group = grouped.setdefault(
            key,
            {
                "strategy_group_id": key[0],
                "symbols": [],
                "side": str(row["side"]),
                "fact_key": key[1],
                "timeframe": str(policy.get("timeframe") or ""),
                "lookback_bars": int(policy.get("lookback_bars") or 0),
                "max_rank": int(policy.get("max_rank") or 0),
                "require_positive_return": bool(
                    policy.get("require_positive_return")
                ),
            },
        )
        group["symbols"].append(str(row["symbol"]).upper())

    groups = tuple(
        ComparativeStrengthGroupPlan(
            strategy_group_id=str(item["strategy_group_id"]),
            symbols=tuple(sorted(set(item["symbols"]))),
            side=str(item["side"]),
            fact_key=str(item["fact_key"]),
            timeframe=str(item["timeframe"]),
            lookback_bars=int(item["lookback_bars"]),
            max_rank=int(item["max_rank"]),
            require_positive_return=bool(item["require_positive_return"]),
        )
        for item in sorted(grouped.values(), key=lambda value: value["strategy_group_id"])
    )
    return ComparativeStrengthFactPlan(
        groups=groups,
        required_symbols=tuple(
            sorted({symbol for group in groups for symbol in group.symbols})
        ),
    )


def materialize_comparative_strength_fact_snapshots(
    conn: sa.engine.Connection,
    *,
    candles_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    observed_at_ms: int,
    source_ref: str,
) -> dict[str, Any]:
    plan = load_comparative_strength_fact_plan(conn)
    materialized: list[str] = []
    blocked: list[str] = []
    blockers: list[str] = []
    for group in plan.groups:
        try:
            snapshot = compute_comparative_strength(
                strategy_group_id=group.strategy_group_id,
                universe_symbols=group.symbols,
                timeframe=group.timeframe,
                lookback_bars=group.lookback_bars,
                candles_by_symbol=candles_by_symbol,
                observed_at_ms=observed_at_ms,
                valid_until_ms=_valid_until_ms(
                    candles_by_symbol,
                    symbols=group.symbols,
                    observed_at_ms=observed_at_ms,
                ),
                source_ref=source_ref,
            )
        except ComparativeStrengthError as exc:
            blocker = f"{group.strategy_group_id}:{exc}"
            blockers.append(blocker)
            for symbol in group.symbols:
                fact_id = _write_blocked_fact(
                    conn,
                    group=group,
                    symbol=symbol,
                    observed_at_ms=observed_at_ms,
                    source_ref=source_ref,
                    blocker=blocker,
                )
                blocked.append(fact_id)
            continue
        for symbol in group.symbols:
            fact_id = _write_snapshot_fact(
                conn,
                group=group,
                symbol=symbol,
                snapshot=snapshot,
                source_ref=source_ref,
            )
            materialized.append(fact_id)
    return {
        "status": (
            "comparative_strength_fact_snapshots_blocked"
            if blocked
            else "comparative_strength_fact_snapshots_materialized"
        ),
        "materialized_count": len(materialized),
        "blocked_count": len(blocked),
        "fact_snapshot_ids": [*materialized, *blocked],
        "blockers": blockers,
        "required_symbols": list(plan.required_symbols),
        "forbidden_effects": {
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _write_snapshot_fact(
    conn: sa.engine.Connection,
    *,
    group: ComparativeStrengthGroupPlan,
    symbol: str,
    snapshot: ComparativeStrengthSnapshot,
    source_ref: str,
) -> str:
    fact_id = _fact_id(
        group.strategy_group_id,
        symbol,
        snapshot.trigger_candle_close_time_ms,
    )
    _upsert_fact(
        conn,
        {
            "fact_snapshot_id": fact_id,
            "strategy_group_id": group.strategy_group_id,
            "symbol": symbol,
            "side": group.side,
            "runtime_profile_id": None,
            "fact_surface": FACT_SURFACE,
            "source_kind": SOURCE_KIND,
            "source_ref": source_ref,
            "computed": True,
            "satisfied": True,
            "freshness_state": "fresh",
            "failed_facts": _json([]),
            "fact_values": _json(
                {
                    **snapshot.model_dump(mode="json"),
                    "candidate_symbol": symbol,
                    "fact_key": group.fact_key,
                    "max_rank": group.max_rank,
                    "require_positive_return": group.require_positive_return,
                }
            ),
            "blocker_class": None,
            "observed_at_ms": snapshot.observed_at_ms,
            "valid_until_ms": snapshot.valid_until_ms,
            "created_at_ms": snapshot.observed_at_ms,
        },
    )
    return fact_id


def _write_blocked_fact(
    conn: sa.engine.Connection,
    *,
    group: ComparativeStrengthGroupPlan,
    symbol: str,
    observed_at_ms: int,
    source_ref: str,
    blocker: str,
) -> str:
    fact_id = _fact_id(group.strategy_group_id, symbol, observed_at_ms)
    _upsert_fact(
        conn,
        {
            "fact_snapshot_id": fact_id,
            "strategy_group_id": group.strategy_group_id,
            "symbol": symbol,
            "side": group.side,
            "runtime_profile_id": None,
            "fact_surface": FACT_SURFACE,
            "source_kind": SOURCE_KIND,
            "source_ref": source_ref,
            "computed": False,
            "satisfied": False,
            "freshness_state": "unknown",
            "failed_facts": _json([group.fact_key]),
            "fact_values": _json(
                {
                    "fact_key": group.fact_key,
                    "candidate_symbol": symbol,
                    "blocker": blocker,
                    "universe_symbols": list(group.symbols),
                }
            ),
            "blocker_class": "computed_not_satisfied",
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": observed_at_ms,
            "created_at_ms": observed_at_ms,
        },
    )
    return fact_id


def _upsert_fact(conn: sa.engine.Connection, row: dict[str, Any]) -> None:
    existing = conn.execute(
        sa.text(
            "SELECT fact_snapshot_id FROM brc_runtime_fact_snapshots "
            "WHERE fact_snapshot_id = :fact_snapshot_id"
        ),
        {"fact_snapshot_id": row["fact_snapshot_id"]},
    ).first()
    if existing:
        assignments = ", ".join(
            f"{key} = :{key}"
            for key in row
            if key != "fact_snapshot_id"
        )
        conn.execute(
            sa.text(
                "UPDATE brc_runtime_fact_snapshots SET "
                + assignments
                + " WHERE fact_snapshot_id = :fact_snapshot_id"
            ),
            row,
        )
        return
    columns = ", ".join(row)
    values = ", ".join(f":{key}" for key in row)
    conn.execute(
        sa.text(
            f"INSERT INTO brc_runtime_fact_snapshots ({columns}) "
            f"VALUES ({values})"
        ),
        row,
    )


def _valid_until_ms(
    candles_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    symbols: Sequence[str],
    observed_at_ms: int,
) -> int:
    trigger = max(
        (
            int(candles_by_symbol[symbol][-1]["close_time_ms"])
            for symbol in symbols
            if symbol in candles_by_symbol and candles_by_symbol[symbol]
        ),
        default=observed_at_ms,
    )
    return max(trigger + 3_600_000, observed_at_ms + 1)


def _fact_id(strategy_group_id: str, symbol: str, authority_ms: int) -> str:
    identity = f"{strategy_group_id}|{symbol}|{authority_ms}"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"fact:comparative:{strategy_group_id}:{symbol}:{suffix}"


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
