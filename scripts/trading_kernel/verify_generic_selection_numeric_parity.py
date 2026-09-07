#!/usr/bin/env python3
"""Certify frozen Generic Dynamic Selection numeric authority locally.

This tool is deliberately outside the production runtime.  It reads explicit,
immutable research inputs only when invoked for local certification; no worker,
repository, or exchange adapter imports it.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import zipfile
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.domain.dynamic_selection_numeric import (
    DYNAMIC_SELECTION_DECIMAL_CONTEXT,
    absolute_directional_efficiency_24h,
    persistent_leadership_score_6h,
    positive_impulse_recency_12h,
    rank_brf2_residual_extension_v0_decimal,
    rank_dynamic_selection_features,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

STAGE3_1_REPLAY_MANIFEST_SHA256 = (
    "sha256:289c75428742c1bebfa8b6585aaed82a8af0ae7b1b1feefcc482f017911f305e"
)
BRF2_STRATEGY_GROUP_ID = "BRF2-001"
_ONE_HOUR_MS = 60 * 60 * 1000
_TOP_N = 16
_REFERENCE_COMMIT = "f65d72fa92580de4b8c0323f4106d5975b97f4eb"


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
        raise Brf2NumericParityError(
            "Stage-3.1 member-decision artifact digest mismatch"
        )

    expected = _read_expected_brf2_top16(member_decisions_path)
    sources = load_frozen_hourly_sources(cache_dir)
    actual = {
        cutoff: tuple(
            item.exchange_instrument_id
            for item in rank_brf2_residual_extension_v0_decimal(
                {
                    member: _window_at_cutoff(rows, cutoff=cutoff, count=73)
                    for member, rows in sources.items()
                }
            )[:16]
        )
        for cutoff in expected
    }
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
    parser.add_argument("--sor-cache-dir", type=Path, required=True,
                        help="Frozen SOR 15m cache for the shared Golden/Core gate")
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
    matrix = certify_strategy_numeric_matrix(
        cache_dir=args.cache_dir.resolve(),
        artifact_dir=args.artifact_dir.resolve(),
    )
    from scripts.trading_kernel.verify_sor_dynamic_selection_core_parity import verify
    from scripts.trading_kernel.verify_sor_dynamic_selection_golden import (
        verify_artifact,
    )

    sor_artifacts = REPO_ROOT / "tests/trading_kernel/fixtures/sor_dynamic_selection_v0"
    verify_artifact(argparse.Namespace(artifact_dir=sor_artifacts, repo_root=REPO_ROOT,
                                      verify_inputs=True, cache_dir=args.sor_cache_dir.resolve()))
    matrix["sor_core"] = verify(argparse.Namespace(artifact_dir=sor_artifacts, cache_dir=args.sor_cache_dir.resolve()))
    matrix["SOR_GOLDEN"] = "PASS"
    print(json.dumps(matrix, sort_keys=True))
    return 0 if matrix["COMMON_NUMERIC_AUTHORITY"] == "PASS" else 1


def read_verified_archive(path: Path, expected_digest: str) -> list[list[str]]:
    """Read source price strings only after authenticating the archive bytes."""
    if _sha256_file(path) != expected_digest:
        raise Brf2NumericParityError(f"raw source digest mismatch: {path.name}")
    with zipfile.ZipFile(path) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise Brf2NumericParityError("raw archive requires one CSV")
        with archive.open(csv_names[0]) as stream:
            rows = list(csv.reader(io.TextIOWrapper(stream, encoding="utf-8")))
    if rows and rows[0][0] == "open_time":
        rows = rows[1:]
    return rows


def load_frozen_hourly_sources(
    cache_dir: Path,
) -> dict[str, tuple[tuple[int, Decimal], ...]]:
    """Verify all 96 raw hourly archives; normalized cache is never price authority."""
    manifest_path = cache_dir / "market_data_manifest.json"
    if (
        _sha256_file(manifest_path)
        != "sha256:09f0a8f03c93912a050c0778e4ebacb219ff81f847c7859fe1ba95bbe34cf094"
    ):
        raise Brf2NumericParityError("frozen market-data manifest digest mismatch")
    manifest = json.loads(manifest_path.read_text())
    sources: dict[str, dict[int, Decimal]] = {
        member: {} for member in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
    }
    seen: set[tuple[str, str]] = set()
    for meta in manifest["archives"]:
        if meta["interval"] != "1h":
            continue
        member = f"binance-usdm:{meta['symbol']}:perpetual"
        if member not in sources or (member, meta["period"]) in seen:
            raise Brf2NumericParityError("unexpected or duplicate source member/period")
        seen.add((member, meta["period"]))
        path = (cache_dir / "raw" / meta["relative_path"]).resolve()
        if not path.is_relative_to((cache_dir / "raw").resolve()):
            raise Brf2NumericParityError("source archive escaped cache root")
        rows = read_verified_archive(path, meta["sha256"])
        if len(rows) != meta["row_count"]:
            raise Brf2NumericParityError("raw archive cardinality mismatch")
        for row in rows:
            opened = int(row[0])
            if opened % _ONE_HOUR_MS or int(row[6]) != opened + _ONE_HOUR_MS - 1:
                raise Brf2NumericParityError("raw archive candle timing mismatch")
            close_time = opened + _ONE_HOUR_MS
            close = Decimal(row[4])
            if not close.is_finite() or close <= 0 or close_time in sources[member]:
                raise Brf2NumericParityError("invalid or duplicate raw close")
            sources[member][close_time] = close
    expected = {
        (member, period)
        for member in sources
        for period in ("2026-06", "2026-07", "2026-08", "2026-09-01")
    }
    if seen != expected:
        raise Brf2NumericParityError("missing frozen source archives")
    return {member: tuple(sorted(rows.items())) for member, rows in sources.items()}


def _frozen_reference_functions() -> dict[str, Any]:
    """Load only pure numeric function ASTs from exact committed research source.

    This offline certifier may read Git evidence; the production domain never
    imports research or runs these functions.
    """
    repo = Path(__file__).resolve().parents[2]
    paths = {
        "research/semantic_dynamic_selection_stage3_1/core.py": {
            "absolute_directional_efficiency_24h",
            "persistent_leadership_score_6h",
        },
        "research/semantic_dynamic_selection/features.py": {
            "positive_impulse_recency_12h",
            "residual_extension_z_24h",
        },
        "research/semantic_dynamic_selection/selection.py": {
            "_simple_returns",
            "_log_returns",
        },
    }
    namespace: dict[str, Any] = {
        "Decimal": Decimal,
        "fsum": math.fsum,
        "sqrt": math.sqrt,
        "log": math.log,
    }
    for path, required in paths.items():
        result = subprocess.run(
            ["git", "show", f"{_REFERENCE_COMMIT}:{path}"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        functions = [
            node
            for node in ast.parse(result.stdout).body
            if isinstance(node, ast.FunctionDef) and node.name in required
        ]
        if {node.name for node in functions} != required:
            raise Brf2NumericParityError("frozen numeric reference incomplete")
        exec(  # noqa: S102 -- offline, exact-commit pure numeric reference only
            compile(ast.Module(body=functions, type_ignores=[]), path, "exec"),
            namespace,
        )
    return namespace


def certify_strategy_numeric_matrix(
    *, cache_dir: Path, artifact_dir: Path
) -> dict[str, object]:
    manifest_path = artifact_dir / "stage3_1_replay_manifest.json"
    if _sha256_file(manifest_path) != STAGE3_1_REPLAY_MANIFEST_SHA256:
        raise Brf2NumericParityError("Stage-3.1 replay manifest digest mismatch")
    manifest = json.loads(manifest_path.read_text())
    artifact_path = artifact_dir / "stage3_1_member_decisions.parquet"
    if _sha256_file(artifact_path) != manifest["artifact_sha256"][artifact_path.name]:
        raise Brf2NumericParityError("member artifact digest mismatch")
    rows = _read_parquet_rows(
        artifact_path,
        columns=("strategy", "feature_cutoff_at_ms", "rank", "exchange_instrument_id"),
    )
    expected: dict[str, dict[int, list[tuple[int, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        expected[str(row["strategy"])][
            _require_int(row["feature_cutoff_at_ms"], "cutoff")
        ].append(
            (_require_int(row["rank"], "rank"), str(row["exchange_instrument_id"]))
        )
    cadences = {"CPM-RO-001": 4, "MPG-001": 1, "MI-001": 1, "BRF2-001": 4}
    if set(expected) != set(cadences):
        raise Brf2NumericParityError("strategy evidence matrix incomplete")
    sources = load_frozen_hourly_sources(cache_dir)
    reference = _frozen_reference_functions()
    matrix: dict[str, object] = {
        "COMMON_NUMERIC_AUTHORITY": "PASS",
        "reference_commit": _REFERENCE_COMMIT,
        "source_archive_count": 96,
        "strategies": {},
    }
    reports: dict[str, dict[str, Any]] = {}
    for strategy, cadence in cadences.items():
        cutoffs = tuple(range(1781467200000, 1788134400000, cadence * _ONE_HOUR_MS))
        if set(cutoffs) != set(expected[strategy]):
            raise Brf2NumericParityError(f"{strategy} frozen cutoff set differs")
        mismatches: list[int] = []
        for cutoff in cutoffs:
            ordered = sorted(expected[strategy][cutoff])
            if [rank for rank, _ in ordered] != list(range(1, 25)) or {
                member for _, member in ordered
            } != set(sources):
                raise Brf2NumericParityError("incomplete Candidate24 rank surface")
            windows = {
                member: _window_at_cutoff(source, cutoff=cutoff, count=73)
                for member, source in sources.items()
            }
            with localcontext(Context(prec=28)):
                reference_values = _strategy_values(
                    strategy, windows, reference=reference
                )
                reference_order = sorted(
                    reference_values, key=lambda m: (-reference_values[m], m)
                )
            if reference_order != [member for _, member in ordered]:
                raise Brf2NumericParityError(
                    f"research implementation/artifact rank mismatch: {strategy}@{cutoff}"
                )
            with localcontext(DYNAMIC_SELECTION_DECIMAL_CONTEXT):
                if strategy == "BRF2-001":
                    candidate_order = [
                        item.exchange_instrument_id
                        for item in rank_brf2_residual_extension_v0_decimal(windows)
                    ]
                else:
                    values = _strategy_values(strategy, windows, reference=None)
                    candidate_order = [
                        item.exchange_instrument_id
                        for item in rank_dynamic_selection_features(values)
                    ]
            thresholds = (12, 16) if strategy == "MPG-001" else (16,)
            if any(
                set(candidate_order[:n]) != set(reference_order[:n]) for n in thresholds
            ):
                mismatches.append(cutoff)
        reports[strategy] = {
            "status": "FAIL" if mismatches else "PASS",
            "checked_cutoffs": len(cutoffs),
            "mismatch_count": len(mismatches),
            "mismatch_cutoffs": mismatches,
        }
    matrix["strategies"] = reports
    for group, report in reports.items():
        matrix[f"{group.split('-')[0]}_SPEC_CERT"] = report["status"]
    matrix["numeric_source_sha256"] = _sha256_file(
        Path(__file__).resolve().parents[2]
        / "src/trading_kernel/domain/dynamic_selection_numeric.py"
    )
    return matrix


def _strategy_values(
    strategy: str,
    windows: Mapping[str, tuple[Decimal, ...]],
    *,
    reference: dict[str, Any] | None,
) -> dict[str, Decimal]:
    if strategy == "BRF2-001":
        if reference is None:
            raise AssertionError("BRF2 candidate uses the production panel function")
        returns = {m: reference["_log_returns"](w) for m, w in windows.items()}
        market = tuple(
            math.fsum(returns[m][j] for m in windows) / 24 for j in range(72)
        )
        return {
            m: Decimal(str(reference["residual_extension_z_24h"](r, market)))
            for m, r in returns.items()
        }
    if strategy == "CPM-RO-001":
        function = (
            reference["absolute_directional_efficiency_24h"]
            if reference
            else absolute_directional_efficiency_24h
        )
        return {m: function(w[-25:]) for m, w in windows.items()}
    if strategy == "MI-001":
        function = (
            reference["positive_impulse_recency_12h"]
            if reference
            else positive_impulse_recency_12h
        )
        return {
            m: function(tuple(w[j] / w[j - 1] - 1 for j in range(len(w) - 12, len(w))))
            for m, w in windows.items()
        }
    history: dict[str, list[int]] = {m: [] for m in windows}
    for offset in range(5, -1, -1):
        returns = {
            m: (w[-1 - offset] - w[-9 - offset]) / w[-9 - offset] * 100
            for m, w in windows.items()
        }
        for rank, member in enumerate(
            sorted(returns, key=lambda m: (-returns[m], m)), 1
        ):
            history[member].append(rank)
    function = (
        reference["persistent_leadership_score_6h"]
        if reference
        else persistent_leadership_score_6h
    )
    return {m: function(tuple(ranks)) for m, ranks in history.items()}


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
    if times != tuple(
        cutoff - _ONE_HOUR_MS * offset for offset in range(count - 1, -1, -1)
    ):
        raise Brf2NumericParityError(f"noncontiguous BRF2 source at cutoff {cutoff}")
    return tuple(close for _, close in selected)


def _read_parquet_rows(
    path: Path, *, columns: tuple[str, ...]
) -> list[dict[str, object]]:
    try:
        from pyarrow import parquet  # type: ignore[import-untyped]
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
        raise Brf2NumericParityError(
            f"invalid JSON certification input: {path}"
        ) from exc
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
        raise Brf2NumericParityError(
            f"{label} is not a canonical sha256 digest"
        ) from exc
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
