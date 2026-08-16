"""Canonical, display-safe attribution for persisted Ticket exit causes."""

from __future__ import annotations

from dataclasses import dataclass

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
    if normalized.startswith("owner_flatten_all"):
        label = "Owner 手动平仓"
    elif normalized.startswith("deployment_drain"):
        label = "部署前安全退出"
    else:
        label = _LABELS.get(normalized, f"系统请求退出（{normalized}）")
    return CanonicalExitAttribution(code=normalized, label=label)


def is_controlled_exit(code: str | None) -> bool:
    """Classify only explicit Owner or deployment controlled exits."""

    return code is not None and code.strip().startswith(_CONTROLLED_PREFIXES)
