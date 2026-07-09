"""Stop-risk reservation helpers for ticket-bound action-time flow."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from typing import Any


RISK_RESERVATION_BASIS = "entry_reference_stop_distance_v0"


def compute_stop_risk_reservation(
    *,
    action_time_fact: dict[str, Any],
    protection: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    entry_reference_price = entry_reference_price_from_facts(
        action_time_fact=action_time_fact,
        protection=protection,
    )
    stop_price = _decimal(protection.get("reference_price"))
    target_notional = _decimal(budget.get("target_notional"))
    intended_qty = (
        target_notional / entry_reference_price
        if target_notional > 0 and entry_reference_price > 0
        else Decimal("0")
    )
    risk_at_stop = (
        abs(entry_reference_price - stop_price) * intended_qty
        if entry_reference_price > 0 and stop_price > 0 and intended_qty > 0
        else Decimal("0")
    )
    row = {
        "side": budget.get("side"),
        "entry_reference_price": entry_reference_price,
        "stop_price": stop_price,
        "intended_qty": intended_qty,
        "risk_at_stop": risk_at_stop,
        "risk_reservation_basis": RISK_RESERVATION_BASIS,
    }
    return {**row, "blockers": budget_stop_risk_blockers(row)}


def budget_stop_risk_blockers(budget: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    side = str(budget.get("side") or "").strip().lower()
    entry_reference_price = _decimal(budget.get("entry_reference_price"))
    stop_price = _decimal(budget.get("stop_price"))
    if _decimal(budget.get("entry_reference_price")) <= 0:
        blockers.append("risk_reservation_entry_reference_price_missing")
    if _decimal(budget.get("stop_price")) <= 0:
        blockers.append("risk_reservation_stop_price_missing")
    if _decimal(budget.get("intended_qty")) <= 0:
        blockers.append("risk_reservation_intended_qty_invalid")
    if _decimal(budget.get("risk_at_stop")) <= 0:
        blockers.append("risk_at_stop_invalid")
    if str(budget.get("risk_reservation_basis") or "") != RISK_RESERVATION_BASIS:
        blockers.append("risk_reservation_basis_missing_or_invalid")
    if entry_reference_price > 0 and stop_price > 0:
        if side == "long" and stop_price >= entry_reference_price:
            blockers.append("risk_reservation_stop_side_not_protective")
        elif side == "short" and stop_price <= entry_reference_price:
            blockers.append("risk_reservation_stop_side_not_protective")
        elif side not in {"long", "short"}:
            blockers.append("risk_reservation_side_missing_or_invalid")
    return blockers


def entry_reference_price_from_facts(
    *,
    action_time_fact: dict[str, Any],
    protection: dict[str, Any],
) -> Decimal:
    _ = protection
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    for key in (
        "last_price",
        "mark_price",
        "current_price",
        "close",
        "entry_price",
        "opening_range_low_reference",
    ):
        if key in fact_values:
            value = _decimal(fact_values.get(key))
            if value > 0:
                return value
    return Decimal("0")


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}
