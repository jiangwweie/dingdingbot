"""One bounded concurrent read group, with sanitized stage timings and cleanup."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    ProductSessionRequest,
)
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.product import ProductSessionSnapshot

T = TypeVar("T")


@dataclass
class EntryReadTelemetry:
    throttle_wait_ms: int = 0
    http_ms: int = 0
    http_reads: int = 0


entry_read_telemetry: ContextVar[EntryReadTelemetry | None] = ContextVar(
    "entry_read_telemetry", default=None,
)


class EntryFactCollection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: EntryAdmissionSnapshot
    rules: InstrumentRulesFacts
    product: ProductSessionSnapshot | None


async def collect_entry_facts(
    source: EntryFactsSource,
    *,
    snapshot_request: EntryAdmissionSnapshotRequest,
    rules_request: InstrumentRulesRequest,
    product_request: ProductSessionRequest | None,
    timeout_seconds: float,
    phase: str,
    identity: str,
) -> EntryFactCollection:
    started = time.monotonic()
    telemetry = EntryReadTelemetry()
    token = entry_read_telemetry.set(telemetry)
    stages: dict[str, dict[str, str | int]] = {}

    async def measured(name: str, operation: Awaitable[T]) -> T:
        start = time.monotonic()
        row: dict[str, str | int] = {"status": "reading"}
        stages[name] = row
        try:
            value = await operation
            row["status"] = "ok"
            return value
        except BaseException as exc:
            row["status"] = type(exc).__name__
            raise
        finally:
            row["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    async def product() -> ProductSessionSnapshot | None:
        if product_request is None:
            return None
        reader = getattr(source, "read_product_session", None)
        if not callable(reader):
            raise TypeError("TradFi action-time Product source is unavailable")
        return await reader(product_request)

    tasks = (
        asyncio.create_task(measured("admission", source.read_entry_admission_snapshot(snapshot_request))),
        asyncio.create_task(measured("rules", source.read_instrument_rules(rules_request))),
        asyncio.create_task(measured("product", product())),
    )
    error: str | None = None
    try:
        snapshot, rules, session = await asyncio.wait_for(
            asyncio.gather(*tasks), timeout=timeout_seconds,
        )
        return EntryFactCollection(snapshot=snapshot, rules=rules, product=session)
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        entry_read_telemetry.reset(token)
        if error is not None:
            logging.getLogger(__name__).warning(json.dumps({
                "status": "entry_facts_failed", "phase": phase,
                "identity": identity, "error_type": error,
                "elapsed_ms": int((time.monotonic()-started)*1000),
                "stages": stages,
                "throttle_wait_ms": telemetry.throttle_wait_ms,
                "http_ms": telemetry.http_ms, "http_reads": telemetry.http_reads,
            }, sort_keys=True))


async def record_entry_fact_health(uow: KernelUnitOfWork, *, venue_id: str, account_id: str,
                                  failed: bool, now_ms: int) -> None:
    from src.trading_kernel.application.ports import (
        MonitorOwnerStatus,
        MonitorStateRecord,
    )

    await uow.monitors.save_if_changed(MonitorStateRecord(
        monitor_key=f"entry-facts:{venue_id}:{account_id}",
        owner_status=(MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE if failed else MonitorOwnerStatus.RUNNING),
        summary=("开仓事实读取失败；本次开仓已阻止" if failed else "开仓事实读取成功"),
        intervention=("系统等待新的合法机会；工程核查读取日志" if failed else "无需操作"),
        updated_at_ms=now_ms,
    ))
