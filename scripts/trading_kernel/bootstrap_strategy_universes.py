#!/usr/bin/env python3
"""Install and boundedly await the one approved six-Event StrategyUniverse batch."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.install_strategy_universe import (
    UniverseConfigurationRequest,
    configure_strategy_universe,
)
from src.trading_kernel.application.read_strategy_universe_status import (
    StrategyUniverseStatusRequest,
    read_strategy_universe_status,
)
from src.trading_kernel.application.strategy_universe_batch_manifest import (
    APPROVED_FIRST_BATCH_INSTRUMENT_IDS,
    APPROVED_UNIVERSE_EVENT_ORDER,
)
from src.trading_kernel.domain.strategy_registry import (
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)

EVENT_ORDER = APPROVED_UNIVERSE_EVENT_ORDER
INITIAL_MEMBERS = APPROVED_FIRST_BATCH_INSTRUMENT_IDS


class BootstrapBlocked(RuntimeError):
    """The immutable batch cannot safely continue from current PostgreSQL truth."""


@dataclass(frozen=True)
class BootstrapResult:
    event_id: str
    status: str
    universe_version_id: str


def _validate_static_manifest() -> None:
    contracts = {contract.event_id: contract for contract in registered_strategy_contracts()}
    if tuple(event_id for event_id in EVENT_ORDER if event_id in contracts) != EVENT_ORDER:
        raise BootstrapBlocked("registry_event_manifest_mismatch")
    if len(INITIAL_MEMBERS) != 7 or len(set(INITIAL_MEMBERS)) != 7:
        raise BootstrapBlocked("initial_member_manifest_invalid")
    if any("AVAX" in member or not member.startswith("binance-usdm:") for member in INITIAL_MEMBERS):
        raise BootstrapBlocked("initial_member_manifest_out_of_scope")


async def _validate_database_authority(
    engine: AsyncEngine,
    *,
    runtime_profile_id: str,
) -> None:
    contracts = {contract.event_id: contract for contract in registered_strategy_contracts()}
    expected_event_specs = tuple(contracts[event_id].event_spec_id for event_id in EVENT_ORDER)
    async with engine.connect() as connection:
        event_rows = (
            await connection.execute(
                text(
                    "SELECT event_id, event_spec_id FROM brc_event_specs "
                    "WHERE event_id = ANY(:event_ids) AND status = 'active' "
                    "ORDER BY event_id"
                ),
                {"event_ids": list(EVENT_ORDER)},
            )
        ).mappings().all()
        policy_rows = (
            await connection.execute(
                text(
                    "SELECT scope FROM brc_owner_policy_current "
                    "WHERE enabled = true "
                    "AND scope ->> 'runtime_profile_id' = :runtime_profile_id "
                    "ORDER BY owner_policy_id LIMIT 2"
                ),
                {"runtime_profile_id": runtime_profile_id},
            )
        ).mappings().all()
    actual_event_specs = {
        str(row["event_id"]): str(row["event_spec_id"]) for row in event_rows
    }
    if actual_event_specs != {
        event_id: contracts[event_id].event_spec_id for event_id in EVENT_ORDER
    }:
        raise BootstrapBlocked("registry_event_authority_mismatch")
    if len(policy_rows) != 1:
        raise BootstrapBlocked("owner_policy_authority_mismatch")
    scope = policy_rows[0]["scope"]
    if not isinstance(scope, dict):
        raise BootstrapBlocked("owner_policy_scope_invalid")
    allowed = scope.get("allowed_event_spec_ids")
    if not isinstance(allowed, list) or tuple(sorted(str(value) for value in allowed)) != tuple(
        sorted(expected_event_specs)
    ):
        raise BootstrapBlocked("owner_policy_event_manifest_mismatch")


async def bootstrap_strategy_universes(
    database_url: str,
    *,
    runtime_profile_id: str,
    now_ms: Callable[[], int],
    wait_timeout_ms: int = 300_000,
    poll_interval_ms: int = 5_000,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[BootstrapResult, ...]:
    """Converge PostgreSQL on the exact batch without a file checkpoint or auto-abandon."""

    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    if not runtime_profile_id.strip() or wait_timeout_ms <= 0 or poll_interval_ms <= 0:
        raise ValueError("bootstrap identities and timing must be positive")
    _validate_static_manifest()
    engine = create_async_engine(database_url)
    try:
        await _validate_database_authority(engine, runtime_profile_id=runtime_profile_id)
        results: list[BootstrapResult] = []
        for event_id in EVENT_ORDER:
            installed_at_ms = now_ms()
            async with PostgresKernelUnitOfWork(engine) as uow:
                installed = await configure_strategy_universe(
                    uow,
                    UniverseConfigurationRequest(
                        runtime_profile_id=runtime_profile_id,
                        event_id=event_id,
                        exchange_instrument_ids=INITIAL_MEMBERS,
                        installed_at_ms=installed_at_ms,
                    ),
                )
            if installed.universe is None:
                raise BootstrapBlocked("warming_universe_slot_occupied")
            universe_version_id = installed.universe.universe_version_id
            deadline_ms = installed_at_ms + wait_timeout_ms
            while installed.lifecycle_state != "active":
                if now_ms() >= deadline_ms:
                    raise BootstrapBlocked(f"warming_timeout:{event_id}")
                await sleep(poll_interval_ms / 1_000)
                async with PostgresKernelUnitOfWork(engine) as uow:
                    status = await read_strategy_universe_status(
                        uow,
                        StrategyUniverseStatusRequest(
                            runtime_profile_id=runtime_profile_id,
                            event_id=event_id,
                        ),
                    )
                exact = tuple(
                    universe
                    for universe in status.universes
                    if universe.event_id == event_id
                )
                if len(exact) != 1:
                    raise BootstrapBlocked(f"universe_status_identity_conflict:{event_id}")
                current = exact[0]
                if tuple(member.exchange_instrument_id for member in current.members) != INITIAL_MEMBERS:
                    raise BootstrapBlocked(f"universe_member_manifest_mismatch:{event_id}")
                if current.lifecycle_state == "active":
                    installed = installed.model_copy(update={"lifecycle_state": "active"})
            results.append(
                BootstrapResult(
                    event_id=event_id,
                    status=installed.status.value,
                    universe_version_id=universe_version_id,
                )
            )
        return tuple(results)
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""))
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--wait-timeout-ms", type=int, default=300_000)
    parser.add_argument("--poll-interval-ms", type=int, default=5_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        results = asyncio.run(
            bootstrap_strategy_universes(
                str(args.database_url),
                runtime_profile_id=str(args.runtime_profile_id),
                now_ms=lambda: int(time.time() * 1_000),
                wait_timeout_ms=args.wait_timeout_ms,
                poll_interval_ms=args.poll_interval_ms,
            )
        )
    except BootstrapBlocked as exc:
        print(f"status=blocked reason={exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError, SQLAlchemyError):
        print("status=failed reason=operation_failed", file=sys.stderr)
        return 1
    print("status=complete events=" + ",".join(result.event_id for result in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
