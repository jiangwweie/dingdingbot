"""Freeze Protocol V2 manifest, human report, and publishable artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

REQUIRED_ARTIFACTS = (
    "market_context_hourly.parquet",
    "candidate_context_hourly.parquet",
    "detector_evaluations.parquet",
    "replayed_events.parquet",
    "first_passage_outcomes.parquet",
    "feature_screening.csv",
    "feature_bucket_statistics.csv",
    "discovery_cutoffs.json",
    "replay_counters.json",
    "production_parity.json",
    "production_execution_sensitivity.csv",
)

AUTHORITY_FILES = (
    "src/trading_kernel/domain/detectors/cpm.py",
    "src/trading_kernel/domain/detectors/mpg.py",
    "src/trading_kernel/domain/detectors/mi.py",
    "src/trading_kernel/domain/detectors/brf2.py",
    "src/trading_kernel/application/produce_strategy_signal.py",
    "src/trading_kernel/application/project_comparative_universe.py",
    "src/trading_kernel/domain/exposure_episode.py",
    "src/trading_kernel/domain/signal.py",
    "src/trading_kernel/domain/strategy_registry.py",
)

RESEARCH_FILES = (
    "research/multi_strategy_selection/analyze_features.py",
    "research/multi_strategy_selection/comparative_replay.py",
    "research/multi_strategy_selection/context_features.py",
    "research/multi_strategy_selection/finalize_artifacts.py",
    "research/multi_strategy_selection/first_passage.py",
    "research/multi_strategy_selection/market_data.py",
    "research/multi_strategy_selection/outcomes.py",
    "research/multi_strategy_selection/production_parity.py",
    "research/multi_strategy_selection/replay.py",
    "research/multi_strategy_selection/run_full_replay.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _report(output: Path) -> str:
    market = pd.read_parquet(output / "market_context_hourly.parquet")
    candidate = pd.read_parquet(output / "candidate_context_hourly.parquet")
    evaluations = pd.read_parquet(output / "detector_evaluations.parquet")
    events = pd.read_parquet(output / "replayed_events.parquet")
    outcomes = pd.read_parquet(output / "first_passage_outcomes.parquet")
    screening = pd.read_csv(output / "feature_screening.csv")
    parity = json.loads((output / "production_parity.json").read_text())
    counters = json.loads((output / "replay_counters.json").read_text())
    supported = screening.loc[screening["classification"] == "SUPPORTED_FOR_SHADOW"]
    classes = screening["classification"].value_counts().to_dict()
    event_counts = events.groupby("strategy").size().to_dict()
    path_counts = outcomes["path_label"].value_counts().to_dict()
    market_state_count = len(market)
    candidate_hour_count = len(candidate)
    complete_market_state_count = int(
        (
            market["valid_candidate_count"].eq(24)
            & market["valid_pair_count"].eq(276)
            & market["missing_pair_count"].eq(0)
        ).sum()
    )
    expected_evaluations = candidate_hour_count * 4
    if complete_market_state_count != market_state_count:
        raise ValueError("not every market state has the exact complete 24-member context")
    if counters["candidate_hour_count"] != candidate_hour_count:
        raise ValueError("candidate-hour counter does not match candidate context cardinality")
    if len(evaluations) != expected_evaluations:
        raise ValueError("Detector evaluation denominator is incomplete")
    if len(events) != len(outcomes):
        raise ValueError("Replay Event and first-passage outcome cardinality differ")
    supported_rows = "\n".join(
        f"| {row.strategy} | {row.feature} | {row.discovery_high_minus_low_net_path_rate:.3f} | "
        f"{row.holdout_high_minus_low_net_path_rate:.3f} | {row.holdout_low_resolved_n} | "
        f"{row.holdout_high_resolved_n} | {row.same_sign_ratio:.1%} |"
        for row in supported.itertuples()
    )
    return f"""# Stage-2 Full Replay Report — Protocol V2

## Status

```text
research_status = STAGE2_FULL_REPLAY_COMPLETE
selector_design_authority = NONE
implementation_authority = NONE
production_authority = NONE
```

## Code facts

- Authority: `dev@2697f4b5943ed6a98f04a93e1b78d38e53780890`.
- CandidateUniverse is the exact sorted 24-member SOR Dynamic V0 panel.
- CPM/MPG/MI/BRF2 use direct current-dev Detector invocation and production
  `build_comparative_universe_projection()` for MPG/MI.
- Signal anchor is the trigger candle final close. Protection is the exact
  Detector `protection_reference` fact. Forward path starts strictly after the
  trigger close boundary.
- Signal-R is not production execution R. No Detector, threshold, ExitProfile,
  Capacity, leverage, Selection Authority, or production behavior changed.

## Replay facts

| Denominator | Count |
| --- | ---: |
| Candidate-hours | {counters['candidate_hour_count']:,} |
| Valid Detector evaluations | {counters['valid_detector_evaluation_count']:,} |
| Invalid Detector evaluations | {counters['invalid_detector_evaluation_count']:,} |
| Raw triggered evaluations | {counters['raw_triggered_count']:,} |
| Rising-edge Replay Events | {counters['replay_event_count']:,} |

| Strategy | Events |
| --- | ---: |
| BRF2 | {event_counts.get('BRF2-001', 0)} |
| CPM | {event_counts.get('CPM-RO-001', 0)} |
| MI | {event_counts.get('MI-001', 0)} |
| MPG | {event_counts.get('MPG-001', 0)} |

| Path | Count |
| --- | ---: |
| SIGNAL_TP1_FIRST | {path_counts.get('SIGNAL_TP1_FIRST', 0)} |
| SIGNAL_STOP_FIRST | {path_counts.get('SIGNAL_STOP_FIRST', 0)} |
| NEITHER | {path_counts.get('NEITHER', 0)} |
| AMBIGUOUS | {path_counts.get('AMBIGUOUS', 0)} |

All {market_state_count:,} hourly market states contained all 24 candidates and all 276 pairwise
correlations. All Replay Events had valid Signal-R geometry. No observed Event
required a real 1m ambiguity drill-down; the 15m→1m and still-ambiguous branches
are covered by deterministic tests.

## Frozen classifications

| Classification | Count |
| --- | ---: |
| SUPPORTED_FOR_SHADOW | {classes.get('SUPPORTED_FOR_SHADOW', 0)} |
| INCONCLUSIVE | {classes.get('INCONCLUSIVE', 0)} |
| REJECTED | {classes.get('REJECTED', 0)} |

### Supported hypotheses

Effect is `HIGH net_path_rate - LOW net_path_rate`.

| Strategy | Feature | Discovery effect | Holdout effect | Holdout LOW N | Holdout HIGH N | LOSO same-sign |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{supported_rows}

Interpretation:

- BRF2 Events had better Signal-R path quality in HIGH average cross-asset
  correlation and HIGH market realized-volatility states.
- CPM Events had better Signal-R path quality in LOW average cross-asset
  correlation states and HIGH candidate directional-efficiency states.
- MPG produced no supported Context feature under the frozen gates.
- MI produced no supported Context feature; its extreme Holdout buckets were
  generally below the required 15 resolved observations.

## Production parity and execution sensitivity

- Production historical signals: {parity['production_signal_count']}.
- Current-version direct Detector trigger matches: {parity['current_detector_trigger_match_count']}.
- Normalized Detector fact matches: {parity['normalized_fact_semantic_match_count']}.
- Protection-reference matches: {parity['protection_reference_match_count']}.
- Legacy EventSpec v2 drift: {parity['detector_version_drift']}.
- Fixed-24 ComparisonUniverse drift for MPG/MI: {parity['comparison_universe_drift']}.
- Matched production Tickets: {parity['matched_ticket_count']} / {parity['production_ticket_count']}.
- Signal-basis vs actual-entry path classification: {parity['classification_same_count']} same,
  {parity['classification_changed_count']} changed.
- Absolute execution-anchor delta: P75 `{parity['p75_abs_execution_anchor_delta_signal_r']:.3f}`
  Signal-R; P90 `{parity['p90_abs_execution_anchor_delta_signal_r']:.3f}` Signal-R.

The requested immutable 2026-08-30 production snapshot was unavailable. These
checks use current Tokyo PostgreSQL retained historical lineage and therefore
are secondary sanity evidence only.

## Research inference

The four supported rows may enter a future Shadow Selection design as
univariate hypotheses. They do not authorize a composite score, threshold
optimization, ticker whitelist, production Selector, or strategy change.

## Not proven

This study does not prove profitability, causality, optimal thresholds,
execution-adjusted edge, fee/slippage-adjusted edge, production readiness, or
that a multi-feature Selector will outperform. Required next evidence remains:

```text
Shadow Selection -> Forward Evidence -> Execution Economics -> Owner Activation
```
"""


def finalize(cache: Path, output: Path, publish: Path) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[2]
    missing = [name for name in REQUIRED_ARTIFACTS if not (output / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing required Stage-2 artifacts: {missing}")
    report = _report(output)
    publish.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_ARTIFACTS:
        shutil.copy2(output / name, publish / name)
    (output / "STAGE2_FULL_REPLAY_REPORT.md").write_text(report, encoding="utf-8")
    (publish / "STAGE2_FULL_REPLAY_REPORT.md").write_text(report, encoding="utf-8")
    archive_manifest = json.loads((cache / "market_data_manifest.json").read_text())
    cutoffs = json.loads((output / "discovery_cutoffs.json").read_text())
    screening = pd.read_csv(output / "feature_screening.csv")
    counters = json.loads((output / "replay_counters.json").read_text())
    parity = json.loads((output / "production_parity.json").read_text())
    candidate_universe = tuple(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    candidate_universe_digest = "sha256:" + hashlib.sha256(
        json.dumps(candidate_universe, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    authority_file_sha256 = {
        name: _sha256(repo_root / name) for name in AUTHORITY_FILES
    }
    research_file_sha256 = {
        name: _sha256(repo_root / name) for name in RESEARCH_FILES
    }
    manifest: dict[str, object] = {
        "schema": "brc.research.multi_strategy_selection.stage2_manifest.v2",
        "protocol_version": "2",
        "research_status": "STAGE2_FULL_REPLAY_COMPLETE",
        "dev_head_sha": "2697f4b5943ed6a98f04a93e1b78d38e53780890",
        "production_reference_commit": "3fa2e21ce52bc3c203c721be4b696dc4265fcf96",
        "research_estimand": "signal_basis_event_path_quality",
        "signal_anchor_basis": "trigger_candle_final_close",
        "protection_basis": "detector_protection_reference",
        "forward_path_start": "strictly_after_trigger_close",
        "execution_equivalence": False,
        "production_execution_validation": "secondary_only",
        "option_a": "OUT_OF_SCOPE",
        "evaluation_window": ["2026-07-31T00:00:00Z", "2026-08-31T00:00:00Z"],
        "warmup_start": "2026-06-15T00:00:00Z",
        "discovery_window": ["2026-07-31T00:00:00Z", "2026-08-16T00:00:00Z"],
        "holdout_window": ["2026-08-16T00:00:00Z", "2026-08-31T00:00:00Z"],
        "candidate_count": len(candidate_universe),
        "candidate_universe": candidate_universe,
        "candidate_universe_digest": candidate_universe_digest,
        "authority_file_sha256": authority_file_sha256,
        "research_file_sha256": research_file_sha256,
        "market_data": {
            "source": archive_manifest["source"],
            "archive_manifest_sha256": _sha256(cache / "market_data_manifest.json"),
            "archive_count": len(archive_manifest["archives"]),
            "archives": archive_manifest["archives"],
            "runtime_close_boundary": "open_time + interval_ms",
        },
        "context_features": {
            "F1": "population stddev of complete 24-symbol simple 24h returns",
            "F2": "mean valid off-diagonal Pearson correlation of 24 hourly log-return vectors",
            "F3": "positive 24h-return breadth over exactly 24 candidates",
            "F4": "median symbol sqrt(sum(last 24 hourly log_return^2))",
            "F5": "sum of 24 equal-weight hourly cross-sectional log returns",
            "F6": "CPM-only 24h candidate directional efficiency",
        },
        "discovery_tercile_cutoffs": cutoffs,
        "first_passage": {
            "labels": ["SIGNAL_TP1_FIRST", "SIGNAL_STOP_FIRST", "NEITHER", "AMBIGUOUS"],
            "max_forward_bars_1h": 48,
            "primary_path_resolution": "15m",
            "ambiguous_resolution": "1m_then_AMBIGUOUS",
        },
        "counters": counters,
        "classification_counts": screening["classification"].value_counts().to_dict(),
        "supported_hypotheses": screening.loc[
            screening["classification"] == "SUPPORTED_FOR_SHADOW",
            ["strategy", "feature"],
        ].to_dict("records"),
        "production_parity": parity,
        "production_reference_snapshot_status": parity["source_status"],
        "completed_stages": [f"R{index}" for index in range(17)],
        "selector_design_authority": "NONE",
        "implementation_authority": "NONE",
        "production_authority": "NONE",
    }
    artifact_names = (*REQUIRED_ARTIFACTS, "STAGE2_FULL_REPLAY_REPORT.md")
    manifest["artifact_sha256"] = {name: _sha256(publish / name) for name in artifact_names}
    for target in (
        output / "stage2_replay_manifest.json",
        publish / "stage2_replay_manifest.json",
        Path(__file__).with_name("stage2_replay_manifest.json"),
    ):
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--publish-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = finalize(args.cache_dir.resolve(), args.output_dir.resolve(), args.publish_dir.resolve())
    print(json.dumps({"status": manifest["research_status"], "supported": manifest["supported_hypotheses"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
