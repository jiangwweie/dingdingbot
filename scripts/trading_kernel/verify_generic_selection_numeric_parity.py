#!/usr/bin/env python3
"""Certify frozen Generic Dynamic Selection numeric authority locally.

This tool is deliberately outside the production runtime.  It reads explicit,
immutable research inputs only when invoked for local certification; no worker,
repository, or exchange adapter imports it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from src.trading_kernel.domain.dynamic_selection_numeric import (
    rank_brf2_residual_extension_v0_decimal,
)

STAGE3_1_REPLAY_MANIFEST_SHA256 = (
    "sha256:289c75428742c1bebfa8b6585aaed82a8af0ae7b1b1feefcc482f017911f305e"
)
BRF2_STRATEGY_GROUP_ID = "BRF2-001"
_ONE_HOUR_MS = 60 * 60 * 1000
_TOP_N = 16


class Brf2NumericParityError(RuntimeError):
    """The Decimal BRF2 candidate is not the frozen Stage-3.1 selector."""


@dataclass(frozen=True, slots=True)
class Brf2NumericParityResult:
    status: Literal["PASS"]
    checked_cutoff_count: int
    mismatch_count: int
    replay_manifest_sha256: str
    market_data_manifest_sha256: str
    member_decisions_sha256: str


def compare_brf2_top16_member_sets(
    *,
    expected_top16_by_cutoff: Mapping[int, tuple[str, ...]],
    actual_top16_by_cutoff: Mapping[int, tuple[str, ...]],
) -> Brf2NumericParityResult:
    """Require exact Top16 membership for every frozen cutoff."""

    expected_cutoffs = frozenset(expected_top16_by_cutoff)
    actual_cutoffs = frozenset(actual_top16_by_cutoff)
    if not expected_cutoffs or expected_cutoffs != actual_cutoffs:
        raise Brf2NumericParityError(
            "BRF2 frozen cutoff set differs: "
            f"missing={sorted(expected_cutoffs - actual_cutoffs)} "
            f"unexpected={sorted(actual_cutoffs - expected_cutoffs)}"
        )
    for cutoff in sorted(expected_cutoffs):
        expected = _validated_top16(
            expected_top16_by_cutoff[cutoff],
            label=f"expected BRF2 Top16 at {cutoff}",
        )
        actual = _validated_top16(
            actual_top16_by_cutoff[cutoff],
            label=f"actual BRF2 Top16 at {cutoff}",
        )
        if frozenset(expected) != frozenset(actual):
            raise Brf2NumericParityError(
                f"BRF2 Top16 mismatch at {cutoff}: "
                f"missing={sorted(set(expected) - set(actual))} "
                f"unexpected={sorted(set(actual) - set(expected))}"
            )
    return Brf2NumericParityResult(
        status="PASS",
        checked_cutoff_count=len(expected_cutoffs),
        mismatch_count=0,
        replay_manifest_sha256="",
        market_data_manifest_sha256="",
        member_decisions_sha256="",
    )


def verify_brf2_decimal_top16_parity(
    *,
    cache_dir: Path,
    artifact_dir: Path,
) -> Brf2NumericParityResult:
    """Validate every Stage-3.1 BRF2 cutoff against Decimal Candidate24 ranks."""

    replay_manifest_path = artifact_dir / "stage3_1_replay_manifest.json"
    if _sha256_file(replay_manifest_path) != STAGE3_1_REPLAY_MANIFEST_SHA256:
        raise Brf2NumericParityError("Stage-3.1 replay manifest digest mismatch")
    replay_manifest = _read_json(replay_manifest_path)
    expected_market_digest = _require_digest(
        replay_manifest.get("market_data_manifest_sha256"),
        "Stage-3.1 market-data manifest digest",
    )
    cache_manifest_path = cache_dir / "market_data_manifest.json"
    actual_market_digest = _sha256_file(cache_manifest_path)
    if actual_market_digest != expected_market_digest:
        raise Brf2NumericParityError("frozen market-data manifest digest mismatch")

    member_decisions_path = artifact_dir / "stage3_1_member_decisions.parquet"
    expected_member_digest = _require_digest(
        _require_mapping(replay_manifest.get("artifact_sha256"), "artifact_sha256").get(
            "stage3_1_member_decisions.parquet"
        ),
        "Stage-3.1 member-decision artifact digest",
    )
    actual_member_digest = _sha256_file(member_decisions_path)
    if actual_member_digest != expected_member_digest:
        raise Brf2NumericParityError("Stage-3.1 member-decision artifact digest mismatch")

    expected = _read_expected_brf2_top16(member_decisions_path)
    actual = _calculate_decimal_brf2_top16(
        cache_dir=cache_dir,
        expected_top16_by_cutoff=expected,
    )
    compared = compare_brf2_top16_member_sets(
        expected_top16_by_cutoff=expected,
        actual_top16_by_cutoff=actual,
    )
    return Brf2NumericParityResult(
        status=compared.status,
        checked_cutoff_count=compared.checked_cutoff_count,
        mismatch_count=compared.mismatch_count,
        replay_manifest_sha256=STAGE3_1_REPLAY_MANIFEST_SHA256,
        market_data_manifest_sha256=actual_market_digest,
        member_decisions_sha256=actual_member_digest,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=os.getenv("GENERIC_SELECTION_STAGE3_1_CACHE_DIR"),
        required=os.getenv("GENERIC_SELECTION_STAGE3_1_CACHE_DIR") is None,
        help="Frozen Stage-3.1 market cache containing normalized 1h Parquet files",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=os.getenv("GENERIC_SELECTION_STAGE3_1_ARTIFACT_DIR"),
        required=os.getenv("GENERIC_SELECTION_STAGE3_1_ARTIFACT_DIR") is None,
        help="Frozen Stage-3.1 artifact directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = verify_brf2_decimal_top16_parity(
        cache_dir=args.cache_dir.resolve(),
        artifact_dir=args.artifact_dir.resolve(),
    )
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


def _read_expected_brf2_top16(path: Path) -> dict[int, tuple[str, ...]]:
    rows = _read_parquet_rows(
        path,
        columns=(
            "strategy",
            "feature_cutoff_at_ms",
            "exchange_instrument_id",
            "rank",
        ),
    )
    by_cutoff: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for row in rows:
        if row["strategy"] != BRF2_STRATEGY_GROUP_ID:
            continue
        cutoff = _require_int(
            row["feature_cutoff_at_ms"],
            "Stage-3.1 BRF2 feature cutoff",
        )
        by_cutoff[cutoff].append(
            (
                _require_int(row["rank"], "Stage-3.1 BRF2 rank"),
                str(row["exchange_instrument_id"]),
            )
        )
    if not by_cutoff:
        raise Brf2NumericParityError("Stage-3.1 artifact has no BRF2 member decisions")
    expected: dict[int, tuple[str, ...]] = {}
    for cutoff, decisions in by_cutoff.items():
        ordered = tuple(sorted(decisions))
        ranks = tuple(rank for rank, _ in ordered)
        if ranks != tuple(range(1, 25)):
            raise Brf2NumericParityError(
                f"Stage-3.1 BRF2 rank surface is incomplete at {cutoff}"
            )
        expected[cutoff] = tuple(member for _, member in ordered[:_TOP_N])
    return expected


def _calculate_decimal_brf2_top16(
    *,
    cache_dir: Path,
    expected_top16_by_cutoff: Mapping[int, tuple[str, ...]],
) -> dict[int, tuple[str, ...]]:
    expected_members = frozenset().union(*map(frozenset, expected_top16_by_cutoff.values()))
    if not expected_members:
        raise Brf2NumericParityError("BRF2 expected member set is empty")
    all_members = _candidate_members_from_cache(cache_dir)
    windows = {
        instrument_id: _load_1h_closes(
            cache_dir=cache_dir,
            instrument_id=instrument_id,
        )
        for instrument_id in all_members
    }
    actual: dict[int, tuple[str, ...]] = {}
    for cutoff in sorted(expected_top16_by_cutoff):
        closes = {
            instrument_id: _window_at_cutoff(
                windows[instrument_id],
                cutoff=cutoff,
                count=73,
            )
            for instrument_id in all_members
        }
        actual[cutoff] = tuple(
            item.exchange_instrument_id
            for item in rank_brf2_residual_extension_v0_decimal(closes)[:_TOP_N]
        )
    return actual


def _candidate_members_from_cache(cache_dir: Path) -> tuple[str, ...]:
    normalized = cache_dir / "normalized"
    members = tuple(
        sorted(
            f"binance-usdm:{path.name.removesuffix('_1h.parquet')}:perpetual"
            for path in normalized.glob("*_1h.parquet")
        )
    )
    if len(members) != 24 or len(set(members)) != 24:
        raise Brf2NumericParityError("frozen cache must contain exactly 24 1h candidates")
    return members


def _load_1h_closes(
    *,
    cache_dir: Path,
    instrument_id: str,
) -> tuple[tuple[int, Decimal], ...]:
    symbol = instrument_id.split(":", 2)[1]
    rows = _read_parquet_rows(
        cache_dir / "normalized" / f"{symbol}_1h.parquet",
        columns=("close_time", "close"),
    )
    normalized = tuple(
        sorted(
            (
                _require_int(row["close_time"], f"1h close time for {symbol}"),
                Decimal(str(row["close"])),
            )
            for row in rows
        )
    )
    if not normalized or len({time for time, _ in normalized}) != len(normalized):
        raise Brf2NumericParityError(f"1h cache is invalid: {symbol}")
    return normalized


def _window_at_cutoff(
    rows: tuple[tuple[int, Decimal], ...],
    *,
    cutoff: int,
    count: int,
) -> tuple[Decimal, ...]:
    selected = tuple((time, close) for time, close in rows if time <= cutoff)[-count:]
    if len(selected) != count or selected[-1][0] != cutoff:
        raise Brf2NumericParityError(f"incomplete BRF2 source at cutoff {cutoff}")
    times = tuple(time for time, _ in selected)
    if times != tuple(cutoff - _ONE_HOUR_MS * offset for offset in range(count - 1, -1, -1)):
        raise Brf2NumericParityError(f"noncontiguous BRF2 source at cutoff {cutoff}")
    return tuple(close for _, close in selected)


def _read_parquet_rows(path: Path, *, columns: tuple[str, ...]) -> list[dict[str, object]]:
    try:
        from pyarrow import parquet  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise Brf2NumericParityError(
            "pyarrow is required only for this local numeric certification; "
            "install requirements-dev.txt"
        ) from exc
    if not path.is_file():
        raise Brf2NumericParityError(f"certification input is missing: {path}")
    table = parquet.read_table(path, columns=list(columns))
    return table.to_pylist()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise Brf2NumericParityError(f"certification input is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Brf2NumericParityError(f"invalid JSON certification input: {path}") from exc
    return _require_mapping(value, path.name)


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Brf2NumericParityError(f"{label} must be an object")
    return value


def _require_digest(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if len(normalized) != 71 or not normalized.startswith("sha256:"):
        raise Brf2NumericParityError(f"{label} is not a canonical sha256 digest")
    try:
        int(normalized[7:], 16)
    except ValueError as exc:
        raise Brf2NumericParityError(f"{label} is not a canonical sha256 digest") from exc
    return normalized


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise Brf2NumericParityError(f"{label} must be an integer")
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise Brf2NumericParityError(f"{label} must be an integer") from exc


def _validated_top16(members: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    if len(members) != _TOP_N or len(set(members)) != _TOP_N:
        raise Brf2NumericParityError(f"{label} must contain exactly 16 unique members")
    return members


if __name__ == "__main__":
    raise SystemExit(main())
