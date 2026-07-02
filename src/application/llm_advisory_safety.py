"""Safety checks for LLM advisory outputs.

The advisory plane can summarize and recommend registered strategy families,
but it must not emit executable trading instructions. These helpers keep that
policy explicit before provider output is persisted or pushed.
"""

from __future__ import annotations

from typing import Any

from src.domain.llm_advisory import LlmAdvisoryOutputSafetyReport


FORBIDDEN_TRUTHY_AUTHORITY_KEYS = {
    "live_ready",
    "withdrawal_requested",
    "transfer_requested",
    "strategy_execution_requested",
    "autonomous_order_requested",
    "sizing_override_requested",
    "leverage_override_requested",
    "side_override_requested",
    "execution_intent_requested",
    "order_submit_requested",
    "owner_action_enabled",
    "strategy_execution_authorized",
    "execution_intent_created",
    "order_created",
    "exchange_called",
}

FORBIDDEN_INSTRUCTION_KEYS = {
    "side",
    "direction",
    "quantity",
    "qty",
    "size",
    "notional",
    "leverage",
    "entry_price",
    "stop_loss",
    "take_profit",
    "client_order_id",
    "exchange_order_id",
    "execution_intent_id",
    "order_id",
    "submit_order",
    "place_order",
}

ALLOWED_PROVIDER_KEYS = {
    "recommendation_type",
    "summary",
    "confidence",
    "recommended_strategy_family_ids",
    "observe_only_strategy_family_ids",
    "reason_codes",
    "risk_notes",
    "missing_facts",
    "research_idea_notes",
    "review_notes",
    "feishu_card_type",
}


def evaluate_llm_advisory_output_safety(
    payload: dict[str, Any],
) -> LlmAdvisoryOutputSafetyReport:
    normalized = _normalize_payload(payload)
    blocked_keys: list[str] = []
    for key in _walk_keys(payload):
        lower = key.lower()
        if lower in FORBIDDEN_INSTRUCTION_KEYS:
            blocked_keys.append(key)
        if lower in FORBIDDEN_TRUTHY_AUTHORITY_KEYS and _truthy_value_for_key(
            payload,
            key,
        ):
            blocked_keys.append(key)
    blocked_keys = sorted(set(blocked_keys))
    return LlmAdvisoryOutputSafetyReport(
        status="blocked" if blocked_keys else "pass",
        blocked_keys=blocked_keys,
        blocked_reason_codes=[
            f"llm_output_forbidden_key:{key}" for key in blocked_keys
        ],
        normalized_payload=normalized,
    )


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: payload.get(key) for key in ALLOWED_PROVIDER_KEYS if key in payload}
    if "confidence" in normalized:
        normalized["confidence"] = str(normalized["confidence"])
    return normalized


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _truthy_value_for_key(payload: Any, target_key: str) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) == target_key:
                return bool(value)
            if _truthy_value_for_key(value, target_key):
                return True
    if isinstance(payload, list):
        return any(_truthy_value_for_key(item, target_key) for item in payload)
    return False
