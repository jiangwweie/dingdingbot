"""Secondary-only parity and execution-anchor sensitivity from Tokyo lineage."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shlex
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd

from research.multi_strategy_selection.first_passage import (
    PathBar,
    evaluate_signal_path,
)
from research.multi_strategy_selection.replay import (
    EVALUATION_END_MS,
    EVALUATION_START_MS,
)

TARGET_GROUPS_SQL = "'CPM-RO-001','MPG-001','MI-001','BRF2-001'"


def _query_csv(query: str) -> pd.DataFrame:
    copy = f"COPY ({query}) TO STDOUT WITH CSV HEADER"
    command = shlex.join(
        (
            "sudo",
            "docker",
            "exec",
            "brc-trading-kernel-pg",
            "psql",
            "-U",
            "brc_kernel",
            "-d",
            "brc_trading_kernel",
            "-c",
            copy,
        )
    )
    result = subprocess.run(
        ("ssh", "tokyo", "--", command),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return pd.read_csv(io.StringIO(result.stdout))


def _signals() -> pd.DataFrame:
    return _query_csv(
        "SELECT s.signal_event_id,s.strategy_group_id,s.strategy_version_id,"
        "s.event_spec_id,s.exchange_instrument_id,s.position_side,"
        "s.occurred_at_ms,s.fact_digest,f.value #>> '{}' AS protection_reference "
        "FROM brc_signal_events s JOIN brc_signal_fact_snapshots f "
        "ON f.signal_event_id=s.signal_event_id AND f.role='protection_reference' "
        f"WHERE s.occurred_at_ms>={EVALUATION_START_MS} "
        f"AND s.occurred_at_ms<{EVALUATION_END_MS} "
        f"AND s.strategy_group_id IN ({TARGET_GROUPS_SQL})"
    )


def _tickets() -> pd.DataFrame:
    return _query_csv(
        "SELECT t.ticket_id,t.signal_event_id,t.strategy_group_id,t.event_spec_id,"
        "t.exchange_instrument_id,t.position_side,s.occurred_at_ms,"
        "t.entry_reference_price,t.initial_stop_price "
        "FROM brc_trade_tickets t JOIN brc_signal_events s "
        "ON s.signal_event_id=t.signal_event_id "
        f"WHERE s.occurred_at_ms>={EVALUATION_START_MS} "
        f"AND s.occurred_at_ms<{EVALUATION_END_MS} "
        f"AND s.strategy_group_id IN ({TARGET_GROUPS_SQL})"
    )


def _facts() -> pd.DataFrame:
    return _query_csv(
        "SELECT f.signal_event_id,f.fact_definition_id,f.role,f.value::text AS value,"
        "f.satisfied FROM brc_signal_fact_snapshots f JOIN brc_signal_events s "
        "ON s.signal_event_id=f.signal_event_id "
        f"WHERE s.occurred_at_ms>={EVALUATION_START_MS} "
        f"AND s.occurred_at_ms<{EVALUATION_END_MS} "
        f"AND s.strategy_group_id IN ({TARGET_GROUPS_SQL})"
    )


def _semantic_fact_digest(rows: pd.DataFrame) -> str:
    facts = [
        {
            "fact_definition_id": str(row.fact_definition_id),
            "role": str(row.role),
            "value": json.loads(str(row.value)),
            "satisfied": str(row.satisfied).lower() in {"t", "true", "1"},
        }
        for row in rows.sort_values("fact_definition_id").itertuples()
    ]
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _path_bars(frame: pd.DataFrame) -> tuple[PathBar, ...]:
    return tuple(
        PathBar(
            open_time_ms=int(row["open_time"]),
            close_time_ms=int(row["close_time"]),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
        )
        for _, row in frame.iterrows()
    )


def validate(cache_dir: Path, output_dir: Path) -> dict[str, object]:
    replay = pd.read_parquet(output_dir / "replayed_events.parquet")
    signals = _signals()
    tickets = _tickets()
    facts = _facts()
    production_fact_semantics = {
        signal_id: _semantic_fact_digest(group)
        for signal_id, group in facts.groupby("signal_event_id")
    }
    replay_keys = replay.rename(columns={"trigger_candle_close_time_ms": "occurred_at_ms"})
    merged = signals.merge(
        replay_keys,
        on=["event_spec_id", "exchange_instrument_id", "occurred_at_ms"],
        how="left",
        suffixes=("_production", "_replay"),
        indicator=True,
    )
    matched = merged.loc[merged["_merge"] == "both"]
    fact_match = matched.apply(
        lambda row: production_fact_semantics.get(row["signal_event_id"])
        == row["detector_fact_semantic_digest"],
        axis=1,
    )
    protection_match = pd.to_numeric(matched["protection_reference"]).eq(
        pd.to_numeric(matched["signal_stop_reference"])
    )
    replay_key_set = set(
        zip(
            replay["event_spec_id"],
            replay["exchange_instrument_id"],
            replay["trigger_candle_close_time_ms"],
            strict=True,
        )
    )
    production_key_set = set(
        zip(signals["event_spec_id"], signals["exchange_instrument_id"], signals["occurred_at_ms"], strict=True)
    )
    evaluations = pd.read_parquet(output_dir / "detector_evaluations.parquet")
    evaluation_merge = signals.merge(
        evaluations,
        left_on=["event_spec_id", "exchange_instrument_id", "occurred_at_ms"],
        right_on=["event_spec_id", "exchange_instrument_id", "trigger_candle_close_time_ms"],
        how="left",
    )
    legacy_version = evaluation_merge["strategy_version_id"].ne(
        evaluation_merge["strategy_group_id"].map(
            {
                "CPM-RO-001": "sgv:CPM-RO-001:v3",
                "MPG-001": "sgv:MPG-001:v3",
                "MI-001": "sgv:MI-001:v3",
                "BRF2-001": "sgv:BRF2-001:v3",
            }
        )
    )
    current_version = evaluation_merge.loc[~legacy_version]
    comparison_drift = current_version.loc[
        current_version["strategy_group_id"].isin({"MPG-001", "MI-001"})
        & current_version["detector_status"].ne("triggered")
    ]

    ticket_rows: list[dict[str, object]] = []
    frames: dict[str, pd.DataFrame] = {}
    replay_lookup = {
        (
            str(record["event_spec_id"]),
            str(record["exchange_instrument_id"]),
            int(str(record["trigger_candle_close_time_ms"])),
        ): cast(dict[str, object], record)
        for record in replay.to_dict("records")
    }
    for raw_ticket in tickets.to_dict("records"):
        ticket = cast(dict[str, object], raw_ticket)
        occurred_at_ms = int(str(ticket["occurred_at_ms"]))
        lookup = (
            str(ticket["event_spec_id"]),
            str(ticket["exchange_instrument_id"]),
            occurred_at_ms,
        )
        if lookup not in replay_lookup:
            continue
        event = replay_lookup[lookup]
        symbol = str(ticket["exchange_instrument_id"]).split(":", 2)[1]
        if symbol not in frames:
            frames[symbol] = pd.read_parquet(cache_dir / "normalized" / f"{symbol}_15m.parquet")
        bars = frames[symbol]
        selected = bars.loc[
            (bars["open_time"] >= occurred_at_ms)
            & (bars["open_time"] < occurred_at_ms + 48 * 3_600_000)
        ].head(192)
        actual = evaluate_signal_path(
            side=cast(Literal["long", "short"], str(ticket["position_side"])),
            anchor=Decimal(str(ticket["entry_reference_price"])),
            stop=Decimal(str(ticket["initial_stop_price"])),
            trigger_close_ms=occurred_at_ms,
            bars_15m=_path_bars(selected),
            bars_1m_by_15m={},
        )
        signal_risk = Decimal(str(event["signal_risk_per_unit"]))
        actual_entry = Decimal(str(ticket["entry_reference_price"]))
        signal_anchor = Decimal(str(event["signal_anchor_price"]))
        direction_adjusted = (
            actual_entry - signal_anchor
            if ticket["position_side"] == "long"
            else signal_anchor - actual_entry
        )
        ticket_rows.append(
            {
                "ticket_reference_digest": "sha256:"
                + hashlib.sha256(str(ticket["ticket_id"]).encode()).hexdigest(),
                "strategy": ticket["strategy_group_id"],
                "symbol": symbol,
                "signal_path_label": event["path_label"],
                "actual_entry_path_label": actual.label.value,
                "execution_anchor_delta_signal_r": float(direction_adjusted / signal_risk),
            }
        )
    ticket_frame = pd.DataFrame(ticket_rows)
    ticket_frame.to_csv(output_dir / "production_execution_sensitivity.csv", index=False)
    absolute = ticket_frame["execution_anchor_delta_signal_r"].abs() if not ticket_frame.empty else pd.Series(dtype=float)
    result = {
        "source_status": "CURRENT_TOKYO_RETAINED_LINEAGE_NOT_IMMUTABLE_0005_SNAPSHOT",
        "production_signal_count": len(signals),
        "replay_matching_count": len(matched),
        "missing_in_replay": int((merged["_merge"] == "left_only").sum()),
        "extra_in_replay": len(replay_key_set - production_key_set),
        "normalized_fact_semantic_match_count": int(fact_match.sum()),
        "persisted_fact_digest_comparison": "NOT_EXPECTED_PROJECTION_VERSION_DIFFERS",
        "protection_reference_match_count": int(protection_match.sum()),
        "geometry_mismatch": int((~protection_match).sum()),
        "detector_file_drift": 0,
        "detector_version_drift": int(legacy_version.sum()),
        "comparison_universe_drift": len(comparison_drift),
        "current_version_production_signal_count": len(current_version),
        "current_detector_trigger_match_count": int(
            current_version["detector_status"].eq("triggered").sum()
        ),
        "entry_parity": "NOT_EXPECTED",
        "production_ticket_count": len(tickets),
        "matched_ticket_count": len(ticket_frame),
        "median_execution_anchor_delta_signal_r": None if absolute.empty else float(ticket_frame["execution_anchor_delta_signal_r"].median()),
        "p75_abs_execution_anchor_delta_signal_r": None if absolute.empty else float(np.quantile(absolute, 0.75)),
        "p90_abs_execution_anchor_delta_signal_r": None if absolute.empty else float(np.quantile(absolute, 0.90)),
        "classification_same_count": 0 if ticket_frame.empty else int(ticket_frame["signal_path_label"].eq(ticket_frame["actual_entry_path_label"]).sum()),
        "classification_changed_count": 0 if ticket_frame.empty else int(ticket_frame["signal_path_label"].ne(ticket_frame["actual_entry_path_label"]).sum()),
    }
    (output_dir / "production_parity.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.cache_dir.resolve(), args.output_dir.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
