"""Idempotent PostgreSQL seed for the six registered strategy Events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.exit_policy import registered_exit_policies
from src.trading_kernel.domain.exit_policy import ExitPolicy
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
    instruments,
    strategy_candidate_scopes,
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
            "inserted_instrument_count": 0,
            "inserted_candidate_scope_count": 0,
        }

        contracts_by_group: dict[str, list[RegisteredStrategyContract]] = {}
        for contract in contracts:
            contracts_by_group.setdefault(contract.strategy_group_id, []).append(
                contract
            )

        for strategy_group_id, group_contracts in sorted(contracts_by_group.items()):
            active_version_id = group_contracts[0].strategy_version_id
            counters["inserted_strategy_group_count"] += await self._insert_exact(
                strategy_groups,
                "strategy_group_id",
                {
                    "strategy_group_id": strategy_group_id,
                    "display_name": _display_name(strategy_group_id),
                    "active_version_id": active_version_id,
                    "status": "active",
                    "updated_at_ms": seeded_at_ms,
                },
                compare_keys=("display_name", "active_version_id", "status"),
            )
            counters["inserted_strategy_version_count"] += await self._insert_exact(
                strategy_versions,
                "strategy_version_id",
                {
                    "strategy_version_id": active_version_id,
                    "strategy_group_id": strategy_group_id,
                    "version": 2,
                    "semantics": {
                        "event_spec_ids": sorted(
                            item.event_spec_id for item in group_contracts
                        ),
                        "registry_semantic_hash": registry_semantic_hash,
                        "source": "committed_old_main_program_v2",
                    },
                    "status": "active",
                    "created_at_ms": seeded_at_ms,
                },
                compare_keys=(
                    "strategy_group_id",
                    "version",
                    "semantics",
                    "status",
                ),
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

        instruments_by_id = {
            item.exchange_instrument_id: item
            for contract in contracts
            for item in contract.candidate_instruments
        }
        for exchange_instrument_id, instrument in sorted(instruments_by_id.items()):
            counters["inserted_instrument_count"] += await self._insert_exact(
                instruments,
                "exchange_instrument_id",
                {
                    "exchange_instrument_id": exchange_instrument_id,
                    "venue_id": "binance-usdm",
                    "asset_class": "crypto",
                    "venue_symbol": instrument.venue_symbol,
                    "contract_kind": "perpetual",
                    "status": "active",
                },
                compare_keys=(
                    "venue_id",
                    "asset_class",
                    "venue_symbol",
                    "contract_kind",
                    "status",
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
                        "source": "committed_old_main_program_v2",
                    },
                    "status": "active",
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
                    "status": "active",
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

            for instrument in contract.candidate_instruments:
                candidate_scope_id = (
                    f"candidate:{contract.event_spec_id}:"
                    f"{instrument.exchange_instrument_id}"
                )
                counters["inserted_candidate_scope_count"] += await self._insert_exact(
                    strategy_candidate_scopes,
                    "candidate_scope_id",
                    {
                        "candidate_scope_id": candidate_scope_id,
                        "strategy_group_id": contract.strategy_group_id,
                        "event_spec_id": contract.event_spec_id,
                        "exchange_instrument_id": instrument.exchange_instrument_id,
                        "position_side": contract.position_side,
                        "priority_rank": instrument.priority_rank,
                        "status": "active",
                        "created_at_ms": seeded_at_ms,
                    },
                    compare_keys=(
                        "strategy_group_id",
                        "event_spec_id",
                        "exchange_instrument_id",
                        "position_side",
                        "priority_rank",
                        "status",
                    ),
                )

        return RegistrySeedResult(
            registry_semantic_hash=registry_semantic_hash,
            **counters,
        )

    async def list_current_event_ids(self) -> tuple[str, ...]:
        result = await self._connection.execute(
            sa.select(event_specs.c.event_id)
            .where(event_specs.c.status == "active")
            .order_by(event_specs.c.event_id)
        )
        return tuple(str(value) for value in result.scalars())

    async def get_exit_policy(self, event_spec_id: str) -> ExitPolicy | None:
        normalized = str(event_spec_id or "").strip()
        if not normalized:
            raise ValueError("exit-policy lookup requires Event Spec identity")
        result = await self._connection.execute(
            sa.select(exit_policies).where(
                exit_policies.c.event_spec_id == normalized,
                exit_policies.c.status == "active",
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        policy = ExitPolicy.model_validate(row["policy"])
        if (
            policy.exit_policy_id != str(row["exit_policy_id"])
            or policy.exit_policy_version != str(row["exit_policy_version"])
            or policy.event_spec_id != normalized
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
