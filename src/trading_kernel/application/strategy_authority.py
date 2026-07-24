"""Current Strategy Registry authority checks for a frozen new-entry Ticket."""

from __future__ import annotations

from src.trading_kernel.application.ports import (
    EventSpecSnapshot,
    StrategyGroupSnapshot,
    StrategyVersionSnapshot,
)
from src.trading_kernel.domain.ticket import TradeTicket


def strategy_authority_matches_ticket(
    strategy_group: StrategyGroupSnapshot | None,
    strategy_version: StrategyVersionSnapshot | None,
    event_spec: EventSpecSnapshot | None,
    ticket: TradeTicket,
) -> bool:
    """Require exact active Group, Version, and EventSpec authority for ENTRY."""

    runtime = ticket.identity.runtime
    return bool(
        strategy_group
        and strategy_group.status == "active"
        and strategy_group.strategy_group_id == runtime.strategy_group_id
        and strategy_group.active_version_id == runtime.strategy_version_id
        and strategy_version
        and strategy_version.status == "active"
        and strategy_version.strategy_group_id == runtime.strategy_group_id
        and strategy_version.strategy_version_id == runtime.strategy_version_id
        and event_spec
        and event_spec.status == "active"
        and event_spec.event_spec_id == runtime.event_spec_id
        and event_spec.strategy_version_id == runtime.strategy_version_id
        and event_spec.position_side == ticket.identity.netting_domain.position_side
        and event_spec.entry_order_type == ticket.entry_order_type.value
    )
