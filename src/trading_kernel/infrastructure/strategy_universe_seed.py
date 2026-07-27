"""Deterministic seed for membership authority, separate from Event semantics."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.strategy_universe import (
    UniverseLifecycle,
    registered_strategy_universes,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (
    UniverseSeedConflict,
)


class StrategyUniverseSeedResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    inserted_universe_version_count: int = 0
    inserted_member_count: int = 0
    inserted_instrument_count: int = 0
    inserted_candidate_scope_count: int = 0
    inserted_current_pointer_count: int = 0
    inserted_activation_count: int = 0

    @property
    def total_inserted_count(self) -> int:
        return sum(self.model_dump(mode="python").values())


async def seed_strategy_universes(
    uow: KernelUnitOfWork,
    *,
    seeded_at_ms: int,
) -> StrategyUniverseSeedResult:
    if seeded_at_ms <= 0:
        raise ValueError("strategy universe seed time must be positive")
    contracts = {
        contract.event_spec_id: contract
        for contract in registered_strategy_contracts()
    }
    counters = {
        field: 0
        for field in StrategyUniverseSeedResult.model_fields
    }
    for universe in registered_strategy_universes():
        contract = contracts.get(universe.event_spec_id)
        if contract is None:
            raise UniverseSeedConflict(
                f"universe has no registered Event: {universe.event_spec_id}"
            )
        initial_lifecycle = (
            UniverseLifecycle.ACTIVE
            if universe.asset_class == "crypto"
            else UniverseLifecycle.WARMING
        )
        result = await uow.strategy_universes.install_exact(
            universe,
            position_side=contract.position_side,
            initial_lifecycle=initial_lifecycle,
            installed_at_ms=seeded_at_ms,
        )
        for field in counters:
            counters[field] += int(getattr(result, field))
    return StrategyUniverseSeedResult(**counters)


__all__ = [
    "StrategyUniverseSeedResult",
    "UniverseSeedConflict",
    "seed_strategy_universes",
]
