"""One bounded notification attempt. Leases commit before external I/O."""

import asyncio
import time
from typing import Protocol
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.ports import MonitorOwnerStatus, MonitorStateRecord
from src.trading_kernel.infrastructure.pg_models import notice_outbox as outbox
from src.trading_kernel.infrastructure.pg_models import trade_aggregates
from src.trading_kernel.infrastructure.pg_repositories import PostgresMonitorRepository


class NoticeChannel(Protocol):
    @property
    def configured(self) -> bool: ...
    async def send(self, message: str) -> None: ...


class DeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: str


async def deliver_one_notice(
    engine: AsyncEngine, channel: NoticeChannel, *, now_ms: int
) -> DeliveryResult:
    started_ns = time.monotonic_ns()
    async with engine.begin() as c:
        await c.execute(sa.text("SET LOCAL statement_timeout='5s'"))
        monitors = PostgresMonitorRepository(c)
        if not channel.configured:
            await monitors.save_if_changed(
                MonitorStateRecord(
                    monitor_key="notification:feishu",
                    owner_status=MonitorOwnerStatus.NOT_ENABLED,
                    summary="独立飞书机器人未配置；消息保留待发",
                    intervention="配置首尔独立机器人",
                    updated_at_ms=now_ms,
                )
            )
            return DeliveryResult(status="channel_missing")
        older = outbox.alias("older")
        row = (
            (
                await c.execute(
                    sa.select(outbox)
                    .where(
                        outbox.c.status.in_(["pending", "retry", "delivering"]),
                        outbox.c.next_attempt_at_ms <= now_ms,
                        sa.or_(
                            outbox.c.lease_until_ms.is_(None),
                            outbox.c.lease_until_ms <= now_ms,
                        ),
                        ~sa.exists(
                            sa.select(1).where(
                                older.c.stream_key == outbox.c.stream_key,
                                older.c.sequence < outbox.c.sequence,
                                older.c.status.in_(["pending", "retry", "delivering"]),
                            )
                        ),
                    )
                    .order_by(outbox.c.sequence)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            retrying = bool(
                await c.scalar(
                    sa.select(
                        sa.exists().where(outbox.c.status.in_(["retry", "delivering"]))
                    )
                )
            )
            dead = bool(
                await c.scalar(sa.select(sa.exists().where(outbox.c.status == "dead")))
            )
            await monitors.save_if_changed(
                MonitorStateRecord(
                    monitor_key="notification:feishu",
                    owner_status=MonitorOwnerStatus.NEEDS_INTERVENTION
                    if dead
                    else MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE
                    if retrying
                    else MonitorOwnerStatus.RUNNING,
                    summary="存在投递失败消息；未获平台接受"
                    if dead
                    else "通知等待有限重试"
                    if retrying
                    else "通知通道已配置；平台接受不代表已读",
                    intervention="检查独立机器人和投递记录" if dead else "none",
                    updated_at_ms=now_ms,
                )
            )
            return DeliveryResult(status="no_work")
        stale = False
        state_advanced = False
        if row["ticket_id"] is not None:
            aggregate = (
                (
                    await c.execute(
                        sa.select(
                            trade_aggregates.c.position_qty,
                            trade_aggregates.c.status,
                            trade_aggregates.c.management_mode,
                            trade_aggregates.c.version,
                        ).where(trade_aggregates.c.ticket_id == row["ticket_id"])
                    )
                )
                .mappings()
                .one_or_none()
            )
            if aggregate is not None:
                state_advanced = aggregate["version"] > row["state_version"]
                stale = (
                    row["kind"]
                    in {
                        "opened",
                        "tp1",
                        "manual_fill",
                        "risk",
                        "recovered",
                        "review",
                        "review_cleared",
                    }
                    and aggregate["position_qty"] == 0
                    and aggregate["status"] != "entry_outcome_unknown"
                    or row["kind"] == "opened"
                    and aggregate["management_mode"] != "AUTO"
                )
                newer = bool(
                    await c.scalar(
                        sa.select(
                            sa.exists().where(
                                outbox.c.stream_key == row["stream_key"],
                                outbox.c.sequence > row["sequence"],
                                outbox.c.kind == row["kind"],
                            )
                        )
                    )
                )
                stale = (
                    stale
                    or row["kind"]
                    in {"risk", "recovered", "review", "review_cleared", "residual"}
                    and newer
                )
        replacement_groups = (
            {"risk", "recovered"},
            {"review", "review_cleared"},
            {"residual", "closed"},
            {"runtime_fault", "runtime_recovered"},
        )
        group = next((g for g in replacement_groups if row["kind"] in g), None)
        if group is not None:
            stale = stale or bool(
                await c.scalar(
                    sa.select(
                        sa.exists().where(
                            outbox.c.stream_key == row["stream_key"],
                            outbox.c.sequence > row["sequence"],
                            outbox.c.kind.in_(group),
                        )
                    )
                )
            )
        if stale or row["attempts"] >= 5:
            status = "superseded" if stale else "dead"
            await c.execute(
                sa.update(outbox)
                .where(outbox.c.sequence == row["sequence"])
                .values(
                    status=status,
                    lease_token=None,
                    lease_until_ms=None,
                    updated_at_ms=now_ms,
                )
            )
            return DeliveryResult(status=status)
        token = uuid4().hex
        attempts = int(row["attempts"]) + 1
        payload = str(row["delivery_payload"] or row["payload"])
        if row["delivery_payload"] is None and state_advanced:
            payload = "【事件快照·后续状态已更新，以控制台为准】\n" + payload
        if (
            row["delivery_payload"] is None
            and now_ms - int(row["created_at_ms"]) > 60000
        ):
            payload = "【延迟通知·以下为事件时快照】\n" + payload
        await c.execute(
            sa.update(outbox)
            .where(outbox.c.sequence == row["sequence"])
            .values(
                status="delivering",
                delivery_payload=payload,
                attempts=attempts,
                lease_token=token,
                lease_until_ms=now_ms + 15000,
                updated_at_ms=now_ms,
            )
        )
    # No PG connection or transaction held while sending. Never log exception text.
    error = None
    try:
        await asyncio.wait_for(channel.send(payload), timeout=3)
    except Exception as exc:  # noqa: BLE001 - redact credentials and platform response
        error = "timeout" if isinstance(exc, TimeoutError) else "channel_rejected"
    status = "accepted" if error is None else "dead" if attempts >= 5 else "retry"
    completed_at_ms = now_ms + (time.monotonic_ns() - started_ns) // 1_000_000
    async with engine.begin() as c:
        await c.execute(sa.text("SET LOCAL statement_timeout='5s'"))
        updated = await c.execute(
            sa.update(outbox)
            .where(
                outbox.c.sequence == row["sequence"],
                outbox.c.lease_token == token,
                outbox.c.status == "delivering",
            )
            .values(
                status=status,
                lease_token=None,
                lease_until_ms=None,
                last_error=error,
                accepted_at_ms=completed_at_ms if error is None else None,
                next_attempt_at_ms=completed_at_ms
                + min(300000, 5000 * 2 ** (attempts - 1)),
                updated_at_ms=now_ms,
            )
        )
        if updated.rowcount != 1:
            return DeliveryResult(status="lease_lost")
        await PostgresMonitorRepository(c).save_if_changed(
            MonitorStateRecord(
                monitor_key="notification:feishu",
                owner_status=MonitorOwnerStatus.RUNNING
                if error is None
                else MonitorOwnerStatus.NEEDS_INTERVENTION
                if status == "dead"
                else MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
                summary="平台已接受；不代表已读"
                if error is None
                else "通知投递失败；有限重试"
                if status == "retry"
                else "通知投递失败；重试已停止",
                intervention="none" if error is None else "检查独立机器人和投递记录",
                updated_at_ms=now_ms,
            )
        )
    return DeliveryResult(status=status)
