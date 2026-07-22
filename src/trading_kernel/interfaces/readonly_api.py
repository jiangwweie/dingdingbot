"""Exact-key readonly views for Owner and operations surfaces."""

from src.trading_kernel.application.ports import KernelUnitOfWork, MonitorStateRecord


async def get_monitor_state(
    uow: KernelUnitOfWork,
    monitor_key: str,
) -> MonitorStateRecord | None:
    normalized = str(monitor_key or "").strip()
    if not normalized:
        raise ValueError("monitor_key must be non-blank")
    return await uow.monitors.get(normalized)
