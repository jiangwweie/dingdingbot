#!/usr/bin/env python3
"""Install one Strategy Universe from strict command-line identities."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.install_strategy_universe import (  # noqa: E402
    UniverseConfigurationRequest,
    UniverseInstallResult,
    configure_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (  # noqa: E402
    UniverseInstallConflict,
)

_USDT_PERPETUAL_SYMBOL = re.compile(r"^[A-Z0-9]+USDT$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--event-spec-id", required=True)
    parser.add_argument("--instrument", action="append", required=True)
    parser.add_argument("--installed-at-ms", type=int)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    instruments = tuple(args.instrument)
    if not 1 <= len(instruments) <= 10:
        parser.error("configure requires between one and ten instruments")
    if len(set(instruments)) != len(instruments):
        parser.error("instruments must be unique")
    if any(
        _USDT_PERPETUAL_SYMBOL.fullmatch(instrument) is None or instrument == "USDT"
        for instrument in instruments
    ):
        parser.error("instrument must be an uppercase USDT perpetual symbol")
    if not str(args.database_url or "").startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    installed_at_ms = (
        int(time.time() * 1_000)
        if args.installed_at_ms is None
        else args.installed_at_ms
    )
    if installed_at_ms <= 0:
        parser.error("installed-at-ms must be positive")
    try:
        request = UniverseConfigurationRequest(
            runtime_profile_id=args.runtime_profile_id,
            event_id=args.event_spec_id,
            exchange_instrument_ids=tuple(
                f"binance-usdm:{instrument}:perpetual" for instrument in instruments
            ),
            installed_at_ms=installed_at_ms,
        )
    except ValidationError:
        parser.error("configuration identities must be exact")
    try:
        result = asyncio.run(_configure(args.database_url, request))
    except UniverseInstallConflict as exc:
        print(f"error={exc.reason_code}", file=sys.stderr)
        return 2
    except Exception:
        print("error=operation_failed", file=sys.stderr)
        return 1
    if result.universe is None or result.lifecycle_state is None:
        print(f"error={result.status.value}", file=sys.stderr)
        return 2
    _print_result(result)
    return 0


async def _configure(
    database_url: str,
    request: UniverseConfigurationRequest,
) -> UniverseInstallResult:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            return await configure_strategy_universe(uow, request)
    finally:
        await engine.dispose()


def _print_result(result: UniverseInstallResult) -> None:
    universe = result.universe
    if universe is None or result.lifecycle_state is None:
        raise ValueError("configuration result lacks a Universe identity")
    print(f"status={result.status.value}")
    print(f"event_spec_id={universe.event_spec_id}")
    print(f"universe_version_id={universe.universe_version_id}")
    print(f"semantic_digest={universe.semantic_digest}")
    print(f"lifecycle_state={result.lifecycle_state}")
    print(f"member_count={len(universe.exchange_instrument_ids)}")


if __name__ == "__main__":
    raise SystemExit(main())
