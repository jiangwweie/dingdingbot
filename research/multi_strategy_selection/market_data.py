"""Official Binance Data Vision acquisition and normalized Kline cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)

BASE_URL = "https://data.binance.vision/data/futures/um"
MONTHS = ("2026-06", "2026-07", "2026-08")
DAYS = ("2026-09-01",)
INTERVALS = ("1h", "4h", "15m")
INTERVAL_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)


def symbol_from_instrument(instrument_id: str) -> str:
    return instrument_id.split(":", 2)[1]


@dataclass(frozen=True, slots=True)
class ArchiveSpec:
    symbol: str
    interval: str
    period_kind: str
    period: str
    url: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class ArchiveEvidence:
    symbol: str
    interval: str
    period_kind: str
    period: str
    source_endpoint: str
    relative_path: str
    retrieved_at_ms: int
    sha256: str
    row_count: int
    first_open_time_ms: int
    last_close_time_ms: int


def archive_plan() -> tuple[ArchiveSpec, ...]:
    specs: list[ArchiveSpec] = []
    symbols = tuple(symbol_from_instrument(item) for item in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    for symbol in symbols:
        for interval in INTERVALS:
            for period in MONTHS:
                name = f"{symbol}-{interval}-{period}.zip"
                relative = f"monthly/{symbol}/{interval}/{name}"
                specs.append(ArchiveSpec(symbol, interval, "monthly", period, f"{BASE_URL}/monthly/klines/{symbol}/{interval}/{name}", relative))
            for period in DAYS:
                name = f"{symbol}-{interval}-{period}.zip"
                relative = f"daily/{symbol}/{interval}/{name}"
                specs.append(ArchiveSpec(symbol, interval, "daily", period, f"{BASE_URL}/daily/klines/{symbol}/{interval}/{name}", relative))
    return tuple(specs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"archive must contain one CSV: {path}")
        with archive.open(members[0]) as stream:
            frame = pd.read_csv(stream)
    if tuple(frame.columns) != COLUMNS:
        frame = pd.read_csv(path, names=COLUMNS, compression="zip", header=None)
        if not pd.api.types.is_numeric_dtype(frame["open_time"]):
            frame = frame.iloc[1:].copy()
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="raise").astype("int64")
    frame["close_time"] = pd.to_numeric(frame["close_time"], errors="raise").astype("int64")
    return frame


def _download_one(cache_dir: Path, spec: ArchiveSpec) -> ArchiveEvidence:
    target = cache_dir / "raw" / spec.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    retrieved_at_ms = int(time.time() * 1000)
    if not target.is_file():
        temp = target.with_suffix(".part")
        request = urllib.request.Request(
            spec.url,
            headers={"User-Agent": "BRC-Stage2-Research/2"},
        )
        error: Exception | None = None
        for attempt in range(5):
            temp.unlink(missing_ok=True)
            try:
                with (
                    urllib.request.urlopen(request, timeout=60) as response,
                    temp.open("wb") as output,
                ):
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                with zipfile.ZipFile(temp) as archive:
                    if archive.testzip() is not None:
                        raise ValueError("downloaded archive checksum failed")
                temp.replace(target)
                error = None
                break
            except (OSError, ValueError, urllib.error.URLError) as exc:
                error = exc
                time.sleep(2**attempt)
        if error is not None:
            raise error
    frame = _read_zip(target)
    return ArchiveEvidence(
        symbol=spec.symbol,
        interval=spec.interval,
        period_kind=spec.period_kind,
        period=spec.period,
        source_endpoint=spec.url,
        relative_path=spec.relative_path,
        retrieved_at_ms=retrieved_at_ms,
        sha256=_sha256(target),
        row_count=len(frame),
        first_open_time_ms=int(frame["open_time"].min()),
        last_close_time_ms=int(frame["close_time"].max()),
    )


def download_all(cache_dir: Path, *, workers: int = 8) -> tuple[ArchiveEvidence, ...]:
    plan = archive_plan()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        evidence = tuple(pool.map(lambda spec: _download_one(cache_dir, spec), plan))
    manifest = {
        "schema": "brc.research.binance_klines.v1",
        "source": "Binance Data Vision USD-M perpetual klines",
        "archives": [asdict(item) for item in sorted(evidence, key=lambda item: item.relative_path)],
    }
    manifest_path = cache_dir / "market_data_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    normalize(cache_dir)
    return evidence


def normalize(cache_dir: Path) -> None:
    output = cache_dir / "normalized"
    output.mkdir(parents=True, exist_ok=True)
    for symbol in tuple(symbol_from_instrument(item) for item in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS):
        for interval in INTERVALS:
            paths = sorted((cache_dir / "raw").glob(f"*/{symbol}/{interval}/*.zip"))
            frames = [_read_zip(path) for path in paths]
            frame = pd.concat(frames, ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
            frame["close_time"] = frame["open_time"] + INTERVAL_MS[interval]
            for column in ("open", "high", "low", "close", "volume", "quote_volume"):
                frame[column] = frame[column].astype(str)
            frame.to_parquet(output / f"{symbol}_{interval}.parquet", index=False)


def download_daily_1m(
    cache_dir: Path,
    symbol_days: set[tuple[str, str]],
    *,
    workers: int = 4,
) -> tuple[ArchiveEvidence, ...]:
    specs = tuple(
        ArchiveSpec(
            symbol=symbol,
            interval="1m",
            period_kind="daily",
            period=day,
            url=f"{BASE_URL}/daily/klines/{symbol}/1m/{symbol}-1m-{day}.zip",
            relative_path=f"daily/{symbol}/1m/{symbol}-1m-{day}.zip",
        )
        for symbol, day in sorted(symbol_days)
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return tuple(pool.map(lambda spec: _download_one(cache_dir, spec), specs))


def load_daily_1m(cache_dir: Path, symbol: str, day: str) -> pd.DataFrame:
    path = cache_dir / "raw" / "daily" / symbol / "1m" / f"{symbol}-1m-{day}.zip"
    frame = _read_zip(path).sort_values("open_time").reset_index(drop=True)
    frame["close_time"] = frame["open_time"] + INTERVAL_MS["1m"]
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    evidence = download_all(args.cache_dir.resolve(), workers=args.workers)
    print(json.dumps({"status": "complete", "archive_count": len(evidence)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
