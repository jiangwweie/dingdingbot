"""Execute Stage-2 Full Replay Protocol V2 and emit required artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from research.multi_strategy_selection.analyze_features import (
    apply_buckets,
    freeze_cutoffs,
    screen,
    write_cutoffs,
)
from research.multi_strategy_selection.outcomes import compute_first_passage
from research.multi_strategy_selection.replay import (
    build_context_datasets,
    replay_detectors,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    cache_dir = args.cache_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    market, candidate = build_context_datasets(cache_dir)
    market.to_parquet(output / "market_context_hourly.parquet", index=False)
    candidate.to_parquet(output / "candidate_context_hourly.parquet", index=False)
    events, evaluations, counters = replay_detectors(cache_dir, market, candidate)
    evaluations.to_parquet(output / "detector_evaluations.parquet", index=False)
    events.to_parquet(output / "replayed_events_unbucketed.parquet", index=False)
    outcomes = compute_first_passage(cache_dir, events)
    outcomes.to_parquet(output / "first_passage_outcomes.parquet", index=False)
    merged = events.merge(
        outcomes,
        on=["event_spec_id", "strategy", "symbol", "direction", "trigger_candle_close_time_ms"],
        validate="one_to_one",
    )
    cutoffs = freeze_cutoffs(market, candidate)
    bucketed = apply_buckets(merged, cutoffs)
    bucketed.to_parquet(output / "replayed_events.parquet", index=False)
    screening, details = screen(bucketed)
    screening.to_csv(output / "feature_screening.csv", index=False)
    details.to_csv(output / "feature_bucket_statistics.csv", index=False)
    write_cutoffs(output / "discovery_cutoffs.json", cutoffs)
    (output / "replay_counters.json").write_text(
        json.dumps(asdict(counters), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "complete", "events": len(events), "outcomes": len(outcomes), "screening_rows": len(screening)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
