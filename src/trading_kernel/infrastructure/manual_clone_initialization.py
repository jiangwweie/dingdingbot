"""Empty independent manual-product installation, never a live-policy repair."""

import sqlalchemy as sa

from src.trading_kernel.infrastructure.manual_runtime_initialization import (
    initialize_manual_runtime,
)
from src.trading_kernel.infrastructure.pg_models import (
    runtime_capabilities_current,
    schema_metadata,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    _set_exchange_command_capability,
)


async def initialize_tokyo_manual(
    uow: PostgresKernelUnitOfWork, request: RuntimeAuthoritySeedRequest
) -> None:
    c = uow._require_connection()
    if await c.scalar(sa.select(sa.exists().select_from(schema_metadata))):
        raise ValueError("Tokyo initialization requires empty authority")
    if request.account_id != "owner-subaccount-runtime-v0":
        raise ValueError("Tokyo initialization account differs")
    await initialize_manual_runtime(uow, request)
    # Deployment capability is distinct from Owner new-entry authority. The new
    # paused Policy, real Resume/TOTP, configuration and action-time gates remain.
    await _set_exchange_command_capability(
        c, stage="entry_paused", updated_at_ms=request.seeded_at_ms
    )
    row = (
        (
            await c.execute(
                sa.select(runtime_capabilities_current).where(
                    runtime_capabilities_current.c.capability_key == "exchange_commands"
                )
            )
        )
        .mappings()
        .one()
    )
    certification = {
        **row["certification"],
        "owner_cooperation": "owner-cooperation-v1",
        "deployment_commit": request.runtime_commit,
    }
    await c.execute(
        sa.update(runtime_capabilities_current)
        .where(runtime_capabilities_current.c.capability_key == "exchange_commands")
        .values(certification=certification)
    )
