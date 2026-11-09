"""Transactional display-only outbox; network I/O is not owned by this repository."""

from hashlib import sha256

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.notice_templates import render_notice
from src.trading_kernel.domain.notices import TEMPLATE_VERSION, NoticeSnapshot
from src.trading_kernel.infrastructure.pg_models import notice_outbox


async def enqueue_notice(connection: AsyncConnection, snapshot: NoticeSnapshot) -> None:
    key = sha256(
        f"{snapshot.ticket_id}:{snapshot.event_id}:{snapshot.kind}:feishu".encode()
    ).hexdigest()
    await connection.execute(
        insert(notice_outbox)
        .values(
            notice_key=key,
            stream_key=snapshot.ticket_id,
            ticket_id=snapshot.ticket_id,
            kind=snapshot.kind.value,
            state_version=snapshot.state_version,
            snapshot=snapshot.model_dump(mode="json"),
            payload=render_notice(snapshot),
            template_version=TEMPLATE_VERSION,
            channel="feishu",
            status="pending",
            attempts=0,
            next_attempt_at_ms=snapshot.event_at_ms,
            created_at_ms=snapshot.event_at_ms,
            updated_at_ms=snapshot.event_at_ms,
        )
        .on_conflict_do_nothing(index_elements=["notice_key"])
    )


async def enqueue_runtime_notice(connection: AsyncConnection, previous, state) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.trading_kernel.application.ports import MonitorOwnerStatus

    if state.monitor_key.startswith("notification:"):
        return
    failed = state.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
    was_failed = (
        previous is not None
        and previous["owner_status"] == MonitorOwnerStatus.NEEDS_INTERVENTION
    )
    recovered = was_failed and state.owner_status in {
        MonitorOwnerStatus.COMPLETED,
        MonitorOwnerStatus.RUNNING,
    }
    if not (failed and (not was_failed or previous["summary"] != state.summary) or recovered):
        return
    kind = "runtime_fault" if failed else "runtime_recovered"
    digest = sha256(state.monitor_key.encode()).hexdigest()
    clock = datetime.fromtimestamp(
        state.updated_at_ms // 1000, ZoneInfo("Asia/Shanghai")
    )
    subject = "对账" if state.monitor_key.startswith("reconciliation") else "运行"
    payload = "\n".join(
        (
            f"【首尔】{subject}{'异常待处理' if failed else '检查恢复'}｜{clock:%m-%d %H:%M}",
            "系统已记录异常，需要检查控制台"
            if failed
            else "该项检查已恢复；其他门槛仍独立生效",
            "当前持仓与保护以控制台和 App 为准",
            "https://manual.jiaoyingpan.cloud/trading/",
        )
    )
    await connection.execute(
        insert(notice_outbox)
        .values(
            notice_key=sha256(
                f"{digest}:{state.projection_version}:{kind}".encode()
            ).hexdigest(),
            stream_key="monitor:" + digest,
            ticket_id=None,
            kind=kind,
            state_version=state.projection_version,
            snapshot=state.model_dump(mode="json"),
            payload=payload,
            template_version=TEMPLATE_VERSION,
            channel="feishu",
            status="pending",
            attempts=0,
            next_attempt_at_ms=state.updated_at_ms,
            created_at_ms=state.updated_at_ms,
            updated_at_ms=state.updated_at_ms,
        )
        .on_conflict_do_nothing(index_elements=["notice_key"])
    )


async def read_delivery_summary(connection: AsyncConnection):
    import sqlalchemy as sa

    from src.trading_kernel.application.owner_console.models import (
        NoticeDeliverySummary,
    )
    from src.trading_kernel.infrastructure.pg_models import monitor_current

    pending = (
        sa.select(notice_outbox.c.sequence)
        .where(notice_outbox.c.status.in_(["pending", "retry", "delivering"]))
        .limit(501)
        .subquery()
    )
    failed = (
        sa.select(notice_outbox.c.sequence)
        .where(notice_outbox.c.status == "dead")
        .limit(501)
        .subquery()
    )
    row = (
        (
            await connection.execute(
                sa.select(
                    sa.select(sa.func.count())
                    .select_from(pending)
                    .scalar_subquery()
                    .label("pending"),
                    sa.select(sa.func.count())
                    .select_from(failed)
                    .scalar_subquery()
                    .label("failed"),
                    sa.select(monitor_current.c.owner_status)
                    .where(monitor_current.c.monitor_key == "notification:feishu")
                    .scalar_subquery()
                    .label("monitor"),
                    sa.select(notice_outbox.c.accepted_at_ms)
                    .where(notice_outbox.c.status == "accepted")
                    .order_by(notice_outbox.c.sequence.desc())
                    .limit(1)
                    .scalar_subquery()
                    .label("accepted"),
                )
            )
        )
        .mappings()
        .one()
    )
    return NoticeDeliverySummary(
        channel_state="unknown"
        if row["monitor"] is None
        else "missing"
        if row["monitor"] == "not_enabled"
        else "configured",
        pending_count=min(row["pending"], 500),
        failed_count=min(row["failed"], 500),
        pending_count_capped=row["pending"] > 500,
        failed_count_capped=row["failed"] > 500,
        last_accepted_at_ms=row["accepted"],
    )
