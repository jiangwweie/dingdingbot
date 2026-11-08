"""Fresh manual account authority through the canonical seed and Owner control paths."""

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    set_strategy_entry_state,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    RuntimeAuthoritySeedResult,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


async def initialize_manual_runtime(
    uow: PostgresKernelUnitOfWork, request: RuntimeAuthoritySeedRequest
) -> RuntimeAuthoritySeedResult:
    """Keep global ENTRY/capability disabled and apply the standing retirement decision."""
    if request.schema_revision != CURRENT_SCHEMA_REVISION:
        raise ValueError("fresh manual initialization requires the current schema")
    result = await seed_runtime_authority(uow, request)
    await set_strategy_entry_state(
        uow,
        strategy_group_id="SOR-001",
        target_state=StrategyEntryState.PAUSED,
        request=ControlMutationRequest(
            expected_version=1,
            reason="Owner permanent Crypto SOR retirement; independent manual account initialization",
            idempotency_key="manual-initialization:retired-sor",
            owner_identity="Owner-standing-retirement-decision",
            now_ms=request.seeded_at_ms,
        ),
        authentication_strength="session",
    )
    return result
