"""Pure compact phone templates built exclusively from frozen observed facts."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from zoneinfo import ZoneInfo

from src.trading_kernel.domain.notices import NoticeKind, NoticeSnapshot


def format_number(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("notice numbers must be finite")
    text = format(value, ",f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_amount(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("notice amounts must be finite")
    if 0 < abs(value) < Decimal(".01"):
        return ("-" if value < 0 else "") + "<0.01U"
    with localcontext() as ctx:
        ctx.prec = max(38, len(value.as_tuple().digits) + 4)
        rounded = value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return format_number(rounded) + "U"


_TITLES = {
    NoticeKind.OPENED: "开仓已保护",
    NoticeKind.TAKEOVER: "已转人工",
    NoticeKind.TP1: "TP1 成交",
    NoticeKind.MANUAL_FILL: "退出成交",
    NoticeKind.CLOSED: "已平仓",
    NoticeKind.RESIDUAL: "已平仓·待清残单",
    NoticeKind.RISK: "风险变化",
    NoticeKind.RECOVERED: "保护事实恢复",
    NoticeKind.REVIEW: "状态待核实",
    NoticeKind.REVIEW_CLEARED: "核实完成",
}


def render_notice(facts: NoticeSnapshot) -> str:
    mode = {"AUTO": "自动", "MANUAL": "人工", "REVIEW_REQUIRED": "自动处置暂停"}[
        facts.mode
    ]
    title = f"【首尔】{facts.symbol} {'多' if facts.side == 'long' else '空'}｜{_TITLES[facts.kind]}｜{mode}"
    qty = "待核实" if facts.quantity is None else format_number(facts.quantity)
    position = f"余仓 {qty} {facts.symbol}"
    if facts.quantity is not None and facts.entry_price is not None:
        position += f"｜入场计 {format_amount(facts.quantity * facts.entry_price)}"
    entry = (
        "入场均价待核实"
        if facts.entry_price is None
        else f"均价 {format_number(facts.entry_price)}"
    )
    if facts.fill_quantity is not None:
        label = "累计成交" if facts.kind is NoticeKind.MANUAL_FILL else "成交"
        entry += f"｜{facts.fill_role or 'TP1'} {label} {format_number(facts.fill_quantity)} {facts.symbol}"
        if facts.fill_price is not None:
            entry += f" @ {format_number(facts.fill_price)}"
    if facts.quantity == 0:
        stop = "仓位已归零"
        if facts.residual_order_count is not None:
            stop += f"｜残单 {facts.residual_order_count}"
        else:
            stop += "｜残单待核实"
    elif facts.protection == "unknown":
        prices = " / ".join(format_number(s.price) for s in facts.stops[:3])
        stop = f"止损 {prices}｜覆盖待核实" if prices else "止损待核实"
        if len(facts.stops) > 3:
            stop += f"（共{len(facts.stops)}档）"
    else:
        prices = " / ".join(format_number(s.price) for s in facts.stops)
        stop = f"止损 {prices}" if prices else "未确认有效止损"
        if facts.protection == "full":
            stop += "｜全仓覆盖"
        elif facts.quantity is not None and facts.protected_quantity is not None:
            gap = max(Decimal(0), facts.quantity - facts.protected_quantity)
            stop += f"｜未覆盖 {format_number(gap)} {facts.symbol}"
    if facts.kind is NoticeKind.RISK and facts.risk_at_stop is not None:
        stop += f"｜止损风险 {format_amount(facts.risk_at_stop)}"
    if facts.new_entry_restricted:
        stop += "｜新开仓受限"
    clock = datetime.fromtimestamp(facts.event_at_ms // 1000, ZoneInfo("Asia/Shanghai"))
    footer = f"{facts.strategy}｜{facts.strategy_semantics}｜{clock:%H:%M}"
    if facts.mode == "MANUAL":
        footer += "｜后续退出由你管理"
    return f"{title}\n{position}\n{entry}\n{stop}\n{footer}"
