"""Exact-key readonly views for Owner and operations surfaces."""

from src.trading_kernel.application.ports import KernelUnitOfWork, MonitorStateRecord
from src.trading_kernel.application.project_owner_state import (
    OwnerProjectionRequest,
    project_owner_state,
)


async def get_monitor_state(
    uow: KernelUnitOfWork,
    monitor_key: str,
) -> MonitorStateRecord | None:
    normalized = str(monitor_key or "").strip()
    if not normalized:
        raise ValueError("monitor_key must be non-blank")
    return await uow.monitors.get(normalized)


async def get_owner_projection(
    uow: KernelUnitOfWork,
    request: OwnerProjectionRequest,
) -> MonitorStateRecord:
    return await project_owner_state(uow, request)
