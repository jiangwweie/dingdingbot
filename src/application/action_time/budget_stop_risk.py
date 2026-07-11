"""Stop-risk reservation helpers for ticket-bound action-time flow."""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Any


from src.application.action_time.pricing_sizing import (
    RISK_RESERVATION_BASIS,
    budget_stop_risk_blockers as _typed_budget_stop_risk_blockers,
    materialize_ticket_sizing_risk_decision,
    pricing_reference_from_action_time_fact_values,
)


def compute_stop_risk_reservation(
    *,
    action_time_fact: dict[str, Any],
    protection: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    pricing_result = pricing_reference_from_action_time_fact_values(fact_values)
    decision_result = (
        materialize_ticket_sizing_risk_decision(
            pricing_reference=pricing_result.reference,
            target_notional=budget.get("target_notional"),
            stop_price=protection.get("reference_price"),
        )
        if pricing_result.reference is not None
        else None
    )
    decision = decision_result.decision if decision_result is not None else None
    row = {
        "side": budget.get("side"),
        "entry_reference_price": (
            decision.entry_reference_price if decision is not None else Decimal("0")
        ),
        "stop_price": decision.stop_price if decision is not None else Decimal("0"),
        "intended_qty": (
            decision.intended_qty if decision is not None else Decimal("0")
        ),
        "risk_at_stop": (
            decision.risk_at_stop if decision is not None else Decimal("0")
        ),
        "risk_reservation_basis": RISK_RESERVATION_BASIS,
    }
    blockers = [
        *pricing_result.blockers,
        *(decision_result.blockers if decision_result is not None else ()),
    ]
    return {**row, "blockers": list(dict.fromkeys(blockers))}


def budget_stop_risk_blockers(budget: dict[str, Any]) -> list[str]:
    return _typed_budget_stop_risk_blockers(budget)


def entry_reference_price_from_facts(
    *,
    action_time_fact: dict[str, Any],
    protection: dict[str, Any],
) -> Decimal:
    _ = protection
    fact_values = _as_dict(action_time_fact.get("fact_values"))
    result = pricing_reference_from_action_time_fact_values(fact_values)
    return (
        result.reference.entry_reference_price
        if result.reference is not None
        else Decimal("0")
    )


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
