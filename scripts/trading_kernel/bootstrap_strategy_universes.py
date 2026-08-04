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

from src.trading_kernel.application.certification_batch import (
    StartCertificationBatchRequest,
    start_certification_batch,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseConfigurationRequest,
    configure_strategy_universe,
)
from src.trading_kernel.application.read_strategy_universe_status import (
    StrategyUniverseStatusRequest,
    StrategyUniverseStatusResult,
    StrategyUniverseVersionStatus,
    read_strategy_universe_status,
)
from src.trading_kernel.application.strategy_universe_batch_manifest import (
    APPROVED_FIRST_BATCH_INSTRUMENT_IDS,
    APPROVED_UNIVERSE_EVENT_ORDER,
    APPROVED_UNIVERSE_EVENT_SPECS,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.instrument_certification import (
    build_certification_manifest_digest,
)
from src.trading_kernel.domain.strategy_registry import (
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)

EVENT_ORDER = APPROVED_UNIVERSE_EVENT_ORDER
EVENT_SPEC_BY_EVENT_ID = dict(APPROVED_UNIVERSE_EVENT_SPECS)
INITIAL_MEMBERS = APPROVED_FIRST_BATCH_INSTRUMENT_IDS
CERTIFICATION_PROMOTION_WINDOW_MS = 120_000


class BootstrapBlocked(RuntimeError):
    """The immutable batch cannot safely continue from current PostgreSQL truth."""


@dataclass(frozen=True)
class BootstrapResult:
    event_id: str
    event_spec_id: str
    status: str
    universe_version_id: str


@dataclass(frozen=True)
class BootstrapAuthority:
    runtime_commit: str
    schema_revision: str
    seed_identity: str
    owner_policy_id: str
    owner_policy_version: int


def _select_bootstrap_universe(
    status: StrategyUniverseStatusResult,
    *,
    event_id: str,
    universe_version_id: str,
) -> StrategyUniverseVersionStatus:
    exact = tuple(
        universe
        for universe in status.universes
        if universe.event_id == event_id
        and universe.universe_version_id == universe_version_id
    )
    if len(exact) != 1:
        raise BootstrapBlocked(f"universe_status_identity_conflict:{event_id}")
    return exact[0]


def _validate_static_manifest() -> None:
    contracts = {contract.event_id: contract for contract in registered_strategy_contracts()}
    if tuple(EVENT_SPEC_BY_EVENT_ID) != EVENT_ORDER or {
        event_id: contracts[event_id].event_spec_id
        for event_id in EVENT_ORDER
        if event_id in contracts
    } != EVENT_SPEC_BY_EVENT_ID:
        raise BootstrapBlocked("registry_event_manifest_mismatch")
    if len(INITIAL_MEMBERS) != 7 or len(set(INITIAL_MEMBERS)) != 7:
        raise BootstrapBlocked("initial_member_manifest_invalid")
    if any("AVAX" in member or not member.startswith("binance-usdm:") for member in INITIAL_MEMBERS):
        raise BootstrapBlocked("initial_member_manifest_out_of_scope")


async def _validate_database_authority(
    engine: AsyncEngine,
    *,
    runtime_profile_id: str,
) -> BootstrapAuthority:
    expected_event_specs = tuple(
        EVENT_SPEC_BY_EVENT_ID[event_id] for event_id in EVENT_ORDER
    )
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
        identity_rows = (
            await connection.execute(
                text(
                    "SELECT metadata_key, metadata_value "
                    "FROM brc_schema_metadata "
                    "WHERE metadata_key IN "
                    "('runtime_commit','schema_revision','seed_identity')"
                )
            )
        ).all()
        policy_identity = (
            await connection.execute(
                text(
                    "SELECT owner_policy_id, policy_version "
                    "FROM brc_owner_policy_current "
                    "WHERE enabled = true "
                    "AND scope ->> 'runtime_profile_id' = :runtime_profile_id "
                    "ORDER BY owner_policy_id LIMIT 2"
                ),
                {"runtime_profile_id": runtime_profile_id},
            )
        ).all()
    actual_event_specs = {
        str(row["event_id"]): str(row["event_spec_id"]) for row in event_rows
    }
    if actual_event_specs != {
        event_id: EVENT_SPEC_BY_EVENT_ID[event_id] for event_id in EVENT_ORDER
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
    identity = {str(key): str(value) for key, value in identity_rows}
    if set(identity) != {"runtime_commit", "schema_revision", "seed_identity"}:
        raise BootstrapBlocked("runtime_identity_incomplete")
    if len(policy_identity) != 1:
        raise BootstrapBlocked("owner_policy_identity_mismatch")
    return BootstrapAuthority(
        runtime_commit=identity["runtime_commit"],
        schema_revision=identity["schema_revision"],
        seed_identity=identity["seed_identity"],
        owner_policy_id=str(policy_identity[0][0]),
        owner_policy_version=int(policy_identity[0][1]),
    )


async def _ensure_certification_batch(
    engine: AsyncEngine,
    *,
    runtime_profile_id: str,
    authority: BootstrapAuthority,
    started_at_ms: int,
) -> str:
    manifest_digest = build_certification_manifest_digest(INITIAL_MEMBERS)
    required_valid_until_ms = started_at_ms + CERTIFICATION_PROMOTION_WINDOW_MS
    async with engine.connect() as connection:
        existing = (
            await connection.execute(
                text(
                    "SELECT certification_batch_id, started_at_ms, "
                    "minimum_valid_until_ms "
                    "FROM brc_instrument_certification_batches "
                    "WHERE runtime_profile_id = :runtime_profile_id "
                    "AND target_commit = :target_commit "
                    "AND target_schema_revision = :target_schema_revision "
                    "AND target_seed_identity = :target_seed_identity "
                    "AND owner_policy_id = :owner_policy_id "
                    "AND owner_policy_version = :owner_policy_version "
                    "AND manifest_digest = :manifest_digest "
                    "AND (status = 'pending' OR "
                    "(status = 'completed' "
                    "AND valid_until_ms >= :required_valid_until_ms)) "
                    "ORDER BY CASE WHEN status = 'pending' THEN 0 ELSE 1 END, "
                    "started_at_ms DESC LIMIT 1"
                ),
                {
                    "runtime_profile_id": runtime_profile_id,
                    "target_commit": authority.runtime_commit,
                    "target_schema_revision": authority.schema_revision,
                    "target_seed_identity": authority.seed_identity,
                    "owner_policy_id": authority.owner_policy_id,
                    "owner_policy_version": authority.owner_policy_version,
                    "manifest_digest": manifest_digest,
                    "required_valid_until_ms": required_valid_until_ms,
                },
            )
        ).one_or_none()
    if existing is None:
        batch_id = "certification-batch:" + canonical_digest(
            {
                "runtime_profile_id": runtime_profile_id,
                "target_commit": authority.runtime_commit,
                "target_schema_revision": authority.schema_revision,
                "target_seed_identity": authority.seed_identity,
                "owner_policy_id": authority.owner_policy_id,
                "owner_policy_version": authority.owner_policy_version,
                "manifest_digest": manifest_digest,
                "started_at_ms": started_at_ms,
            }
        )[7:39]
        batch_started_at_ms = started_at_ms
        minimum_valid_until_ms = required_valid_until_ms
    else:
        batch_id = str(existing[0])
        batch_started_at_ms = int(existing[1])
        minimum_valid_until_ms = int(existing[2])
    async with PostgresKernelUnitOfWork(engine) as uow:
        await start_certification_batch(
            uow,
            StartCertificationBatchRequest(
                certification_batch_id=batch_id,
                runtime_profile_id=runtime_profile_id,
                target_commit=authority.runtime_commit,
                target_schema_revision=authority.schema_revision,
                target_seed_identity=authority.seed_identity,
                owner_policy_id=authority.owner_policy_id,
                owner_policy_version=authority.owner_policy_version,
                exchange_instrument_ids=INITIAL_MEMBERS,
                started_at_ms=batch_started_at_ms,
                minimum_valid_until_ms=minimum_valid_until_ms,
            ),
        )
    return batch_id


async def _read_certification_batch_state(
    engine: AsyncEngine,
    *,
    certification_batch_id: str,
) -> tuple[str, str | None]:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT status, blocker_code "
                    "FROM brc_instrument_certification_batches "
                    "WHERE certification_batch_id = :certification_batch_id"
                ),
                {"certification_batch_id": certification_batch_id},
            )
        ).one_or_none()
    if row is None:
        raise BootstrapBlocked("certification_batch_missing")
    return str(row[0]), None if row[1] is None else str(row[1])


async def _validate_active_universe_manifest(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT event.event_id, current.event_spec_id, "
                    "current.universe_version_id, "
                    "current.lifecycle_state AS current_lifecycle_state, "
                    "version.lifecycle_state AS version_lifecycle_state, "
                    "array_agg(member.exchange_instrument_id "
                    "ORDER BY member.exchange_instrument_id) AS members "
                    "FROM brc_strategy_universe_current AS current "
                    "JOIN brc_strategy_universe_versions AS version "
                    "ON version.universe_version_id = current.universe_version_id "
                    "AND version.event_spec_id = current.event_spec_id "
                    "AND version.semantic_digest = current.semantic_digest "
                    "JOIN brc_event_specs AS event "
                    "ON event.event_spec_id = current.event_spec_id "
                    "JOIN brc_strategy_universe_members AS member "
                    "ON member.universe_version_id = current.universe_version_id "
                    "GROUP BY event.event_id, current.event_spec_id, "
                    "current.universe_version_id, current.lifecycle_state, "
                    "version.lifecycle_state"
                )
            )
        ).mappings().all()
        active_version_count = int(
            await connection.scalar(
                text(
                    "SELECT count(*) FROM brc_strategy_universe_versions "
                    "WHERE lifecycle_state = 'active'"
                )
            )
            or 0
        )
        warming_version_count = int(
            await connection.scalar(
                text(
                    "SELECT count(*) FROM brc_strategy_universe_versions "
                    "WHERE lifecycle_state = 'warming'"
                )
            )
            or 0
        )

    if warming_version_count != 0:
        raise BootstrapBlocked("warming_universe_present")
    if len(rows) != len(EVENT_ORDER) or active_version_count != len(EVENT_ORDER):
        raise BootstrapBlocked("active_universe_manifest_mismatch")
    row_by_event = {str(row["event_id"]): row for row in rows}
    if set(row_by_event) != set(EVENT_ORDER):
        raise BootstrapBlocked("active_universe_manifest_mismatch")
    for event_id in EVENT_ORDER:
        row = row_by_event[event_id]
        if (
            str(row["event_spec_id"]) != EVENT_SPEC_BY_EVENT_ID[event_id]
            or str(row["current_lifecycle_state"]) != "active"
            or str(row["version_lifecycle_state"]) != "active"
        ):
            raise BootstrapBlocked(
                f"active_universe_identity_mismatch:{event_id}"
            )
        if tuple(str(member) for member in row["members"]) != INITIAL_MEMBERS:
            raise BootstrapBlocked(
                f"active_universe_member_manifest_mismatch:{event_id}"
            )


async def refresh_active_certification_batch(
    database_url: str,
    *,
    runtime_profile_id: str,
    now_ms: Callable[[], int],
) -> str:
    """Create or reuse a Batch from the exact current Active Universe manifest."""

    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    if not runtime_profile_id.strip():
        raise ValueError("runtime profile identity must be non-blank")
    _validate_static_manifest()
    engine = create_async_engine(database_url)
    try:
        authority = await _validate_database_authority(
            engine,
            runtime_profile_id=runtime_profile_id,
        )
        await _validate_active_universe_manifest(engine)
        return await _ensure_certification_batch(
            engine,
            runtime_profile_id=runtime_profile_id,
            authority=authority,
            started_at_ms=now_ms(),
        )
    finally:
        await engine.dispose()


async def prepare_certification_batch(
    database_url: str,
    *,
    runtime_profile_id: str,
    now_ms: Callable[[], int],
) -> str:
    """Create or reuse the exact Batch before readonly workers can certify."""

    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    if not runtime_profile_id.strip():
        raise ValueError("runtime profile identity must be non-blank")
    _validate_static_manifest()
    engine = create_async_engine(database_url)
    try:
        authority = await _validate_database_authority(
            engine,
            runtime_profile_id=runtime_profile_id,
        )
        prepared_at_ms = now_ms()
        async with PostgresKernelUnitOfWork(engine) as uow:
            prepared = await configure_strategy_universe(
                uow,
                UniverseConfigurationRequest(
                    runtime_profile_id=runtime_profile_id,
                    event_id=EVENT_ORDER[0],
                    exchange_instrument_ids=INITIAL_MEMBERS,
                    installed_at_ms=prepared_at_ms,
                ),
            )
        if prepared.universe is None:
            raise BootstrapBlocked("warming_universe_slot_occupied")
        if prepared.universe.event_spec_id != EVENT_SPEC_BY_EVENT_ID[EVENT_ORDER[0]]:
            raise BootstrapBlocked("warming_universe_event_spec_mismatch")
        return await _ensure_certification_batch(
            engine,
            runtime_profile_id=runtime_profile_id,
            authority=authority,
            started_at_ms=prepared_at_ms,
        )
    finally:
        await engine.dispose()


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
        authority = await _validate_database_authority(
            engine,
            runtime_profile_id=runtime_profile_id,
        )
        deadline_ms = now_ms() + wait_timeout_ms
        results: list[BootstrapResult] = []
        certification_batch_id: str | None = None
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
            expected_event_spec_id = EVENT_SPEC_BY_EVENT_ID[event_id]
            if installed.universe.event_spec_id != expected_event_spec_id:
                raise BootstrapBlocked(
                    f"warming_universe_event_spec_mismatch:{event_id}"
                )
            if certification_batch_id is None:
                certification_batch_id = await _ensure_certification_batch(
                    engine,
                    runtime_profile_id=runtime_profile_id,
                    authority=authority,
                    started_at_ms=installed_at_ms,
                )
            universe_version_id = installed.universe.universe_version_id
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
                current = _select_bootstrap_universe(
                    status,
                    event_id=event_id,
                    universe_version_id=universe_version_id,
                )
                if tuple(member.exchange_instrument_id for member in current.members) != INITIAL_MEMBERS:
                    raise BootstrapBlocked(f"universe_member_manifest_mismatch:{event_id}")
                if current.event_spec_id != expected_event_spec_id:
                    raise BootstrapBlocked(
                        f"universe_event_spec_mismatch:{event_id}"
                    )
                if current.lifecycle_state == "active":
                    installed = installed.model_copy(update={"lifecycle_state": "active"})
            results.append(
                BootstrapResult(
                    event_id=event_id,
                    event_spec_id=expected_event_spec_id,
                    status=installed.status.value,
                    universe_version_id=universe_version_id,
                )
            )
        if certification_batch_id is None:
            raise BootstrapBlocked("certification_batch_missing")
        while True:
            batch_status, blocker_code = await _read_certification_batch_state(
                engine,
                certification_batch_id=certification_batch_id,
            )
            if batch_status == "completed":
                break
            if batch_status == "blocked":
                raise BootstrapBlocked(
                    "certification_batch_blocked:"
                    + str(blocker_code or "unknown")
                )
            if now_ms() >= deadline_ms:
                raise BootstrapBlocked("certification_batch_timeout")
            await sleep(poll_interval_ms / 1_000)
        return tuple(results)
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""))
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--wait-timeout-ms", type=int, default=300_000)
    parser.add_argument("--poll-interval-ms", type=int, default=5_000)
    certification_batch_mode = parser.add_mutually_exclusive_group()
    certification_batch_mode.add_argument(
        "--prepare-certification-batch-only",
        action="store_true",
    )
    certification_batch_mode.add_argument(
        "--refresh-active-certification-batch-only",
        action="store_true",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.prepare_certification_batch_only:
            certification_batch_id = asyncio.run(
                prepare_certification_batch(
                    str(args.database_url),
                    runtime_profile_id=str(args.runtime_profile_id),
                    now_ms=lambda: int(time.time() * 1_000),
                )
            )
            print(
                "status=prepared certification_batch_id="
                + certification_batch_id
            )
            return 0
        if args.refresh_active_certification_batch_only:
            certification_batch_id = asyncio.run(
                refresh_active_certification_batch(
                    str(args.database_url),
                    runtime_profile_id=str(args.runtime_profile_id),
                    now_ms=lambda: int(time.time() * 1_000),
                )
            )
            print(
                "status=refreshed certification_batch_id="
                + certification_batch_id
            )
            return 0
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
