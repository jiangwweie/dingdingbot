"""Typed Owner notification intents and static Feishu card projection."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Any, Literal, Mapping
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


TEMPLATE_VERSION = "owner-notification-v1"
MAX_INTENTS_PER_RUN = 5


class OwnerNotificationKind(str, Enum):
    OPPORTUNITY_DETECTED = "opportunity_detected"
    OPPORTUNITY_NOT_EXECUTED = "opportunity_not_executed"
    TRADE_SUBMITTED = "trade_submitted"
    POSITION_PROTECTED = "position_protected"
    TP1_RUNNER_ACTIVE = "tp1_runner_active"
    TRADE_CLOSED = "trade_closed"
    INTERVENTION_REQUIRED = "intervention_required"
    SYSTEM_TEMPORARILY_UNAVAILABLE = "system_temporarily_unavailable"
    INCIDENT_RECOVERED = "incident_recovered"


class OwnerNotificationSeverity(str, Enum):
    INFO = "info"
    POSITIVE = "positive"
    WARNING = "warning"
    CRITICAL = "critical"


class OwnerNotificationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    notification_kind: OwnerNotificationKind
    severity: OwnerNotificationSeverity
    correlation_id: str = Field(min_length=1, max_length=256)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"] | None = None
    occurred_at_ms: int = Field(ge=0)
    headline: str = Field(min_length=1, max_length=96)
    current_state: str = Field(min_length=1, max_length=300)
    result_summary: str = Field(min_length=1, max_length=300)
    plain_reason: str = Field(min_length=1, max_length=500)
    next_system_action: str = Field(min_length=1, max_length=500)
    owner_action_required: bool
    owner_action: str | None = Field(default=None, max_length=300)
    technical_refs: tuple[str, ...] = ()
    template_version: str = Field(default=TEMPLATE_VERSION, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _require_owner_action(self) -> "OwnerNotificationIntent":
        if self.owner_action_required and not str(self.owner_action or "").strip():
            raise ValueError("owner_action is required when Owner action is required")
        return self


def owner_notification_dedupe_key(
    automation_id: str,
    intent: OwnerNotificationIntent,
) -> str:
    identity = "|".join(
        (
            str(automation_id or "").strip(),
            intent.correlation_id,
            intent.notification_kind.value,
        )
    )
    return "owner_notification:" + sha256(identity.encode("utf-8")).hexdigest()


def render_owner_notification_card(intent: OwnerNotificationIntent) -> dict[str, Any]:
    side_label = {"long": "做多", "short": "做空"}.get(intent.side or "", "-")
    action_label = intent.owner_action if intent.owner_action_required else "无需操作"
    diagnostic_id = sha256(intent.correlation_id.encode("utf-8")).hexdigest()[:12]
    occurred_at = datetime.fromtimestamp(
        intent.occurred_at_ms / 1000,
        tz=ZoneInfo("Asia/Shanghai"),
    ).strftime("%Y-%m-%d %H:%M:%S")
    content = "\n".join(
        (
            f"**策略**：{intent.strategy_group_id}",
            f"**标的**：{intent.symbol}",
            f"**方向**：{side_label}",
            f"**时间**：{occurred_at}（北京时间）",
            "",
            f"**现在**：{intent.current_state}",
            f"**结果**：{intent.result_summary}",
            f"**原因**：{intent.plain_reason}",
            f"**系统接下来**：{intent.next_system_action}",
            f"**你需要做什么**：{action_label}",
            f"**诊断编号**：{diagnostic_id}",
        )
    )
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": _card_color(intent),
                "title": {"tag": "plain_text", "content": intent.headline},
            },
            "elements": [{"tag": "markdown", "content": content}],
        },
    }


def project_owner_notification_intents(
    control_state: Mapping[str, Any],
    *,
    now_ms: int,
) -> list[OwnerNotificationIntent]:
    tickets = _rows(control_state.get("action_time_tickets"))
    ticket_by_id = {
        str(row.get("ticket_id") or ""): row
        for row in tickets
        if str(row.get("ticket_id") or "")
    }
    lifecycle_by_ticket = {
        str(row.get("ticket_id") or ""): row
        for row in sorted(
            _rows(control_state.get("ticket_bound_order_lifecycle_runs")),
            key=_updated_at,
        )
        if str(row.get("ticket_id") or "")
    }
    outcome_by_ticket = {
        str(row.get("ticket_id") or ""): row
        for row in _rows(control_state.get("live_outcome_ledger"))
        if str(row.get("ticket_id") or "")
    }
    intents: list[OwnerNotificationIntent] = []
    active_incidents: set[str] = set()
    incident_ticket_ids: set[str] = set()

    for command in _rows(control_state.get("ticket_bound_exchange_commands")):
        state = str(command.get("command_state") or "")
        if state not in {"outcome_unknown", "hard_stopped"}:
            continue
        command_id = str(command.get("exchange_command_id") or "unknown")
        correlation = f"incident:exchange:{command_id}"
        active_incidents.add(correlation)
        command_ticket_id = str(command.get("ticket_id") or "")
        if command_ticket_id:
            incident_ticket_ids.add(command_ticket_id)
        ticket = ticket_by_id.get(command_ticket_id, {})
        intents.append(
            _critical_intent(
                correlation_id=correlation,
                row={**ticket, **command},
                occurred_at_ms=_updated_at(command) or now_ms,
                current_state="交易所订单结果暂时无法确认",
                reason=(
                    "交易所返回结果与内部记录尚未完成核对"
                    if state == "outcome_unknown"
                    else "交易命令已经停止，系统不能继续自动推进"
                ),
                owner_action="检查交易所订单和持仓状态",
                technical_refs=(f"exchange_command_state:{state}", command_id),
            )
        )

    unsafe_statuses = {
        "entry_filled",
        "entry_unknown",
        "entry_orphaned",
        "entry_partial_fill_unhandled",
        "protection_missing",
        "protection_submit_failed",
        "protection_reconciliation_mismatch",
    }
    for ticket_id, lifecycle in lifecycle_by_ticket.items():
        status = str(lifecycle.get("status") or "")
        if status not in unsafe_statuses:
            continue
        correlation = f"incident:lifecycle:{ticket_id}"
        active_incidents.add(correlation)
        incident_ticket_ids.add(ticket_id)
        intents.append(
            _critical_intent(
                correlation_id=correlation,
                row={**ticket_by_id.get(ticket_id, {}), **lifecycle},
                occurred_at_ms=_updated_at(lifecycle) or now_ms,
                current_state="已经开仓，但保护状态无法确认",
                reason="持仓、保护单或交易所事实尚未完成一致性确认",
                owner_action="检查交易所持仓和保护单",
                technical_refs=(f"lifecycle_status:{status}", ticket_id),
            )
        )

    handled_signal_ids: set[str] = set()
    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id") or "")
        signal_id = str(ticket.get("signal_event_id") or "")
        if ticket_id in incident_ticket_ids:
            if signal_id:
                handled_signal_ids.add(signal_id)
            continue
        lifecycle = lifecycle_by_ticket.get(ticket_id)
        material = _ticket_material_intent(
            ticket,
            lifecycle=lifecycle,
            outcome=outcome_by_ticket.get(ticket_id, {}),
            now_ms=now_ms,
        )
        if material is not None:
            intents.append(material)
            if signal_id:
                handled_signal_ids.add(signal_id)

    notifications = _rows(control_state.get("server_monitor_notifications"))
    sent_by_identity = {
        (
            normalize_owner_correlation_id(
                str(row.get("correlation_id") or "")
            ),
            str(row.get("notification_kind") or ""),
        ): row
        for row in notifications
        if str(row.get("notification_state") or "") == "sent"
    }
    tickets_by_signal: dict[str, list[dict[str, Any]]] = {}
    for ticket in tickets:
        tickets_by_signal.setdefault(str(ticket.get("signal_event_id") or ""), []).append(ticket)

    for signal in _rows(control_state.get("live_signal_events")):
        signal_id = str(signal.get("signal_event_id") or "")
        if not signal_id or signal_id in handled_signal_ids:
            continue
        correlation = owner_correlation_id("signal", signal_id)
        fresh = (
            signal.get("source_kind") == "live_market"
            and signal.get("status") == "facts_validated"
            and signal.get("freshness_state") == "fresh"
            and signal.get("execution_eligible") is True
            and str(signal.get("required_execution_mode") or "") != "observe_only"
            and int(signal.get("expires_at_ms") or 0) > now_ms
        )
        if fresh:
            intents.append(_opportunity_detected(signal, correlation, now_ms))
            continue
        prior_sent = (correlation, OwnerNotificationKind.OPPORTUNITY_DETECTED.value) in sent_by_identity
        submitted = any(
            str(ticket.get("status") or "") in {"submitted", "closed"}
            for ticket in tickets_by_signal.get(signal_id, [])
        )
        if prior_sent and not submitted:
            intents.append(_opportunity_not_executed(signal, correlation, now_ms))

    recovered_already = {
        str(row.get("correlation_id") or "")
        for row in notifications
        if str(row.get("notification_kind") or "")
        == OwnerNotificationKind.INCIDENT_RECOVERED.value
        and str(row.get("notification_state") or "") == "sent"
    }
    for notification in notifications:
        kind = str(notification.get("notification_kind") or "")
        correlation = str(notification.get("correlation_id") or "")
        if kind not in {
            OwnerNotificationKind.INTERVENTION_REQUIRED.value,
            OwnerNotificationKind.SYSTEM_TEMPORARILY_UNAVAILABLE.value,
        }:
            continue
        if str(notification.get("notification_state") or "") != "sent":
            continue
        if not correlation or correlation in active_incidents or correlation in recovered_already:
            continue
        intents.append(_recovery_intent(notification, now_ms))

    unique: dict[tuple[str, str], OwnerNotificationIntent] = {}
    for intent in intents:
        unique[(intent.correlation_id, intent.notification_kind.value)] = intent
    severity_rank = {
        OwnerNotificationSeverity.CRITICAL: 4,
        OwnerNotificationSeverity.WARNING: 3,
        OwnerNotificationSeverity.POSITIVE: 2,
        OwnerNotificationSeverity.INFO: 1,
    }
    return sorted(
        unique.values(),
        key=lambda item: (severity_rank[item.severity], item.occurred_at_ms),
        reverse=True,
    )[:MAX_INTENTS_PER_RUN]


def _ticket_material_intent(
    ticket: Mapping[str, Any],
    *,
    lifecycle: Mapping[str, Any] | None,
    outcome: Mapping[str, Any],
    now_ms: int,
) -> OwnerNotificationIntent | None:
    ticket_id = str(ticket.get("ticket_id") or "")
    if not ticket_id:
        return None
    row = {**ticket, **dict(lifecycle or {})}
    status = str((lifecycle or {}).get("status") or "")
    values: dict[str, Any] | None = None
    if status == "lifecycle_closed":
        pnl = str(outcome.get("net_pnl") or "待结算")
        r_multiple = str(outcome.get("r_multiple") or "待计算")
        values = {
            "kind": OwnerNotificationKind.TRADE_CLOSED,
            "severity": OwnerNotificationSeverity.POSITIVE,
            "headline": "交易已经结束",
            "current": "持仓已经关闭并进入复盘",
            "result": f"净收益 {pnl}，R 倍数 {r_multiple}",
            "reason": "交易生命周期已经完成",
            "next": "系统保留结果并等待下一次机会",
        }
    elif status == "runner_protected":
        values = {
            "kind": OwnerNotificationKind.TP1_RUNNER_ACTIVE,
            "severity": OwnerNotificationSeverity.POSITIVE,
            "headline": "已止盈一部分，剩余仓位继续运行",
            "current": "第一目标已经完成，剩余仓位受到保护",
            "result": "部分利润已经锁定",
            "reason": "策略进入右尾收益跟踪阶段",
            "next": "系统继续跟踪剩余仓位和保护单",
        }
    elif status == "position_protected":
        values = {
            "kind": OwnerNotificationKind.POSITION_PROTECTED,
            "severity": OwnerNotificationSeverity.POSITIVE,
            "headline": "交易已成交并完成保护",
            "current": "仓位已经建立，止损和止盈保护已确认",
            "result": "交易正在正常运行",
            "reason": "交易所订单和内部记录已经核对",
            "next": "系统继续跟踪 TP1、Runner 和最终退出",
        }
    elif status in {"entry_submit_sent", "entry_fill_pending"} or str(
        ticket.get("status") or ""
    ) == "submitted":
        values = {
            "kind": OwnerNotificationKind.TRADE_SUBMITTED,
            "severity": OwnerNotificationSeverity.INFO,
            "headline": "真实订单已提交",
            "current": "交易所正在处理订单",
            "result": "等待成交和保护确认",
            "reason": "当前机会已经通过系统检查",
            "next": "系统将确认成交并建立保护",
        }
    if values is None:
        return None
    return OwnerNotificationIntent(
        notification_kind=values["kind"],
        severity=values["severity"],
        correlation_id=owner_correlation_id("ticket", ticket_id),
        strategy_group_id=_group(row),
        symbol=_symbol(row),
        side=_side(row),
        occurred_at_ms=_updated_at(row) or int(ticket.get("created_at_ms") or now_ms),
        headline=values["headline"],
        current_state=values["current"],
        result_summary=values["result"],
        plain_reason=values["reason"],
        next_system_action=values["next"],
        owner_action_required=False,
        owner_action=None,
        technical_refs=(f"ticket:{ticket_id}", f"lifecycle_status:{status}"),
    )


def _opportunity_detected(
    signal: Mapping[str, Any],
    correlation: str,
    now_ms: int,
) -> OwnerNotificationIntent:
    return OwnerNotificationIntent(
        notification_kind=OwnerNotificationKind.OPPORTUNITY_DETECTED,
        severity=OwnerNotificationSeverity.INFO,
        correlation_id=correlation,
        strategy_group_id=_group(signal),
        symbol=_symbol(signal),
        side=_side(signal),
        occurred_at_ms=int(signal.get("observed_at_ms") or now_ms),
        headline="发现交易机会",
        current_state="系统正在进行下单前检查",
        result_summary="尚未下单",
        plain_reason="策略条件刚刚满足",
        next_system_action="系统会继续完成账户、风险和订单检查",
        owner_action_required=False,
        owner_action=None,
        technical_refs=(correlation,),
    )


def _opportunity_not_executed(
    signal: Mapping[str, Any],
    correlation: str,
    now_ms: int,
) -> OwnerNotificationIntent:
    return OwnerNotificationIntent(
        notification_kind=OwnerNotificationKind.OPPORTUNITY_NOT_EXECUTED,
        severity=OwnerNotificationSeverity.INFO,
        correlation_id=correlation,
        strategy_group_id=_group(signal),
        symbol=_symbol(signal),
        side=_side(signal),
        occurred_at_ms=int(
            signal.get("invalidated_at_ms")
            or signal.get("expires_at_ms")
            or now_ms
        ),
        headline="交易机会已经结束",
        current_state="系统没有为这次机会建立真实仓位",
        result_summary="最终没有下单",
        plain_reason=_terminal_signal_reason(signal),
        next_system_action="系统继续等待下一次符合条件的机会",
        owner_action_required=False,
        owner_action=None,
        technical_refs=(
            correlation,
            f"signal_status:{str(signal.get('status') or '')}",
        ),
    )


def _critical_intent(
    *,
    correlation_id: str,
    row: Mapping[str, Any],
    occurred_at_ms: int,
    current_state: str,
    reason: str,
    owner_action: str,
    technical_refs: tuple[str, ...],
) -> OwnerNotificationIntent:
    return OwnerNotificationIntent(
        notification_kind=OwnerNotificationKind.INTERVENTION_REQUIRED,
        severity=OwnerNotificationSeverity.CRITICAL,
        correlation_id=correlation_id,
        strategy_group_id=_group(row),
        symbol=_symbol(row),
        side=_side(row),
        occurred_at_ms=occurred_at_ms,
        headline="需要你关注交易状态",
        current_state=current_state,
        result_summary="系统已暂停相关的新开仓推进",
        plain_reason=reason,
        next_system_action="系统继续执行只读核对和安全恢复",
        owner_action_required=True,
        owner_action=owner_action,
        technical_refs=technical_refs,
    )


def _terminal_signal_reason(signal: Mapping[str, Any]) -> str:
    status = str(signal.get("status") or "")
    freshness = str(signal.get("freshness_state") or "")
    if status == "rejected":
        return "最终检查没有满足策略或交易条件"
    if status == "superseded":
        return "更新的市场状态替代了原来的机会"
    if status == "stale" or freshness in {"stale", "expired"}:
        return "信号在全部下单条件完成前已经过期"
    return "机会结束前没有完成全部交易条件"


def _recovery_intent(
    notification: Mapping[str, Any],
    now_ms: int,
) -> OwnerNotificationIntent:
    return OwnerNotificationIntent(
        notification_kind=OwnerNotificationKind.INCIDENT_RECOVERED,
        severity=OwnerNotificationSeverity.POSITIVE,
        correlation_id=str(notification.get("correlation_id") or ""),
        strategy_group_id=_group(notification),
        symbol=_symbol(notification),
        side=_side(notification),
        occurred_at_ms=now_ms,
        headline="问题已经恢复",
        current_state="此前报告的异常已经不再存在",
        result_summary="系统已恢复正常观察或处理",
        plain_reason="最新运行事实已经重新一致",
        next_system_action="系统继续按当前策略范围运行",
        owner_action_required=False,
        owner_action=None,
        technical_refs=(str(notification.get("notification_id") or ""),),
    )


def _card_color(intent: OwnerNotificationIntent) -> str:
    if intent.severity is OwnerNotificationSeverity.CRITICAL:
        return "red"
    if intent.severity is OwnerNotificationSeverity.WARNING:
        return "orange"
    if intent.severity is OwnerNotificationSeverity.POSITIVE:
        return "green"
    if intent.notification_kind is OwnerNotificationKind.OPPORTUNITY_NOT_EXECUTED:
        return "grey"
    return "blue"


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _updated_at(row: Mapping[str, Any]) -> int:
    return int(
        row.get("updated_at_ms")
        or row.get("resolved_at_ms")
        or row.get("created_at_ms")
        or row.get("observed_at_ms")
        or 0
    )


def _group(row: Mapping[str, Any]) -> str:
    return str(row.get("strategy_group_id") or "runtime")


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "all")


def _side(row: Mapping[str, Any]) -> Literal["long", "short"] | None:
    value = str(row.get("side") or "")
    return value if value in {"long", "short"} else None


def owner_correlation_id(prefix: str, identity: str) -> str:
    value = str(identity or "")
    return value if value.startswith(f"{prefix}:") else f"{prefix}:{value}"


def normalize_owner_correlation_id(value: str) -> str:
    normalized = str(value or "")
    for prefix in ("signal", "ticket"):
        doubled = f"{prefix}:{prefix}:"
        while normalized.startswith(doubled):
            normalized = normalized.removeprefix(f"{prefix}:")
    return normalized
