"""Transactional display-only outbox; network I/O is not owned by this repository."""

import os
from hashlib import sha256

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.notice_templates import render_notice
from src.trading_kernel.domain.notices import TEMPLATE_VERSION, NoticeSnapshot
from src.trading_kernel.infrastructure.pg_models import notice_outbox


async def enqueue_notice(connection: AsyncConnection, snapshot: NoticeSnapshot) -> None:
    snapshot = snapshot.model_copy(update={"site_label": notice_site_label()})
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
    recovered = (
        was_failed
        or previous is not None
        and previous["summary"] == "trade_closed_economics_incomplete"
        and state.summary == "review_economics_completed"
    ) and state.owner_status in {
        MonitorOwnerStatus.COMPLETED,
        MonitorOwnerStatus.RUNNING,
    }
    if not (
        failed and (not was_failed or previous["summary"] != state.summary) or recovered
    ):
        return
    kind = "runtime_fault" if failed else "runtime_recovered"
    digest = sha256(state.monitor_key.encode()).hexdigest()
    clock = datetime.fromtimestamp(
        state.updated_at_ms // 1000, ZoneInfo("Asia/Shanghai")
    )
    subject = "对账" if state.monitor_key.startswith("reconciliation") else "运行"
    payload = "\n".join(
        (
            f"【{notice_site_label()}】{subject}{'异常待处理' if failed else '检查恢复'}｜{clock:%m-%d %H:%M}",
            "系统已记录异常，需要检查控制台"
            if failed
            else "盈亏核算已补齐"
            if state.summary == "review_economics_completed"
            else "交易已收尾，盈亏数据仍待补齐"
            if state.summary == "trade_closed_economics_incomplete"
            else "该项检查已恢复；其他门槛仍独立生效",
            "当前持仓与保护以控制台和 App 为准",
            notice_console_url(),
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


async def enqueue_position_operation_notice(
    connection: AsyncConnection, row: dict
) -> None:
    """Display-only result delivery; never used to decide an operation transition."""
    labels = {
        "handed_to_lifecycle": "原止盈已成交，人工操作已结束，继续自动管理",
        "natural_tp_reconciling": "原止盈成交已记账，在途指令待核实",
        "repreview_required": "旧止盈操作已结束，需重新预览并确认",
        "completed": "操作完成",
        "wait_price": "减仓完成，余仓自动续管",
        "runner_continuing": "减仓完成，Runner继续",
        "closed": "交易收尾完成",
        "failed": "操作失败",
        "rejected": "操作未执行",
        "revoked": "操作授权已撤销",
        "review_required": "操作结果待核实",
        "restore_required": "原计划恢复待核实",
    }
    if row["state"] not in labels:
        return
    key = sha256(
        f"owner-operation:{row['operation_id']}:{row['state']}:feishu".encode()
    ).hexdigest()
    await connection.execute(
        insert(notice_outbox)
        .values(
            notice_key=key,
            stream_key=row["ticket_id"],
            ticket_id=row["ticket_id"],
            kind="owner_operation",
            state_version=row["version"],
            snapshot={
                "operation_id": row["operation_id"],
                "ticket_id": row["ticket_id"],
                "state": row["state"],
                "version": row["version"],
                "reason": row["first_blocker"],
            },
            payload="【"
            + notice_site_label()
            + "】"
            + labels[row["state"]]
            + "\n操作："
            + row["operation_id"]
            + "\n"
            + (row["first_blocker"] or ""),
            template_version="seoul-owner-operation-v1",
            channel="feishu",
            status="pending",
            attempts=0,
            next_attempt_at_ms=row["updated_at_ms"],
            created_at_ms=row["updated_at_ms"],
            updated_at_ms=row["updated_at_ms"],
        )
        .on_conflict_do_nothing(index_elements=["notice_key"])
    )


def notice_site_label() -> str:
    label = os.environ.get("TRADING_KERNEL_NOTICE_SITE", "首尔")
    if label not in {"首尔", "东京"}:
        raise ValueError("notice_site_invalid")
    return label


def notice_console_url() -> str:
    from urllib.parse import urlsplit

    origin = os.environ.get(
        "TRADING_KERNEL_CONSOLE_ORIGIN", "https://manual.jiaoyingpan.cloud"
    )
    parts = urlsplit(origin)
    if (
        parts.scheme != "https"
        or parts.netloc not in {"manual.jiaoyingpan.cloud", "jiaoyingpan.cloud"}
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise ValueError("notice_origin_invalid")
    return origin + "/trading/"
