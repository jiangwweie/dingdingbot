"""Authorize one runtime writer and persist a global new-ENTRY fence on drift."""

from __future__ import annotations

from src.trading_kernel.application.ports import (
    RuntimeIncidentRecord,
    UnitOfWorkFactory,
)
from src.trading_kernel.domain.incident_blocking import EntryBlockScope


_RUNTIME_FENCE_INCIDENT_ID = "incident:runtime-fence"
_RUNTIME_FENCE_INCIDENT_KIND = "runtime_identity_mismatch"


async def runtime_writer_is_certified(
    uow_factory: UnitOfWorkFactory,
    *,
    worker_id: str,
    runtime_commit: str,
    schema_revision: str,
    observed_at_ms: int,
) -> bool:
    """Permit only the exact certified writer to mutate durable safety state."""

    async with uow_factory() as uow:
        capability = await uow.signals.get_runtime_capability("exchange_commands")
        certified = bool(
            capability
            and capability.enabled
            and capability.certified_commit == runtime_commit
            and capability.schema_revision == schema_revision
        )
        if certified:
            return True
        await uow.incidents.add(
            RuntimeIncidentRecord(
                incident_id=_RUNTIME_FENCE_INCIDENT_ID,
                ticket_id=None,
                incident_kind=_RUNTIME_FENCE_INCIDENT_KIND,
                status="open",
                first_blocker=_RUNTIME_FENCE_INCIDENT_KIND,
                entry_block_scope=EntryBlockScope.RUNTIME,
                entry_block_key="global",
                details={
                    "worker_id": worker_id,
                    "runtime_commit": runtime_commit,
                    "schema_revision": schema_revision,
                },
                opened_at_ms=observed_at_ms,
            )
        )
    return False
