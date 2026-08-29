"""Build and verify the frozen SOR Dynamic Selection V0 Golden artifact.

This is a bounded local research/test utility. Production runtime code must not
import it or read its tracked artifact. The build path reads the frozen public
Binance 15m cache and writes only the explicit test-fixture directory.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from itertools import pairwise
from pathlib import Path
from typing import Any, TextIO

INTERVAL_MS = 15 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
SESSION_START_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z
SESSION_END_MS = 1_787_011_200_000  # 2026-08-18T00:00:00Z inclusive
EXPECTED_SESSIONS = 961
EXPECTED_MEMBERS = 24
EXPECTED_ROWS = EXPECTED_SESSIONS * EXPECTED_MEMBERS
ACTIVITY_FLOOR = Decimal(20000000)
DECIMAL_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
RESEARCH_SPEC_ID = "sor-dynamic-selection-v0"
STRATEGY_GROUP_ID = "SOR-001"
STRATEGY_VERSION_ID = "sgv:SOR-001:v4"
LONG_EVENT_SPEC_ID = "event_spec:SOR-001:SOR-LONG:v4"
SHORT_EVENT_SPEC_ID = "event_spec:SOR-001:SOR-SHORT:v4"

CANDIDATE_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "DOTUSDT",
    "NEARUSDT",
    "ATOMUSDT",
    "FILUSDT",
    "ETCUSDT",
    "APTUSDT",
    "OPUSDT",
    "ARBUSDT",
    "INJUSDT",
    "SUIUSDT",
    "TRXUSDT",
    "UNIUSDT",
    "RUNEUSDT",
)

SELECTION_SEMANTIC_SOURCE_PATHS = (
    "src/trading_kernel/domain/detectors/sor.py",
    "src/trading_kernel/domain/instrument_selection.py",
)
RESEARCH_PROVENANCE_SOURCE_PATHS = (
    "src/trading_kernel/domain/strategy_registry.py",
    "src/trading_kernel/domain/exit_policy.py",
)

STATIC_SYMBOLS = frozenset(
    {
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
    }
)

MEMBER_COLUMNS = (
    "selection_snapshot_id",
    "member_decision_id",
    "selection_spec_id",
    "session_start_ms",
    "feature_cutoff_at_ms",
    "input_window_start_ms",
    "input_window_end_ms",
    "exchange_instrument_id",
    "symbol",
    "input_window_digest",
    "source_status",
    "or_high",
    "or_low",
    "or_width",
    "pre_or_atr14",
    "pre_or_width_atr14",
    "trailing_24h_quote_volume",
    "or_geometry_valid",
    "atr_valid",
    "activity_valid",
    "selection_ready",
    "primary_reason",
    "secondary_reasons_json",
    "stable_rank",
    "member_state",
    "selected",
    "member_semantic_digest",
    "selection_semantic_digest",
)

SNAPSHOT_COLUMNS = (
    "selection_snapshot_id",
    "selection_spec_id",
    "strategy_group_id",
    "strategy_version_id",
    "session_start_ms",
    "feature_cutoff_at_ms",
    "eligibility_not_before_ms",
    "expires_at_ms",
    "candidate_count",
    "ready_count",
    "selected_count",
    "source_semantic_digest",
    "selection_semantic_digest",
)

MEMBER_DIGEST_FIELDS = tuple(
    column
    for column in MEMBER_COLUMNS
    if column not in {"member_semantic_digest", "selection_semantic_digest"}
)

EXPECTED_REPLAY_COUNTS: dict[str, Any] = {
    "sessions": 961,
    "member_rows": 23064,
    "ready_min": 14,
    "ready_max": 24,
    "state_counts": {
        "INELIGIBLE": 892,
        "SELECTED": 6727,
        "NEAR_THRESHOLD": 6727,
        "NOT_SELECTED": 8718,
    },
    "dynamic": {"triggers": 11259, "tail3": 1323, "tp1": 2989, "reclaim": 7732},
    "static": {"triggers": 10905, "tail3": 1067, "tp1": 2601, "reclaim": 7873},
    "near": {"triggers": 10980, "tail3": 1116},
    "not_selected": {"triggers": 13603, "tail3": 1078},
    "selected_direction_tail3": {"long": 625, "short": 698},
}

EXTERNAL_BINARY_FLOAT_REPLAY_COUNTS: dict[str, object] = {
    "dynamic": {"triggers": 11259, "tail3": 1324, "tp1": 2992, "reclaim": 7729},
    "static": {"triggers": 10905, "tail3": 1067, "tp1": 2601, "reclaim": 7873},
    "near": {"triggers": 10982, "tail3": 1116},
    "not_selected": {"triggers": 13601, "tail3": 1077},
    "selected_direction_tail3": {"long": 625, "short": 699},
}


class GoldenError(RuntimeError):
    """Fail-closed error for Golden build or verification."""


@dataclass(frozen=True)
class Kline:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    quote_volume: Decimal


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _semantic_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _instrument_id(symbol: str) -> str:
    return f"binance-usdm:{symbol}:perpetual"


def _snapshot_id(session_start_ms: int) -> str:
    return f"selection:{RESEARCH_SPEC_ID}:{session_start_ms}"


def _session_starts() -> tuple[int, ...]:
    sessions = tuple(range(SESSION_START_MS, SESSION_END_MS + DAY_MS, DAY_MS))
    if len(sessions) != EXPECTED_SESSIONS:
        raise GoldenError(f"session contract drifted: {len(sessions)}")
    return sessions


def _selection_spec_payload() -> dict[str, object]:
    return {
        "research_spec_id": RESEARCH_SPEC_ID,
        "strategy_group_id": STRATEGY_GROUP_ID,
        "strategy_version_id": STRATEGY_VERSION_ID,
        "event_spec_ids": [LONG_EVENT_SPEC_ID, SHORT_EVENT_SPEC_ID],
        "candidate_exchange_instrument_ids": [
            _instrument_id(symbol) for symbol in CANDIDATE_SYMBOLS
        ],
        "selection_timezone": "UTC",
        "selection_time": "01:00:00",
        "feature_cutoff_offset_ms": 60 * 60 * 1000,
        "eligibility_not_before_offset_ms": 75 * 60 * 1000,
        "expires_offset_ms": DAY_MS + 60 * 60 * 1000,
        "input_window_bars": 96,
        "or_bars": 4,
        "pre_or_atr_bars": 14,
        "activity_floor_quote_usdt": "20000000",
        "ranking": [
            "pre_or_width_atr14:asc",
            "trailing_24h_quote_volume:desc",
            "exchange_instrument_id:asc",
        ],
        "selected_cap": 7,
        "near_rank_start": 8,
        "near_rank_end": 14,
        "decimal_context": {"precision": 38, "rounding": "ROUND_HALF_EVEN"},
        "feature_numeric_type": "decimal.Decimal",
        "canonical_decimal": "normalize; zero='0'; fixed-point; no exponent",
        "digest_serialization": "utf8-json; sort_keys=true; separators=(',', ':')",
    }


def _source_file_for(cache_dir: Path, symbol: str) -> Path:
    matches = sorted(cache_dir.glob(f"{symbol}_15m_*.csv.gz"))
    if len(matches) != 1:
        raise GoldenError(
            f"{symbol} requires exactly one frozen cache file; found={len(matches)}"
        )
    return matches[0]


def _read_klines(path: Path) -> tuple[dict[int, Kline], dict[str, object]]:
    rows: dict[int, Kline] = {}
    first_open: int | None = None
    last_open: int | None = None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "quote_volume",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise GoldenError(f"cache columns invalid: {path}")
        for raw in reader:
            open_time_ms = int(raw["open_time"])
            if open_time_ms in rows:
                raise GoldenError(f"duplicate Kline open_time: {path}:{open_time_ms}")
            kline = Kline(
                open_time_ms=open_time_ms,
                open=Decimal(raw["open"]),
                high=Decimal(raw["high"]),
                low=Decimal(raw["low"]),
                close=Decimal(raw["close"]),
                quote_volume=Decimal(raw["quote_volume"]),
            )
            if (
                not all(
                    value.is_finite() and value > 0
                    for value in (kline.open, kline.high, kline.low, kline.close)
                )
                or not kline.quote_volume.is_finite()
                or kline.quote_volume < 0
                or kline.high < max(kline.open, kline.close, kline.low)
                or kline.low > min(kline.open, kline.close, kline.high)
            ):
                raise GoldenError(f"invalid price/volume Kline: {path}:{open_time_ms}")
            rows[open_time_ms] = kline
            first_open = open_time_ms if first_open is None else min(first_open, open_time_ms)
            last_open = open_time_ms if last_open is None else max(last_open, open_time_ms)

    if not rows or first_open is None or last_open is None:
        raise GoldenError(f"empty cache file: {path}")
    ordered_times = sorted(rows)
    irregular_steps = sum(
        right - left != INTERVAL_MS
        for left, right in pairwise(ordered_times)
    )
    if irregular_steps:
        raise GoldenError(f"irregular cache cadence: {path}:{irregular_steps}")
    return rows, {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "row_count": len(rows),
        "first_open_time_ms": first_open,
        "last_open_time_ms": last_open,
        "duplicate_count": 0,
        "irregular_step_count": irregular_steps,
    }


def _exact_window(rows: Mapping[int, Kline], start_ms: int, count: int) -> tuple[Kline, ...]:
    times = tuple(start_ms + index * INTERVAL_MS for index in range(count))
    try:
        return tuple(rows[open_time_ms] for open_time_ms in times)
    except KeyError as exc:
        raise GoldenError(f"source window missing open_time_ms={exc.args[0]}") from exc


def _window_digest(window: Sequence[Kline]) -> str:
    return _semantic_digest(
        [
            [
                item.open_time_ms,
                _canonical_decimal(item.open),
                _canonical_decimal(item.high),
                _canonical_decimal(item.low),
                _canonical_decimal(item.close),
                _canonical_decimal(item.quote_volume),
            ]
            for item in window
        ]
    )


def _member_for_session(
    *, symbol: str, rows: Mapping[int, Kline], session_start_ms: int
) -> dict[str, str]:
    window_start_ms = session_start_ms - 23 * 60 * 60 * 1000
    window = _exact_window(rows, window_start_ms, 96)
    if window[-1].open_time_ms != session_start_ms + 45 * 60 * 1000:
        raise GoldenError(f"cutoff window drifted: {symbol}:{session_start_ms}")
    previous_atr_bar = window[77]
    pre_or_bars = window[78:92]
    or_bars = window[92:96]
    if len(pre_or_bars) != 14 or len(or_bars) != 4:
        raise GoldenError("feature window partition drifted")

    previous_close = previous_atr_bar.close
    true_ranges: list[Decimal] = []
    for bar in pre_or_bars:
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
        previous_close = bar.close

    or_high = max(bar.high for bar in or_bars)
    or_low = min(bar.low for bar in or_bars)
    or_width = or_high - or_low
    pre_or_atr14 = sum(true_ranges, Decimal(0)) / Decimal(14)
    activity = sum((bar.quote_volume for bar in window), Decimal(0))
    or_geometry_valid = or_high > or_low
    atr_valid = pre_or_atr14 > 0
    activity_valid = activity >= ACTIVITY_FLOOR
    if not or_geometry_valid:
        primary_reason = "INVALID_OR_GEOMETRY"
    elif not atr_valid:
        primary_reason = "INVALID_ATR"
    elif not activity_valid:
        primary_reason = "LOW_ACTIVITY"
    else:
        primary_reason = ""
    selection_ready = primary_reason == ""
    ratio = Decimal(0) if not atr_valid else or_width / pre_or_atr14
    snapshot_id = _snapshot_id(session_start_ms)
    instrument_id = _instrument_id(symbol)
    return {
        "selection_snapshot_id": snapshot_id,
        "member_decision_id": f"{snapshot_id}:{instrument_id}",
        "selection_spec_id": RESEARCH_SPEC_ID,
        "session_start_ms": str(session_start_ms),
        "feature_cutoff_at_ms": str(session_start_ms + 60 * 60 * 1000),
        "input_window_start_ms": str(window_start_ms),
        "input_window_end_ms": str(session_start_ms + 60 * 60 * 1000),
        "exchange_instrument_id": instrument_id,
        "symbol": symbol,
        "input_window_digest": _window_digest(window),
        "source_status": "READY",
        "or_high": _canonical_decimal(or_high),
        "or_low": _canonical_decimal(or_low),
        "or_width": _canonical_decimal(or_width),
        "pre_or_atr14": _canonical_decimal(pre_or_atr14),
        "pre_or_width_atr14": _canonical_decimal(ratio),
        "trailing_24h_quote_volume": _canonical_decimal(activity),
        "or_geometry_valid": str(or_geometry_valid).lower(),
        "atr_valid": str(atr_valid).lower(),
        "activity_valid": str(activity_valid).lower(),
        "selection_ready": str(selection_ready).lower(),
        "primary_reason": primary_reason,
        "secondary_reasons_json": "[]",
        "stable_rank": "",
        "member_state": "INELIGIBLE" if not selection_ready else "PENDING_RANK",
        "selected": "false",
        "member_semantic_digest": "",
        "selection_semantic_digest": "",
    }


def _rank_session(members: list[dict[str, str]]) -> dict[str, str]:
    if len(members) != EXPECTED_MEMBERS:
        raise GoldenError(f"snapshot member cardinality invalid: {len(members)}")
    ready = [member for member in members if member["selection_ready"] == "true"]
    ready.sort(
        key=lambda member: (
            Decimal(member["pre_or_width_atr14"]),
            -Decimal(member["trailing_24h_quote_volume"]),
            member["exchange_instrument_id"],
        )
    )
    for rank, member in enumerate(ready, start=1):
        member["stable_rank"] = str(rank)
        if rank <= 7:
            member["member_state"] = "SELECTED"
            member["selected"] = "true"
        elif rank <= 14:
            member["member_state"] = "NEAR_THRESHOLD"
        else:
            member["member_state"] = "NOT_SELECTED"

    for member in members:
        member["member_semantic_digest"] = _semantic_digest(
            {field: member[field] for field in MEMBER_DIGEST_FIELDS}
        )
    ordered = sorted(members, key=lambda member: member["exchange_instrument_id"])
    session_start_ms = int(ordered[0]["session_start_ms"])
    source_digest = _semantic_digest(
        [
            [member["exchange_instrument_id"], member["input_window_digest"]]
            for member in ordered
        ]
    )
    selection_spec_digest = _semantic_digest(_selection_spec_payload())
    selection_digest = _semantic_digest(
        {
            "selection_spec_digest": selection_spec_digest,
            "selection_spec_id": RESEARCH_SPEC_ID,
            "session_start_ms": session_start_ms,
            "feature_cutoff_at_ms": session_start_ms + 60 * 60 * 1000,
            "eligibility_not_before_ms": session_start_ms + 75 * 60 * 1000,
            "expires_at_ms": session_start_ms + DAY_MS + 60 * 60 * 1000,
            "candidate_count": EXPECTED_MEMBERS,
            "ready_count": len(ready),
            "selected_count": min(7, len(ready)),
            "source_semantic_digest": source_digest,
            "member_semantic_digests": [
                member["member_semantic_digest"] for member in ordered
            ],
        }
    )
    for member in members:
        member["selection_semantic_digest"] = selection_digest
    return {
        "selection_snapshot_id": _snapshot_id(session_start_ms),
        "selection_spec_id": RESEARCH_SPEC_ID,
        "strategy_group_id": STRATEGY_GROUP_ID,
        "strategy_version_id": STRATEGY_VERSION_ID,
        "session_start_ms": str(session_start_ms),
        "feature_cutoff_at_ms": str(session_start_ms + 60 * 60 * 1000),
        "eligibility_not_before_ms": str(session_start_ms + 75 * 60 * 1000),
        "expires_at_ms": str(session_start_ms + DAY_MS + 60 * 60 * 1000),
        "candidate_count": str(EXPECTED_MEMBERS),
        "ready_count": str(len(ready)),
        "selected_count": str(min(7, len(ready))),
        "source_semantic_digest": source_digest,
        "selection_semantic_digest": selection_digest,
    }


def _deterministic_gzip_csv(
    path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, str]]
) -> tuple[str, str]:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row[field] for field in fieldnames})
    raw = buffer.getvalue().encode("utf-8")
    with (
        path.open("wb") as file_stream,
        gzip.GzipFile(fileobj=file_stream, mode="wb", filename="", mtime=0) as stream,
    ):
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest(), _sha256_file(path)


def _read_events(
    stream: TextIO, events: dict[tuple[int, str], list[dict[str, str]]]
) -> None:
    reader = csv.DictReader(stream)
    required = {
        "symbol",
        "session_ms",
        "direction",
        "policy_tail3_cons",
        "policy_tp1_success_cons",
        "reclaim_before_tp1",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise GoldenError("events evidence columns invalid")
    for row in reader:
        session_start_ms = int(row["session_ms"])
        if SESSION_START_MS <= session_start_ms <= SESSION_END_MS:
            events[(session_start_ms, row["symbol"])].append(row)


def _load_events(path: Path) -> dict[tuple[int, str], list[dict[str, str]]]:
    events: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            _read_events(stream, events)
    else:
        with path.open("rt", encoding="utf-8", newline="") as stream:
            _read_events(stream, events)
    return events


def _metric_counts(
    decisions: Sequence[Mapping[str, str]], events_path: Path
) -> dict[str, object]:
    events = _load_events(events_path)
    policies: dict[str, list[Mapping[str, str]]] = {
        "dynamic": [row for row in decisions if row["member_state"] == "SELECTED"],
        "static": [row for row in decisions if row["symbol"] in STATIC_SYMBOLS],
        "near": [row for row in decisions if row["member_state"] == "NEAR_THRESHOLD"],
        "not_selected": [
            row for row in decisions if row["member_state"] == "NOT_SELECTED"
        ],
    }
    result: dict[str, object] = {}
    for policy, members in policies.items():
        trigger_count = 0
        tail3_count = 0
        tp1_count = 0
        reclaim_count = 0
        direction_tail3: Counter[str] = Counter()
        for member in members:
            key = (int(member["session_start_ms"]), member["symbol"])
            for event in events.get(key, []):
                trigger_count += 1
                tail3 = int(event["policy_tail3_cons"])
                tail3_count += tail3
                tp1_count += int(event["policy_tp1_success_cons"])
                reclaim_count += int(event["reclaim_before_tp1"])
                direction_tail3[event["direction"]] += tail3
        result[policy] = {
            "member_days": len(members),
            "directional_slot_days": len(members) * 2,
            "triggers": trigger_count,
            "tail3": tail3_count,
            "tp1": tp1_count,
            "reclaim": reclaim_count,
            "direction_tail3": dict(sorted(direction_tail3.items())),
        }
    return result


def _assert_replay_parity(
    decisions: Sequence[Mapping[str, str]], snapshots: Sequence[Mapping[str, str]], metrics: Mapping[str, object]
) -> None:
    ready_counts = [int(row["ready_count"]) for row in snapshots]
    state_counts = Counter(row["member_state"] for row in decisions)
    actual = {
        "sessions": len(snapshots),
        "member_rows": len(decisions),
        "ready_min": min(ready_counts),
        "ready_max": max(ready_counts),
        "state_counts": dict(sorted(state_counts.items())),
        "dynamic": {
            field: metrics["dynamic"][field]  # type: ignore[index]
            for field in ("triggers", "tail3", "tp1", "reclaim")
        },
        "static": {
            field: metrics["static"][field]  # type: ignore[index]
            for field in ("triggers", "tail3", "tp1", "reclaim")
        },
        "near": {
            field: metrics["near"][field]  # type: ignore[index]
            for field in ("triggers", "tail3")
        },
        "not_selected": {
            field: metrics["not_selected"][field]  # type: ignore[index]
            for field in ("triggers", "tail3")
        },
        "selected_direction_tail3": metrics["dynamic"]["direction_tail3"],  # type: ignore[index]
    }
    if actual != EXPECTED_REPLAY_COUNTS:
        raise GoldenError(
            "independent replay parity failed:\n"
            + json.dumps({"expected": EXPECTED_REPLAY_COUNTS, "actual": actual}, indent=2)
        )


def build_artifact(args: argparse.Namespace) -> None:
    repo_root = args.repo_root.resolve()
    cache_dir = args.cache_dir.resolve()
    output_dir = args.output_dir.resolve()
    events_path = args.events.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sessions = _session_starts()
    decisions_by_session: dict[int, list[dict[str, str]]] = {
        session: [] for session in sessions
    }
    input_files: list[dict[str, object]] = []

    with localcontext(DECIMAL_CONTEXT):
        for symbol in CANDIDATE_SYMBOLS:
            source_path = _source_file_for(cache_dir, symbol)
            rows, source_meta = _read_klines(source_path)
            source_meta["symbol"] = symbol
            source_meta["exchange_instrument_id"] = _instrument_id(symbol)
            input_files.append(source_meta)
            for session_start_ms in sessions:
                decisions_by_session[session_start_ms].append(
                    _member_for_session(
                        symbol=symbol,
                        rows=rows,
                        session_start_ms=session_start_ms,
                    )
                )

        snapshots: list[dict[str, str]] = []
        decisions: list[dict[str, str]] = []
        for session_start_ms in sessions:
            members = decisions_by_session[session_start_ms]
            snapshots.append(_rank_session(members))
            decisions.extend(
                sorted(members, key=lambda member: member["exchange_instrument_id"])
            )

    metrics = _metric_counts(decisions, events_path)
    _assert_replay_parity(decisions, snapshots, metrics)
    member_path = output_dir / "member_decisions.csv.gz"
    snapshot_path = output_dir / "selection_snapshots.csv.gz"
    member_content_sha, member_file_sha = _deterministic_gzip_csv(
        member_path, MEMBER_COLUMNS, decisions
    )
    snapshot_content_sha, snapshot_file_sha = _deterministic_gzip_csv(
        snapshot_path, SNAPSHOT_COLUMNS, snapshots
    )
    selection_spec_payload = _selection_spec_payload()
    selection_spec_digest = _semantic_digest(selection_spec_payload)
    source_set_digest = _semantic_digest(
        [
            {
                key: item[key]
                for key in (
                    "symbol",
                    "exchange_instrument_id",
                    "filename",
                    "size_bytes",
                    "sha256",
                    "row_count",
                    "first_open_time_ms",
                    "last_open_time_ms",
                )
            }
            for item in sorted(input_files, key=lambda item: str(item["symbol"]))
        ]
    )
    generator_path = Path(__file__).resolve()
    source_files = {
        relative: _sha256_file(repo_root / relative)
        for relative in SELECTION_SEMANTIC_SOURCE_PATHS
    }
    provenance_files = {
        "events_csv": {"path_label": events_path.name, "sha256": _sha256_file(events_path)},
        **{
            f"research_source:{relative}": {
                "path_label": relative,
                "sha256": _sha256_file(repo_root / relative),
            }
            for relative in RESEARCH_PROVENANCE_SOURCE_PATHS
        },
    }
    for label, path in (
        ("independent_replay_report", args.report),
        ("instrument_effect_results_archive", args.results_archive),
    ):
        if path is not None:
            resolved = path.resolve()
            provenance_files[label] = {
                "path_label": resolved.name,
                "sha256": _sha256_file(resolved),
            }
    manifest = {
        "schema_version": "sor-dynamic-selection-golden-v1",
        "research_spec_id": RESEARCH_SPEC_ID,
        "selection_spec": selection_spec_payload,
        "selection_spec_digest": selection_spec_digest,
        "session_start_ms": SESSION_START_MS,
        "session_end_ms_inclusive": SESSION_END_MS,
        "expected_sessions": EXPECTED_SESSIONS,
        "expected_members_per_session": EXPECTED_MEMBERS,
        "expected_member_rows": EXPECTED_ROWS,
        "source_set_digest": source_set_digest,
        "input_files": sorted(input_files, key=lambda item: str(item["symbol"])),
        "source_semantic_identity": source_files,
        "generator": {
            "path": "scripts/trading_kernel/verify_sor_dynamic_selection_golden.py",
            "sha256": _sha256_file(generator_path),
            "python": sys.version,
        },
        "artifacts": {
            "member_decisions": {
                "path": member_path.name,
                "sha256": member_file_sha,
                "uncompressed_content_sha256": member_content_sha,
                "rows": len(decisions),
            },
            "selection_snapshots": {
                "path": snapshot_path.name,
                "sha256": snapshot_file_sha,
                "uncompressed_content_sha256": snapshot_content_sha,
                "rows": len(snapshots),
            },
        },
        "artifact_set_digest": _semantic_digest(
            {
                "selection_spec_digest": selection_spec_digest,
                "source_set_digest": source_set_digest,
                "member_file_sha256": member_file_sha,
                "snapshot_file_sha256": snapshot_file_sha,
            }
        ),
        "independent_replay_parity": {
            "expected_counts": EXPECTED_REPLAY_COUNTS,
            "computed_policy_metrics": metrics,
        },
        "numeric_representation_resolution": {
            "approved_golden_numeric_type": "decimal.Decimal",
            "approved_decimal_context": {
                "precision": 38,
                "rounding": "ROUND_HALF_EVEN",
            },
            "external_report_numeric_type": "binary64 float",
            "external_report_counts": EXTERNAL_BINARY_FLOAT_REPLAY_COUNTS,
            "cohort_boundary_sessions_changed_by_decimal": 7,
            "resolution": (
                "The independent REPORT.md counts are exactly reproducible with "
                "binary64 feature arithmetic. The approved research and production "
                "contracts require Decimal price geometry, so this Golden freezes "
                "the deterministic Decimal result instead of preserving float "
                "rounding noise at equal-ratio ranking boundaries."
            ),
        },
        "provenance_files": provenance_files,
        "test_portfolio": {
            "focused": [
                "artifact verifier: manifest/cardinality/digest/snapshot-member invariants",
                "negative verification: missing artifact, corrupted digest, wrong cardinality",
            ],
            "fast": [
                "focused verifier",
                "production import boundary scan",
                "current document authority tests",
                "project Skill authority tests",
                "Ruff for the verifier",
                "Mypy for the verifier",
                "git diff --check",
            ],
            "release": [
                "rebuild Golden from frozen cache",
                "byte-deterministic artifact comparison",
                "DS-03 SelectionCore parity against all 961x24 decisions",
            ],
            "fixture_review": {
                "reused": [
                    "existing frozen 24-symbol Binance 15m cache",
                    "existing Instrument Effect v1 events.csv.gz",
                ],
                "new": [
                    "member_decisions.csv.gz",
                    "selection_snapshots.csv.gz",
                    "manifest.json",
                ],
                "deleted_or_merged": [],
                "reason": "no existing Kernel fixture owns member-level Dynamic Selection decisions",
            },
        },
        "runtime_authority": "TEST_ONLY_NEVER_PRODUCTION_INPUT",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verify_artifact(
        argparse.Namespace(
            artifact_dir=output_dir,
            repo_root=repo_root,
            cache_dir=cache_dir,
            verify_inputs=True,
        )
    )
    print(
        json.dumps(
            {
                "status": "built_and_verified",
                "artifact_dir": str(output_dir),
                "artifact_set_digest": manifest["artifact_set_digest"],
                "member_rows": len(decisions),
                "snapshots": len(snapshots),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _read_gzip_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]], str]:
    digest = hashlib.sha256()
    rows: list[dict[str, str]] = []
    with gzip.open(path, "rb") as binary:
        raw = binary.read()
    digest.update(raw)
    stream = io.StringIO(raw.decode("utf-8"), newline="")
    reader = csv.DictReader(stream)
    fieldnames = tuple(reader.fieldnames or ())
    rows.extend(dict(row) for row in reader)
    return fieldnames, rows, digest.hexdigest()


def _verify_member_row(row: Mapping[str, str]) -> None:
    actual = _semantic_digest({field: row[field] for field in MEMBER_DIGEST_FIELDS})
    if row["member_semantic_digest"] != actual:
        raise GoldenError(f"member digest mismatch: {row['member_decision_id']}")


def _verify_production_import_boundary(repo_root: Path) -> None:
    forbidden_markers = (
        "sor_dynamic_selection_v0_golden",
        "tests/trading_kernel/fixtures/sor_dynamic_selection_v0",
        "member_decisions.csv.gz",
    )
    violations: list[str] = []
    for path in sorted((repo_root / "src" / "trading_kernel").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in source:
                violations.append(f"{path.relative_to(repo_root)}:{marker}")
    if violations:
        raise GoldenError("production artifact dependency detected: " + ", ".join(violations))


def verify_artifact(args: argparse.Namespace) -> None:
    artifact_dir = args.artifact_dir.resolve()
    repo_root = args.repo_root.resolve()
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        raise GoldenError(f"Golden manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "sor-dynamic-selection-golden-v1":
        raise GoldenError("Golden schema version mismatch")
    if manifest.get("expected_sessions") != EXPECTED_SESSIONS:
        raise GoldenError("manifest session cardinality mismatch")
    if manifest.get("expected_members_per_session") != EXPECTED_MEMBERS:
        raise GoldenError("manifest member cardinality mismatch")
    if manifest.get("expected_member_rows") != EXPECTED_ROWS:
        raise GoldenError("manifest row cardinality mismatch")
    if manifest.get("selection_spec_digest") != _semantic_digest(_selection_spec_payload()):
        raise GoldenError("SelectionSpec digest mismatch")

    artifact_meta = manifest["artifacts"]
    member_path = artifact_dir / artifact_meta["member_decisions"]["path"]
    snapshot_path = artifact_dir / artifact_meta["selection_snapshots"]["path"]
    for path, meta in (
        (member_path, artifact_meta["member_decisions"]),
        (snapshot_path, artifact_meta["selection_snapshots"]),
    ):
        if not path.is_file():
            raise GoldenError(f"Golden artifact missing: {path}")
        if _sha256_file(path) != meta["sha256"]:
            raise GoldenError(f"Golden file digest mismatch: {path.name}")

    member_fields, members, member_content_sha = _read_gzip_csv(member_path)
    snapshot_fields, snapshots, snapshot_content_sha = _read_gzip_csv(snapshot_path)
    if member_fields != MEMBER_COLUMNS:
        raise GoldenError("member artifact columns mismatch")
    if snapshot_fields != SNAPSHOT_COLUMNS:
        raise GoldenError("snapshot artifact columns mismatch")
    if member_content_sha != artifact_meta["member_decisions"]["uncompressed_content_sha256"]:
        raise GoldenError("member uncompressed content digest mismatch")
    if snapshot_content_sha != artifact_meta["selection_snapshots"]["uncompressed_content_sha256"]:
        raise GoldenError("snapshot uncompressed content digest mismatch")
    if len(members) != EXPECTED_ROWS or len(snapshots) != EXPECTED_SESSIONS:
        raise GoldenError(
            f"Golden cardinality mismatch: members={len(members)} snapshots={len(snapshots)}"
        )

    members_by_session: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in members:
        _verify_member_row(row)
        members_by_session[int(row["session_start_ms"])].append(row)
    if set(members_by_session) != set(_session_starts()):
        raise GoldenError("Golden session identity set mismatch")

    snapshot_by_session = {int(row["session_start_ms"]): row for row in snapshots}
    if len(snapshot_by_session) != EXPECTED_SESSIONS:
        raise GoldenError("duplicate snapshot session identity")
    ready_counts: list[int] = []
    state_counts: Counter[str] = Counter()
    for session_start_ms in _session_starts():
        session_members = members_by_session[session_start_ms]
        if len(session_members) != EXPECTED_MEMBERS:
            raise GoldenError(f"member cardinality mismatch for session={session_start_ms}")
        if {row["symbol"] for row in session_members} != set(CANDIDATE_SYMBOLS):
            raise GoldenError(f"candidate panel mismatch for session={session_start_ms}")
        ranks = sorted(
            int(row["stable_rank"])
            for row in session_members
            if row["stable_rank"]
        )
        ready_count = sum(row["selection_ready"] == "true" for row in session_members)
        selected_count = sum(row["selected"] == "true" for row in session_members)
        if ranks != list(range(1, ready_count + 1)):
            raise GoldenError(f"rank sequence mismatch for session={session_start_ms}")
        if selected_count != min(7, ready_count):
            raise GoldenError(f"selected count mismatch for session={session_start_ms}")
        ready_counts.append(ready_count)
        state_counts.update(row["member_state"] for row in session_members)
        snapshot = snapshot_by_session[session_start_ms]
        if int(snapshot["ready_count"]) != ready_count:
            raise GoldenError(f"snapshot ready count mismatch: {session_start_ms}")
        if int(snapshot["selected_count"]) != selected_count:
            raise GoldenError(f"snapshot selected count mismatch: {session_start_ms}")
        if any(
            row["selection_semantic_digest"] != snapshot["selection_semantic_digest"]
            for row in session_members
        ):
            raise GoldenError(f"snapshot/member digest mismatch: {session_start_ms}")

    if min(ready_counts) != 14 or max(ready_counts) != 24:
        raise GoldenError("historical Ready range mismatch")
    if dict(sorted(state_counts.items())) != EXPECTED_REPLAY_COUNTS["state_counts"]:
        raise GoldenError("historical state counts mismatch")
    if manifest["independent_replay_parity"]["expected_counts"] != EXPECTED_REPLAY_COUNTS:
        raise GoldenError("manifest replay parity contract mismatch")

    generator = repo_root / manifest["generator"]["path"]
    if not generator.is_file() or _sha256_file(generator) != manifest["generator"]["sha256"]:
        raise GoldenError("Golden generator identity drifted")
    for relative, expected_sha in manifest["source_semantic_identity"].items():
        path = repo_root / relative
        if not path.is_file() or _sha256_file(path) != expected_sha:
            raise GoldenError(f"source semantic identity drifted: {relative}")

    if args.verify_inputs:
        if args.cache_dir is None:
            raise GoldenError("--verify-inputs requires --cache-dir")
        cache_dir = args.cache_dir.resolve()
        for item in manifest["input_files"]:
            path = cache_dir / item["filename"]
            if not path.is_file() or _sha256_file(path) != item["sha256"]:
                raise GoldenError(f"input cache digest mismatch: {item['filename']}")

    _verify_production_import_boundary(repo_root)
    print(
        json.dumps(
            {
                "status": "verified",
                "artifact_set_digest": manifest["artifact_set_digest"],
                "member_rows": len(members),
                "snapshots": len(snapshots),
                "ready_min": min(ready_counts),
                "ready_max": max(ready_counts),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build and then verify the frozen Golden")
    build.add_argument("--cache-dir", type=Path, required=True)
    build.add_argument("--events", type=Path, required=True)
    build.add_argument("--report", type=Path)
    build.add_argument("--results-archive", type=Path)
    build.add_argument("--output-dir", type=Path, required=True)
    build.set_defaults(handler=build_artifact)
    verify = subparsers.add_parser("verify", help="verify tracked Golden artifacts")
    verify.add_argument("--artifact-dir", type=Path, required=True)
    verify.add_argument("--cache-dir", type=Path)
    verify.add_argument("--verify-inputs", action="store_true")
    verify.set_defaults(handler=verify_artifact)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        args.handler(args)
    except (GoldenError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"golden_verification_failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
