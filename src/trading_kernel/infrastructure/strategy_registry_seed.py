"""Idempotent PostgreSQL seed for the six registered strategy Events."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.exit_policy import ExitPolicy, registered_exit_policies
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    RegistrySeedConflict,
    RegistrySeedResult,
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_required_facts,
    event_specs,
    exit_policies,
    fact_definitions,
    strategy_groups,
    strategy_versions,
)

__all__ = [
    "PostgresStrategyRegistryRepository",
    "RegistrySeedConflict",
    "RegistrySeedResult",
    "seed_strategy_registry",
]


async def seed_strategy_registry(
    uow: KernelUnitOfWork,
    *,
    seeded_at_ms: int,
) -> RegistrySeedResult:
    if seeded_at_ms <= 0:
        raise ValueError("strategy Registry seed time must be positive")
    contracts = registered_strategy_contracts()
    return await uow.strategy_registry.seed_exact(
        contracts,
        registry_semantic_hash=build_registry_semantic_hash(contracts),
        seeded_at_ms=seeded_at_ms,
    )


class PostgresStrategyRegistryRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def seed_exact(
        self,
        contracts: tuple[RegisteredStrategyContract, ...],
        *,
        registry_semantic_hash: str,
        seeded_at_ms: int,
    ) -> RegistrySeedResult:
        counters = {
            "inserted_strategy_group_count": 0,
            "inserted_strategy_version_count": 0,
            "inserted_event_count": 0,
            "inserted_exit_policy_count": 0,
            "inserted_fact_definition_count": 0,
            "inserted_event_fact_count": 0,
        }

        contracts_by_group: dict[str, list[RegisteredStrategyContract]] = {}
        for contract in contracts:
            contracts_by_group.setdefault(contract.strategy_group_id, []).append(
                contract
            )

        for strategy_group_id, group_contracts in sorted(contracts_by_group.items()):
            group_contracts = sorted(
                group_contracts,
                key=lambda item: item.event_spec_id,
            )
            version_ids = {
                contract.strategy_version_id for contract in group_contracts
            }
            semantic_versions = {
                contract.semantic_version for contract in group_contracts
            }
            if len(version_ids) != 1 or len(semantic_versions) != 1:
                raise RegistrySeedConflict(
                    f"strategy Registry group version conflicts: {strategy_group_id}"
                )
            active_version_id = group_contracts[0].strategy_version_id
            semantic_version = group_contracts[0].semantic_version
            group_statuses = {contract.status for contract in group_contracts}
            if len(group_statuses) != 1:
                raise RegistrySeedConflict(
                    f"strategy Registry group status conflicts: {strategy_group_id}"
                )
            status = group_contracts[0].status
            counters["inserted_strategy_group_count"] += (
                await self._activate_strategy_group_version(
                    strategy_group_id=strategy_group_id,
                    active_version_id=active_version_id,
                    status=status,
                    seeded_at_ms=seeded_at_ms,
                )
            )
            counters["inserted_strategy_version_count"] += (
                await self._insert_strategy_version(
                    strategy_version_id=active_version_id,
                    strategy_group_id=strategy_group_id,
                    semantic_version=semantic_version,
                    event_spec_ids=tuple(
                        item.event_spec_id for item in group_contracts
                    ),
                    registry_semantic_hash=registry_semantic_hash,
                    status=status,
                    seeded_at_ms=seeded_at_ms,
                )
            )

        facts_by_id = {
            fact.fact_definition_id: fact
            for contract in contracts
            for fact in (*contract.required_facts, *contract.disable_facts)
        }
        for fact_definition_id, fact in sorted(facts_by_id.items()):
            counters["inserted_fact_definition_count"] += await self._insert_exact(
                fact_definitions,
                "fact_definition_id",
                {
                    "fact_definition_id": fact_definition_id,
                    "fact_name": fact.fact_name,
                    "value_type": fact.value_type,
                    "freshness_ms": fact.freshness_ms,
                    "validation": {
                        "satisfaction": (
                            "positive_decimal"
                            if fact.value_type == "decimal"
                            else "boolean"
                        )
                    },
                },
                compare_keys=(
                    "fact_name",
                    "value_type",
                    "freshness_ms",
                    "validation",
                ),
            )

        for contract in contracts:
            contract_hash = build_registry_semantic_hash((contract,))
            counters["inserted_event_count"] += await self._insert_exact(
                event_specs,
                "event_spec_id",
                {
                    "event_spec_id": contract.event_spec_id,
                    "strategy_version_id": contract.strategy_version_id,
                    "event_id": contract.event_id,
                    "position_side": contract.position_side,
                    "timeframe": contract.timeframe,
                    "freshness_window_ms": contract.freshness_window_ms,
                    "event_time_authority": contract.event_time_authority,
                    "entry_order_type": contract.entry_order_type.value,
                    "protection_reference_fact_definition_id": (
                        _fact_definition_id(
                            contract,
                            contract.protection_reference_fact,
                        )
                    ),
                    "exit_policy_id": contract.exit_policy_id,
                    "execution_semantics": {
                        "event_semantic_hash": contract_hash,
                        "signal_grade": "trial_grade_signal",
                        "source": _contract_source(contract.semantic_version),
                    },
                    "status": contract.status,
                    "created_at_ms": seeded_at_ms,
                },
                compare_keys=(
                    "strategy_version_id",
                    "event_id",
                    "position_side",
                    "timeframe",
                    "freshness_window_ms",
                    "event_time_authority",
                    "entry_order_type",
                    "protection_reference_fact_definition_id",
                    "exit_policy_id",
                    "execution_semantics",
                    "status",
                ),
            )

            exit_policy = next(
                policy
                for policy in registered_exit_policies()
                if policy.event_spec_id == contract.event_spec_id
            )
            counters["inserted_exit_policy_count"] += await self._insert_exact(
                exit_policies,
                "exit_policy_id",
                {
                    "exit_policy_id": exit_policy.exit_policy_id,
                    "exit_policy_version": exit_policy.exit_policy_version,
                    "event_spec_id": exit_policy.event_spec_id,
                    "position_side": exit_policy.position_side,
                    "policy": exit_policy.model_dump(mode="json"),
                    "semantic_hash": exit_policy.semantic_hash(),
                    "status": contract.status,
                    "created_at_ms": seeded_at_ms,
                },
                compare_keys=(
                    "exit_policy_version",
                    "event_spec_id",
                    "position_side",
                    "policy",
                    "semantic_hash",
                    "status",
                ),
            )

            for fact in (*contract.required_facts, *contract.disable_facts):
                counters["inserted_event_fact_count"] += await self._insert_exact(
                    event_required_facts,
                    ("event_spec_id", "fact_definition_id"),
                    {
                        "event_spec_id": contract.event_spec_id,
                        "fact_definition_id": fact.fact_definition_id,
                        "role": fact.role,
                        "required": True,
                    },
                    compare_keys=("role", "required"),
                )

        return RegistrySeedResult(
            registry_semantic_hash=registry_semantic_hash,
            **counters,
        )

    async def _activate_strategy_group_version(
        self,
        *,
        strategy_group_id: str,
        active_version_id: str,
        status: str,
        seeded_at_ms: int,
    ) -> int:
        expected = {
            "strategy_group_id": strategy_group_id,
            "display_name": _display_name(strategy_group_id),
            "active_version_id": active_version_id,
            "status": status,
            "updated_at_ms": seeded_at_ms,
        }
        result = await self._connection.execute(
            sa.select(strategy_groups)
            .where(strategy_groups.c.strategy_group_id == strategy_group_id)
            .with_for_update(of=strategy_groups)
        )
        existing = result.mappings().one_or_none()
        active_version_ids = tuple(
            str(value)
            for value in (
                await self._connection.execute(
                    sa.select(strategy_versions.c.strategy_version_id)
                    .where(
                        strategy_versions.c.strategy_group_id
                        == strategy_group_id,
                        strategy_versions.c.status == "active",
                    )
                    .order_by(
                        strategy_versions.c.version,
                        strategy_versions.c.strategy_version_id,
                    )
                    .with_for_update(of=strategy_versions)
                )
            ).scalars()
        )
        if existing is None:
            if active_version_ids:
                raise RegistrySeedConflict(
                    "strategy Registry active version conflicts: "
                    f"{strategy_group_id}"
                )
            await self._connection.execute(sa.insert(strategy_groups).values(expected))
            return 1
        if not _matches(existing, expected, ("display_name", "status")):
            raise RegistrySeedConflict(
                f"strategy Registry conflict for {strategy_group_id}"
            )

        current_version_id = str(existing["active_version_id"] or "")
        expected_active_versions = (
            () if not current_version_id else (current_version_id,)
        )
        if active_version_ids != expected_active_versions:
            raise RegistrySeedConflict(
                f"strategy Registry active version conflicts: {strategy_group_id}"
            )
        if current_version_id == active_version_id:
            return 0
        if status != "active":
            raise RegistrySeedConflict(
                f"strategy Registry cannot activate disabled group: {strategy_group_id}"
            )
        target_version = _version_from_identity(
            strategy_group_id,
            active_version_id,
        )
        if current_version_id:
            current_version = _version_from_identity(
                strategy_group_id,
                current_version_id,
            )
            if target_version <= current_version:
                raise RegistrySeedConflict(
                    f"strategy Registry version is not monotonic: {strategy_group_id}"
                )
            await self._retire_strategy_version(
                strategy_group_id=strategy_group_id,
                strategy_version_id=current_version_id,
                semantic_version=current_version,
            )

        await self._connection.execute(
            sa.update(strategy_groups)
            .where(strategy_groups.c.strategy_group_id == strategy_group_id)
            .values(
                active_version_id=active_version_id,
                status=status,
                updated_at_ms=seeded_at_ms,
            )
        )
        return 0

    async def _retire_strategy_version(
        self,
        *,
        strategy_group_id: str,
        strategy_version_id: str,
        semantic_version: int,
    ) -> None:
        result = await self._connection.execute(
            sa.select(strategy_versions)
            .where(
                strategy_versions.c.strategy_version_id == strategy_version_id
            )
            .with_for_update(of=strategy_versions)
        )
        existing = result.mappings().one_or_none()
        if (
            existing is None
            or str(existing["strategy_group_id"]) != strategy_group_id
            or int(existing["version"]) != semantic_version
            or str(existing["status"]) != "active"
        ):
            raise RegistrySeedConflict(
                f"strategy Registry active version conflicts: {strategy_version_id}"
            )
        historical_events = (
            await self._connection.execute(
                sa.select(
                    event_specs.c.event_spec_id,
                    event_specs.c.exit_policy_id,
                    event_specs.c.status,
                )
                .where(
                    event_specs.c.strategy_version_id == strategy_version_id
                )
                .order_by(event_specs.c.event_spec_id)
                .with_for_update(of=event_specs)
            )
        ).mappings().all()
        if not historical_events or any(
            row["status"] != "active" for row in historical_events
        ):
            raise RegistrySeedConflict(
                f"strategy Registry historical Event conflicts: {strategy_version_id}"
            )
        historical_event_ids = tuple(
            str(row["event_spec_id"]) for row in historical_events
        )
        historical_policies = (
            await self._connection.execute(
                sa.select(
                    exit_policies.c.exit_policy_id,
                    exit_policies.c.event_spec_id,
                    exit_policies.c.status,
                )
                .where(
                    exit_policies.c.event_spec_id.in_(historical_event_ids)
                )
                .order_by(exit_policies.c.event_spec_id)
                .with_for_update(of=exit_policies)
            )
        ).mappings().all()
        policies_by_event = {
            str(row["event_spec_id"]): row for row in historical_policies
        }
        if len(policies_by_event) != len(historical_events) or any(
            event_id not in policies_by_event
            or policies_by_event[event_id]["status"] != "active"
            or str(policies_by_event[event_id]["exit_policy_id"])
            != str(event["exit_policy_id"])
            for event_id, event in zip(
                historical_event_ids,
                historical_events,
                strict=True,
            )
        ):
            raise RegistrySeedConflict(
                f"strategy Registry historical policy conflicts: {strategy_version_id}"
            )
        await self._connection.execute(
            sa.update(exit_policies)
            .where(exit_policies.c.event_spec_id.in_(historical_event_ids))
            .values(status="retired")
        )
        await self._connection.execute(
            sa.update(event_specs)
            .where(event_specs.c.strategy_version_id == strategy_version_id)
            .values(status="retired")
        )
        await self._connection.execute(
            sa.update(strategy_versions)
            .where(
                strategy_versions.c.strategy_version_id == strategy_version_id
            )
            .values(status="retired")
        )

    async def _insert_strategy_version(
        self,
        *,
        strategy_version_id: str,
        strategy_group_id: str,
        semantic_version: int,
        event_spec_ids: tuple[str, ...],
        registry_semantic_hash: str,
        status: str,
        seeded_at_ms: int,
    ) -> int:
        semantics = {
            "event_spec_ids": list(event_spec_ids),
            "registry_semantic_hash": registry_semantic_hash,
            "source": _contract_source(semantic_version),
        }
        expected = {
            "strategy_version_id": strategy_version_id,
            "strategy_group_id": strategy_group_id,
            "version": semantic_version,
            "semantics": semantics,
            "status": status,
            "created_at_ms": seeded_at_ms,
        }
        result = await self._connection.execute(
            sa.select(strategy_versions)
            .where(
                strategy_versions.c.strategy_version_id == strategy_version_id
            )
            .limit(1)
        )
        existing = result.mappings().one_or_none()
        if existing is None:
            await self._connection.execute(sa.insert(strategy_versions).values(expected))
            return 1
        if not _matches(
            existing,
            expected,
            ("strategy_group_id", "version", "status"),
        ):
            raise RegistrySeedConflict(
                f"strategy Registry conflict for {strategy_version_id}"
            )
        if existing["semantics"] == semantics:
            return 0
        if semantic_version == 2 and _matches_legacy_v2_semantics(
            existing["semantics"],
            event_spec_ids,
        ):
            return 0
        raise RegistrySeedConflict(
            f"strategy Registry conflict for {strategy_version_id}"
        )

    async def list_current_event_ids(self) -> tuple[str, ...]:
        result = await self._connection.execute(
            sa.select(event_specs.c.event_id)
            .join(
                strategy_versions,
                strategy_versions.c.strategy_version_id
                == event_specs.c.strategy_version_id,
            )
            .join(
                strategy_groups,
                sa.and_(
                    strategy_groups.c.strategy_group_id
                    == strategy_versions.c.strategy_group_id,
                    strategy_groups.c.active_version_id
                    == strategy_versions.c.strategy_version_id,
                ),
            )
            .where(
                event_specs.c.status == "active",
                strategy_versions.c.status == "active",
                strategy_groups.c.status == "active",
            )
            .order_by(event_specs.c.event_id)
        )
        return tuple(str(value) for value in result.scalars())

    async def get_exit_policy(
        self,
        *,
        exit_policy_id: str,
        semantic_hash: str,
    ) -> ExitPolicy | None:
        normalized_policy_id = str(exit_policy_id or "").strip()
        normalized_hash = str(semantic_hash or "").strip()
        if not normalized_policy_id or not normalized_hash:
            raise ValueError("exit-policy lookup requires frozen identity and hash")
        result = await self._connection.execute(
            sa.select(exit_policies).where(
                exit_policies.c.exit_policy_id == normalized_policy_id,
                exit_policies.c.semantic_hash == normalized_hash,
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        policy = ExitPolicy.model_validate(row["policy"])
        if (
            policy.exit_policy_id != str(row["exit_policy_id"])
            or policy.exit_policy_version != str(row["exit_policy_version"])
            or policy.exit_policy_id != normalized_policy_id
            or policy.semantic_hash() != str(row["semantic_hash"])
        ):
            raise RegistrySeedConflict(
                f"existing Registry row conflicts: {row['exit_policy_id']}"
            )
        return policy

    async def _insert_exact(
        self,
        table: sa.Table,
        identity_columns: str | tuple[str, ...],
        values: Mapping[str, Any],
        *,
        compare_keys: tuple[str, ...],
    ) -> int:
        identity_names = (
            (identity_columns,)
            if isinstance(identity_columns, str)
            else identity_columns
        )
        predicates = [
            table.c[name] == values[name]
            for name in identity_names
        ]
        result = await self._connection.execute(
            sa.select(table).where(*predicates).limit(1)
        )
        existing = result.mappings().one_or_none()
        if existing is None:
            await self._connection.execute(sa.insert(table).values(dict(values)))
            return 1
        if not _matches(existing, values, compare_keys):
            identity = ":".join(str(values[name]) for name in identity_names)
            raise RegistrySeedConflict(
                f"strategy Registry conflict for {identity}"
            )
        return 0


def _matches(
    existing: RowMapping,
    expected: Mapping[str, Any],
    keys: tuple[str, ...],
) -> bool:
    return all(existing[key] == expected[key] for key in keys)


def _fact_definition_id(
    contract: RegisteredStrategyContract,
    fact_name: str,
) -> str:
    for fact in contract.required_facts:
        if fact.fact_name == fact_name:
            return fact.fact_definition_id
    raise ValueError("protection reference fact is absent from the contract")


def _display_name(strategy_group_id: str) -> str:
    return {
        "CPM-RO-001": "CPM reclaim pullback recovery",
        "MPG-001": "MPG momentum persistence",
        "MI-001": "MI relative strength impulse",
        "SOR-001": "SOR opening range breakout and breakdown",
        "BRF2-001": "BRF2 bear rally failure",
    }[strategy_group_id]


def _version_from_identity(strategy_group_id: str, strategy_version_id: str) -> int:
    match = re.fullmatch(
        rf"sgv:{re.escape(strategy_group_id)}:v([1-9][0-9]*)",
        strategy_version_id,
    )
    if match is None:
        raise RegistrySeedConflict(
            f"strategy Registry version identity conflicts: {strategy_version_id}"
        )
    return int(match.group(1))


def _contract_source(semantic_version: int) -> str:
    if semantic_version == 2:
        return "committed_old_main_program_v2"
    return "committed_strategy_registry_contract"


def _matches_legacy_v2_semantics(
    value: object,
    event_spec_ids: tuple[str, ...],
) -> bool:
    if not isinstance(value, Mapping):
        return False
    if set(value) != {
        "event_spec_ids",
        "registry_semantic_hash",
        "source",
    }:
        return False
    registry_hash = str(value.get("registry_semantic_hash") or "")
    return (
        value.get("event_spec_ids") == list(event_spec_ids)
        and value.get("source") == "committed_old_main_program_v2"
        and re.fullmatch(r"sha256:[0-9a-f]{64}", registry_hash) is not None
    )
