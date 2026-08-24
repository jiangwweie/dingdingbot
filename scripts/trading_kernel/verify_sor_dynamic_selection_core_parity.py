#!/usr/bin/env python3
"""Verify the production SelectionCore against the frozen 961x24 Golden."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.trading_kernel.domain.instrument_selection import (
    INTERVAL_MS,
    SelectionKline,
    SelectionSourceWindow,
    build_sor_dynamic_selection_period,
    build_sor_dynamic_selection_spec_v0,
    run_sor_dynamic_selection_v0,
)


class CoreParityError(RuntimeError):
    """Production SelectionCore differs from the frozen Golden authority."""


@dataclass(frozen=True, slots=True)
class _RawKline:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    quote_volume: Decimal


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("tests/trading_kernel/fixtures/sor_dynamic_selection_v0"),
    )
    return parser


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_golden(
    artifact_dir: Path,
) -> tuple[dict[str, Any], dict[int, dict[str, str]], dict[str, str]]:
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshots: dict[int, dict[str, str]] = {}
    with gzip.open(
        artifact_dir / "selection_snapshots.csv.gz",
        "rt",
        encoding="utf-8",
        newline="",
    ) as stream:
        for row in csv.DictReader(stream):
            snapshots[int(row["session_start_ms"])] = row
    members: dict[str, str] = {}
    with gzip.open(
        artifact_dir / "member_decisions.csv.gz",
        "rt",
        encoding="utf-8",
        newline="",
    ) as stream:
        for row in csv.DictReader(stream):
            members[row["member_decision_id"]] = row["member_semantic_digest"]
    return manifest, snapshots, members


def _read_cache(
    *,
    cache_dir: Path,
    input_meta: dict[str, object],
) -> dict[int, _RawKline]:
    path = cache_dir / str(input_meta["filename"])
    if _sha256_file(path) != input_meta["sha256"]:
        raise CoreParityError(f"cache digest mismatch: {path.name}")
    rows: dict[int, _RawKline] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for raw in csv.DictReader(stream):
            kline = _RawKline(
                open_time_ms=int(raw["open_time"]),
                open=Decimal(raw["open"]),
                high=Decimal(raw["high"]),
                low=Decimal(raw["low"]),
                close=Decimal(raw["close"]),
                quote_volume=Decimal(raw["quote_volume"]),
            )
            rows[kline.open_time_ms] = kline
    return rows


def verify(args: argparse.Namespace) -> dict[str, object]:
    artifact_dir = args.artifact_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    manifest, golden_snapshots, golden_members = _read_golden(artifact_dir)
    input_meta = {
        str(item["exchange_instrument_id"]): item for item in manifest["input_files"]
    }
    candidate_ids = tuple(
        sorted(
            str(item)
            for item in manifest["selection_spec"]["candidate_exchange_instrument_ids"]
        )
    )
    source_rows = {
        instrument_id: _read_cache(
            cache_dir=cache_dir,
            input_meta=input_meta[instrument_id],
        )
        for instrument_id in candidate_ids
    }
    spec = build_sor_dynamic_selection_spec_v0(
        selection_spec_id=str(manifest["research_spec_id"]),
        strategy_group_id=str(manifest["selection_spec"]["strategy_group_id"]),
        strategy_version_id=str(manifest["selection_spec"]["strategy_version_id"]),
        event_spec_ids=tuple(manifest["selection_spec"]["event_spec_ids"]),
        candidate_exchange_instrument_ids=candidate_ids,
        installed_at_ms=int(manifest["session_start_ms"]),
    )

    member_matches = 0
    for session_start_ms in sorted(golden_snapshots):
        period = build_sor_dynamic_selection_period(session_start_ms=session_start_ms)
        window_start_ms = session_start_ms - 23 * 60 * 60 * 1000
        windows: list[SelectionSourceWindow] = []
        for instrument_id in candidate_ids:
            rows = source_rows[instrument_id]
            klines: list[SelectionKline] = []
            for index in range(96):
                raw = rows[window_start_ms + index * INTERVAL_MS]
                klines.append(
                    SelectionKline(
                        open_time_ms=raw.open_time_ms,
                        close_time_ms=raw.open_time_ms + INTERVAL_MS,
                        open=raw.open,
                        high=raw.high,
                        low=raw.low,
                        close=raw.close,
                        quote_volume=raw.quote_volume,
                    )
                )
            windows.append(
                SelectionSourceWindow(
                    exchange_instrument_id=instrument_id,
                    input_window_start_ms=window_start_ms,
                    feature_cutoff_at_ms=period.feature_cutoff_at_ms,
                    klines=tuple(klines),
                )
            )
        result = run_sor_dynamic_selection_v0(
            spec=spec,
            period=period,
            source_windows=tuple(windows),
            decision_at_ms=period.feature_cutoff_at_ms,
            source_observed_at_ms=period.feature_cutoff_at_ms,
            created_at_ms=period.feature_cutoff_at_ms,
        )
        expected_snapshot = golden_snapshots[session_start_ms]
        if (
            result.snapshot.selection_semantic_digest
            != expected_snapshot["selection_semantic_digest"]
        ):
            raise CoreParityError(f"snapshot digest mismatch: {session_start_ms}")
        for decision in result.member_decisions:
            expected_digest = golden_members[decision.member_decision_id]
            if decision.member_semantic_digest != expected_digest:
                raise CoreParityError(
                    f"member digest mismatch: {decision.member_decision_id}"
                )
            member_matches += 1
    return {
        "status": "verified",
        "snapshots": len(golden_snapshots),
        "member_decisions": member_matches,
        "selection_spec_digest": spec.algorithm_semantic_digest,
    }


def main(argv: list[str] | None = None) -> int:
    result = verify(_parser().parse_args(argv))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
