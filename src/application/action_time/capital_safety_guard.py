"""Capital-safety guard for ticket-bound pre-submit paths.

The guard is intentionally read-only. It converts PG scope-freeze current state
into the blocker vocabulary consumed by promotion, ticket, FinalGate, Operation
Layer, Runtime Safety State, and protected submit materializers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BLOCKING_SCOPE_STATUSES = {"frozen", "unknown_risk"}
CLEANUP_ONLY_BLOCKERS = {
    "scope_cleanup_pending_no_current_risk",
    "cleanup_pending_no_current_risk",
    "stale_local_state_cleanup_pending",
}


@dataclass(frozen=True)
class CapitalSafetyScopeStatus:
    scope_key: str
    status: str
    first_blocker: str
    risk_present: bool
    cleanup_required: bool
    recovery_command_id: str
    explanation_code: str
    blockers: tuple[str, ...]

    @property
    def blocks_new_trade_intent(self) -> bool:
        return self.status in BLOCKING_SCOPE_STATUSES and bool(self.blockers)


def current_scope_status(
    control_state: dict[str, Any],
    *,
    strategy_group_id: Any,
    symbol: Any,
    side: Any,
    account_id: Any = "",
    exchange_instrument_id: Any = "",
) -> CapitalSafetyScopeStatus:
    """Return the current capital-safety status for one StrategyGroup/symbol/side.

    An active scope freeze blocks new trade intent only when it represents
    current risk or unknown live exchange risk. Cleanup-only stale local state is
    surfaced but does not block.
    """

    strategy_group_id = str(strategy_group_id or "").strip()
    symbol = str(symbol or "").strip()
    side = str(side or "").strip()
    account_id = str(account_id or "").strip()
    exchange_instrument_id = str(exchange_instrument_id or "").strip()
    scope_key = ":".join(
        value
        for value in (
            account_id,
            strategy_group_id,
            exchange_instrument_id or symbol,
            side,
        )
        if value
    )
    command_rows = [
        row
        for row in _rows(control_state.get("ticket_bound_exchange_commands"))
        if str(row.get("command_state") or "")
        in {"outcome_unknown", "hard_stopped"}
        and _row_affects_scope(
            row,
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=side,
            account_id=account_id,
            exchange_instrument_id=exchange_instrument_id,
        )
    ]
    if command_rows:
        command = sorted(
            command_rows,
            key=lambda item: int(item.get("updated_at_ms") or 0),
        )[-1]
        state = str(command.get("command_state") or "")
        blocker = (
            "exchange_command_outcome_unknown"
            if state == "outcome_unknown"
            else "exchange_command_hard_stopped"
        )
        return CapitalSafetyScopeStatus(
            scope_key=scope_key,
            status="unknown_risk" if state == "outcome_unknown" else "frozen",
            first_blocker=blocker,
            risk_present=state == "hard_stopped",
            cleanup_required=False,
            recovery_command_id=str(command.get("exchange_command_id") or ""),
            explanation_code=blocker,
            blockers=(blocker,),
        )
    rows = [
        row
        for row in _rows(control_state.get("ticket_bound_scope_freezes"))
        if str(row.get("status") or "") == "active"
        and _row_affects_scope(
            row,
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=side,
            account_id=account_id,
            exchange_instrument_id=exchange_instrument_id,
        )
    ]
    if not rows:
        return CapitalSafetyScopeStatus(
            scope_key=scope_key,
            status="clear",
            first_blocker="",
            risk_present=False,
            cleanup_required=False,
            recovery_command_id="",
            explanation_code="capital_safety_scope_clear",
            blockers=(),
        )

    row = sorted(rows, key=lambda item: int(item.get("updated_at_ms") or 0))[-1]
    first_blocker = str(row.get("first_blocker") or "scope_frozen_for_lifecycle_recovery")
    blockers = _dedupe([first_blocker, *_list_texts(row.get("blockers"))])
    if _is_cleanup_only(first_blocker, blockers):
        return CapitalSafetyScopeStatus(
            scope_key=scope_key,
            status="cleanup_only",
            first_blocker=first_blocker,
            risk_present=False,
            cleanup_required=True,
            recovery_command_id=str(row.get("source_id") or ""),
            explanation_code="scope_cleanup_pending_no_current_risk",
            blockers=(),
        )

    unknown_risk = any("unknown" in blocker or "exchange_only" in blocker for blocker in blockers)
    blocking_blocker = (
        "scope_frozen_for_exchange_unknown_risk"
        if unknown_risk
        else "scope_frozen_for_lifecycle_recovery"
    )
    return CapitalSafetyScopeStatus(
        scope_key=scope_key,
        status="unknown_risk" if unknown_risk else "frozen",
        first_blocker=first_blocker,
        risk_present=not unknown_risk,
        cleanup_required=False,
        recovery_command_id=str(row.get("source_id") or ""),
        explanation_code=blocking_blocker,
        blockers=(blocking_blocker,),
    )


def current_scope_blockers(
    control_state: dict[str, Any],
    *,
    strategy_group_id: Any,
    symbol: Any,
    side: Any,
    account_id: Any = "",
    exchange_instrument_id: Any = "",
) -> list[str]:
    status = current_scope_status(
        control_state,
        strategy_group_id=strategy_group_id,
        symbol=symbol,
        side=side,
        account_id=account_id,
        exchange_instrument_id=exchange_instrument_id,
    )
    return list(status.blockers)


def _is_cleanup_only(first_blocker: str, blockers: list[str]) -> bool:
    values = {first_blocker, *blockers}
    return any(
        value in CLEANUP_ONLY_BLOCKERS
        or value.endswith(":scope_cleanup_pending_no_current_risk")
        or "no_current_risk" in value
        or "cleanup_only" in value
        for value in values
    )


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "")]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _row_affects_scope(
    row: dict[str, Any],
    *,
    strategy_group_id: str,
    symbol: str,
    side: str,
    account_id: str,
    exchange_instrument_id: str,
) -> bool:
    row_mode = str(row.get("position_mode") or "")
    domain_key = str(row.get("netting_domain_key") or "").strip()
    typed_domain = bool(
        domain_key
        and not domain_key.startswith("legacy_unknown")
        and row_mode in {"one_way", "hedge", "unknown"}
    )
    if not typed_domain:
        return (
            str(row.get("strategy_group_id") or "") == strategy_group_id
            and str(row.get("symbol") or "") == symbol
            and str(row.get("side") or "") == side
        )
    if account_id and str(row.get("account_id") or "") != account_id:
        return False
    if exchange_instrument_id and str(
        row.get("exchange_instrument_id") or ""
    ) != exchange_instrument_id:
        return False
    if not account_id and str(row.get("symbol") or "") != symbol:
        return False
    if row_mode == "one_way" or str(row.get("position_bucket") or "") == "ANY":
        return True
    expected_bucket = "LONG" if side == "long" else "SHORT"
    return str(row.get("position_bucket") or "") == expected_bucket
