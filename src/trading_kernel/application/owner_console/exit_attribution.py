"""Canonical, display-safe attribution for persisted Ticket exit causes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.trading_kernel.application.owner_console.models import (
        ExitAttribution,
        TradeItemFacts,
    )

_CONTROLLED_PREFIXES = (
    "owner_flatten_all:",
    "deployment_drain:",
)
_LABELS = {
    "initial_stop_triggered": "初始止损触发",
    "take_profit_triggered": "止盈成交触发",
    "failed_breakout_reclaimed": "假突破回收退出",
    "failed_breakdown_reclaimed": "假跌破回收退出",
    "sor_session_expired": "交易时段到期退出",
    "exposure_session_expired": "交易时段到期退出",
    "pre_tp1_time_stop_hit": "TP1 前持仓超时退出",
    "absolute_time_stop_hit": "持仓达到最长时限退出",
    "protection_stop_triggered": "保护止损成交",
    "time_stop_hit": "持仓时间到期退出",
    "strategy_exit": "策略条件退出",
    "recover_exit_rejection": "退出恢复处理",
    "initial_stop_rejected": "初始止损异常后受控退出",
    "initial_stop_absent": "初始止损缺失后受控退出",
    "runner_stop": "Runner 止损退出",
    "runner_exit": "Runner 退出",
    "Initial Stop": "初始止损触发",
    "TP1 + Runner Exit": "TP1 后 Runner 退出",
    "Controlled Exit": "受控退出",
    "External Flat / Exit Fills Unavailable": "外部平仓已确认，成交明细不可得",
    "external_flat_exit_fills_unavailable": "外部平仓已确认，成交明细不可得",
}


@dataclass(frozen=True)
class CanonicalExitAttribution:
    """One persisted reason code and its non-speculative Owner-facing label."""

    code: str
    label: str


def canonical_exit_attribution(code: str) -> CanonicalExitAttribution:
    """Render an exact persisted cause; unknown codes stay visible, never guessed."""

    normalized = code.strip()
    if not normalized:
        raise ValueError("exit attribution code must be non-blank")
    if normalized.startswith("owner_flatten_all:"):
        label = "Owner 全部持仓受控平仓"
    elif normalized.startswith("deployment_drain:"):
        label = "部署前安全退出"
    else:
        label = _LABELS.get(normalized, "退出原因未识别")
    return CanonicalExitAttribution(code=normalized, label=label)


def exit_reason_group(code: str | None) -> str:
    """Aggregate causes without turning individual audit IDs into categories."""
    if code is None:
        return "exit_reason_unavailable"
    if code.startswith("owner_flatten_all:"):
        return "owner_flatten_all"
    if code.startswith("deployment_drain:"):
        return "deployment_drain"
    return code


def classify_exit(
    code: str | None,
) -> Literal["strategy", "owner", "safety", "unknown"]:
    """Classify explicit facts only; a non-Owner exit is not automatically natural."""
    if not code:
        return "unknown"
    if code.startswith("owner_flatten_all:"):
        return "owner"
    if code.startswith(("deployment_drain:", "ticket_incident:")) or code in {
        "recover_exit_rejection",
        "initial_stop_rejected",
        "initial_stop_absent",
        "Controlled Exit",
    }:
        return "safety"
    if code in strategy_exit_codes():
        return "strategy"
    return "unknown"


def is_controlled_exit(code: str | None) -> bool:
    """Classify only explicit Owner or deployment controlled exits."""

    return code is not None and code.strip().startswith(_CONTROLLED_PREFIXES)


def review_fill_exit_attribution(facts: TradeItemFacts) -> ExitAttribution | None:
    """Attribute only a terminal current Review fill to its exact owned order."""
    from decimal import Decimal, InvalidOperation, localcontext

    from src.trading_kernel.application.owner_console.models import (
        EvidenceRef,
        ExitAttribution,
    )

    if facts.aggregate_status != "terminal" or facts.review_id is None:
        return None
    metrics = facts.review_metrics or {}
    rows = metrics.get("order_attribution")
    if not isinstance(rows, list) or not rows or len(rows) > 512:
        return None
    commands = {c.command_id: c for c in facts.exit_commands}
    exits = []
    seen = set()
    total = Decimal(0)
    for row in rows:
        if not isinstance(row, dict) or row.get("role") not in {"entry", "exit"}:
            return None
        if row["role"] != "exit":
            continue
        command_id = row.get("command_id")
        if not isinstance(command_id, str):
            return None
        command = commands.get(command_id)
        order_id = row.get("exchange_order_id")
        time = row.get("occurred_at_ms")
        if (
            command is None
            or command.ticket_id != facts.ticket_id
            or command.status not in {"accepted", "reconciled_accepted"}
            or not isinstance(order_id, str)
            or not order_id
            or isinstance(time, bool)
            or not isinstance(time, int)
            or time < max(facts.issued_at_ms, command.created_at_ms)
            or time > (facts.terminal_at_ms or 0)
        ):
            return None
        try:
            raw_quantity = row.get("quantity")
            if not isinstance(raw_quantity, str):
                return None
            quantity = Decimal(raw_quantity)
            if not quantity.is_finite() or quantity <= 0:
                return None
        except InvalidOperation:
            return None
        trade_id = row.get("exchange_trade_id")
        if not isinstance(trade_id, str) or not trade_id or trade_id in seen:
            return None
        seen.add(trade_id)
        # Review producer resolves conditional algo IDs into actual fill order IDs.
        # Their numbers differ; exact current Review command_id owns that linkage.
        with localcontext() as context:
            context.prec = 80
            total += quantity
        exits.append((time, command))
    if not exits:
        return None
    # A partial exit is not proof of the final flat position.
    try:
        entry_quantity = metrics.get("entry_quantity")
        if not isinstance(entry_quantity, str) or Decimal(entry_quantity) != total:
            return None
    except InvalidOperation:
        return None
    latest = max(time for time, _ in exits)
    kinds = {command.command_kind for time, command in exits if time == latest}
    if len(kinds) != 1:
        return None
    kind = next(iter(kinds))
    code = {
        "initial_stop": "initial_stop_triggered",
        "replace_protection": "runner_stop"
        if facts.tp1_reached
        else "protection_stop_triggered",
        "take_profit": "take_profit_triggered",
    }.get(kind)
    if code is None or facts.review_created_at_ms is None:
        return None
    refs = [
        EvidenceRef(
            kind="review",
            identity=facts.review_id,
            occurred_at_ms=facts.review_created_at_ms,
        )
    ]
    for time, command in exits:
        if time == latest:
            ref = EvidenceRef(
                kind="command",
                identity=command.command_id,
                occurred_at_ms=command.created_at_ms,
            )
            if ref not in refs:
                refs.append(ref)
    return ExitAttribution(
        code=code,
        label=canonical_exit_attribution(code).label,
        source="review_fills",
        evidence=tuple(refs),
    )


def strategy_exit_codes() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "initial_stop_triggered",
                "take_profit_triggered",
                "failed_breakout_reclaimed",
                "failed_breakdown_reclaimed",
                "sor_session_expired",
                "exposure_session_expired",
                "pre_tp1_time_stop_hit",
                "absolute_time_stop_hit",
                "time_stop_hit",
                "strategy_exit",
                "runner_stop",
                "runner_exit",
                "protection_stop_triggered",
                "Initial Stop",
                "TP1 + Runner Exit",
            }
        )
    )
