"""Adapters from runtime artifacts to LLM advisory events.

The adapter is intentionally read-only: it translates existing runtime artifacts
into LlmConsumableEvent instances and leaves persistence, LLM generation, and
Feishu delivery to the advisory plane.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

from src.application.llm_advisory_context_artifact_builder import (
    build_llm_advisory_event,
    build_llm_advisory_context_artifact,
)
from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmConsumableEvent,
    LlmConsumableEventType,
)


OWNER_NOTIFICATION_BLOCKED_REASONS = {
    "runtime_progress_cache_missing",
    "runtime_progress_cache_stale",
    "runtime_progress_cache_schema_stale",
    "runtime_progress_cache_runtime_head_stale",
}

WATCHER_NOISE_STATUSES = {
    "watching_no_signal",
    "waiting_for_signal",
    "no_action",
    "observation_running_no_signal",
}

WATCHER_SIGNAL_STATUSES = {
    "runtime_signal_ready",
    "runtime_signal_ready_for_non_executing_prepare",
    "runtime_prepare_records_ready_for_preview",
    "prepared_shadow_evidence_ready_for_owner_review",
    "operator_evidence_needs_review",
    "ready_for_final_gate_preflight",
}

FORBIDDEN_CONTEXT_KEYS = {
    "api_key",
    "authorization",
    "client_order_id",
    "direction",
    "entry_price",
    "exchange_order_id",
    "leverage",
    "notional",
    "order_id",
    "qty",
    "quantity",
    "secret",
    "side",
    "signature",
    "size",
    "stop_loss",
    "take_profit",
    "token",
    "webhook",
    "webhook_secret",
    "webhook_url",
}

FORBIDDEN_CONTEXT_KEY_NORMALIZED = {
    "apikey",
    "authorization",
    "clientorderid",
    "direction",
    "entryprice",
    "exchangeorderid",
    "leverage",
    "notional",
    "orderid",
    "qty",
    "quantity",
    "secret",
    "side",
    "signature",
    "size",
    "stoploss",
    "takeprofit",
    "token",
    "webhook",
    "webhooksecret",
    "webhookurl",
}

SENSITIVE_CONTEXT_KEY_SUBSTRINGS = (
    "authorization",
    "secret",
    "signature",
    "token",
    "webhook",
)


def now_ms() -> int:
    return int(time.time() * 1000)


def build_daily_check_advisory_event(
    report: dict[str, Any],
    *,
    now: int | None = None,
    source_ref: str | None = None,
) -> LlmConsumableEvent:
    """Build one digest event from a daily-check report."""

    timestamp = now if now is not None else now_ms()
    status = _string(report.get("status"), "unknown")
    notification = _dict(report.get("notification"))
    blockers = _string_list(_dict(report.get("checks")).get("blockers"))
    warnings = _string_list(_dict(report.get("checks")).get("warnings"))
    context_artifact = build_llm_advisory_context_artifact(
        now_ms=timestamp,
        default_artifact_id=f"llm-daily-check-{_source_suffix(report, status)}",
        runtime={
            "source": "daily_check",
            "status": status,
            "runtime_status": report.get("runtime_status"),
            "notification": _safe_fragment(notification),
            "owner_summary": _safe_fragment(report.get("owner_summary")),
            "checks": _safe_fragment(
                _pick(
                    _dict(report.get("checks")),
                    [
                        "waiting_for_market",
                        "blockers",
                        "product_gaps",
                        "fresh_signal_notification_policy_checked",
                        "runtime_dry_run_scenario_count",
                        "real_order_readiness_summary",
                    ],
                )
            ),
        },
        audit={
            "schema_version": report.get("schema_version"),
            "interaction": _safe_fragment(report.get("interaction")),
            "source": _safe_fragment(report.get("source")),
            "warnings": warnings,
        },
        source_refs=_source_refs(source_ref),
    )
    return build_llm_advisory_event(
        event_type=LlmConsumableEventType.DAILY_AUDIT_DIGEST,
        source_type="daily_check",
        source_id=_source_id(report, default="strategygroup_runtime_daily_check"),
        now_ms=timestamp,
        context_artifact=context_artifact,
        allowed_llm_actions=_allowed_actions_for_digest(blockers=blockers),
        delivery_policy=_delivery_policy(notification=notification, status=status),
        severity=_severity(status=status, blockers=blockers),
        dedupe_key=_dedupe_key("daily_check", status, notification.get("reason"), blockers),
    )


def build_completion_audit_advisory_event(
    report: dict[str, Any],
    *,
    now: int | None = None,
    source_ref: str | None = None,
) -> LlmConsumableEvent:
    """Build one digest event from the first-live completion audit."""

    timestamp = now if now is not None else now_ms()
    status = _string(report.get("status"), "unknown")
    gaps = _string_list(report.get("non_market_gaps")) + _string_list(
        report.get("non_market_blockers")
    )
    notification = _dict(report.get("notification"))
    context_artifact = build_llm_advisory_context_artifact(
        now_ms=timestamp,
        default_artifact_id=f"llm-completion-audit-{_source_suffix(report, status)}",
        runtime={
            "source": "completion_audit",
            "status": status,
            "runtime_status": report.get("runtime_status"),
            "goal_complete": bool(report.get("goal_complete")),
            "market_dependent_remaining": report.get("market_dependent_remaining"),
        },
        audit={
            "non_market_gaps": gaps,
            "live_closure_evidence_boundary": _safe_fragment(
                report.get("live_closure_evidence_boundary")
            ),
            "interaction": _safe_fragment(report.get("interaction")),
        },
        source_refs=_source_refs(source_ref),
    )
    return build_llm_advisory_event(
        event_type=LlmConsumableEventType.DAILY_AUDIT_DIGEST,
        source_type="completion_audit",
        source_id=_source_id(report, default="runtime_completion_audit"),
        now_ms=timestamp,
        context_artifact=context_artifact,
        allowed_llm_actions=_allowed_actions_for_digest(blockers=gaps),
        delivery_policy=_delivery_policy(notification=notification, status=status),
        severity=_severity(status=status, blockers=gaps),
        dedupe_key=_dedupe_key("completion_audit", status, None, gaps),
    )


def build_watcher_artifact_advisory_event(
    artifact: dict[str, Any],
    *,
    now: int | None = None,
    source_ref: str | None = None,
) -> LlmConsumableEvent:
    """Build one event from a runtime signal watcher artifact."""

    timestamp = now if now is not None else now_ms()
    status = _watcher_status(artifact)
    event_type = _watcher_event_type(status)
    signal_summary = _first_signal_summary(artifact)
    strategy_ids = _strategy_family_ids(artifact)
    notification = _dict(artifact.get("notification"))
    blockers = _string_list(artifact.get("blockers")) + _string_list(
        _dict(artifact.get("latest_summary")).get("blockers")
    )
    context_artifact = build_llm_advisory_context_artifact(
        now_ms=timestamp,
        default_artifact_id=f"llm-watcher-{_source_suffix(artifact, status)}",
        market={
            "status": status,
            "signal_status": signal_summary.get("status"),
            "signal_type": signal_summary.get("signal_type"),
            "confidence": signal_summary.get("confidence"),
            "reason_codes": _string_list(signal_summary.get("reason_codes")),
        },
        runtime={
            "source": "runtime_signal_watcher",
            "status": status,
            "post_signal_auto_resume": _safe_fragment(artifact.get("post_signal_auto_resume")),
            "notification": _safe_fragment(notification),
            "watcher_tick_plan": _safe_fragment(artifact.get("watcher_tick_plan")),
            "safety_invariants": _safe_fragment(artifact.get("safety_invariants")),
        },
        strategies={
            "strategy_family_ids": strategy_ids,
            "symbol": _first_string_for_keys(artifact, ["symbol"]),
            "timeframe": _first_string_for_keys(artifact, ["timeframe"]),
        },
        audit={
            "operator_evidence_status": _string(
                _dict(artifact.get("operator_evidence")).get("status"),
                "",
            ),
            "wakeup_evidence_status": _string(
                _dict(artifact.get("wakeup_evidence")).get("status"),
                "",
            ),
            "blockers": blockers,
        },
        source_refs=_source_refs(source_ref),
    )
    return build_llm_advisory_event(
        event_type=event_type,
        source_type="runtime_signal_watcher",
        source_id=_source_id(artifact, default="runtime_signal_watcher_artifact"),
        now_ms=timestamp,
        context_artifact=context_artifact,
        allowed_llm_actions=_allowed_actions_for_event(event_type, blockers=blockers),
        delivery_policy=_watcher_delivery_policy(status=status, notification=notification),
        severity=_severity(status=status, blockers=blockers),
        symbol=_first_string_for_keys(artifact, ["symbol"]),
        timeframe=_first_string_for_keys(artifact, ["timeframe"]),
        strategy_family_ids=strategy_ids,
        dedupe_key=_dedupe_key("watcher", status, notification.get("reason"), blockers),
    )


def build_trade_closed_advisory_event(
    artifact: dict[str, Any],
    *,
    now: int | None = None,
    source_ref: str | None = None,
) -> LlmConsumableEvent:
    """Build a post-trade review event from a closed-trade artifact."""

    timestamp = now if now is not None else now_ms()
    trade_id = _string(
        artifact.get("trade_id") or artifact.get("position_id") or artifact.get("review_id"),
        "trade_closed",
    )
    context_artifact = build_llm_advisory_context_artifact(
        now_ms=timestamp,
        default_artifact_id=f"llm-trade-closed-{trade_id}",
        runtime={
            "source": "trade_closed",
            "status": _string(artifact.get("status"), "trade_closed"),
            "symbol": artifact.get("symbol"),
        },
        review={
            "trade_id": trade_id,
            "review_status": artifact.get("review_status") or "review_due",
            "settlement_status": artifact.get("settlement_status"),
            "outcome_summary": _safe_fragment(artifact.get("outcome_summary")),
        },
        source_refs=_source_refs(source_ref),
    )
    return build_llm_advisory_event(
        event_type=LlmConsumableEventType.TRADE_CLOSED,
        source_type="trade_closed",
        source_id=trade_id,
        now_ms=timestamp,
        context_artifact=context_artifact,
        allowed_llm_actions=[
            LlmAdvisoryAllowedAction.REVIEW_CLOSED_TRADE,
            LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
        ],
        delivery_policy=[LlmAdvisoryDeliveryChannel.FEISHU_PUSH],
        severity="info",
        symbol=_string(artifact.get("symbol"), None),
        dedupe_key=_dedupe_key("trade_closed", trade_id, artifact.get("review_status"), []),
    )


def build_review_due_advisory_event(
    artifact: dict[str, Any],
    *,
    now: int | None = None,
    source_ref: str | None = None,
) -> LlmConsumableEvent:
    """Build a review-due reminder event."""

    timestamp = now if now is not None else now_ms()
    review_id = _string(artifact.get("review_id") or artifact.get("trade_id"), "review_due")
    context_artifact = build_llm_advisory_context_artifact(
        now_ms=timestamp,
        default_artifact_id=f"llm-review-due-{review_id}",
        runtime={
            "source": "review_due",
            "status": _string(artifact.get("status"), "review_due"),
        },
        review={
            "review_id": review_id,
            "reason": artifact.get("reason"),
            "strategy_family_ids": _strategy_family_ids(artifact),
        },
        source_refs=_source_refs(source_ref),
    )
    return build_llm_advisory_event(
        event_type=LlmConsumableEventType.REVIEW_DUE,
        source_type="review_due",
        source_id=review_id,
        now_ms=timestamp,
        context_artifact=context_artifact,
        allowed_llm_actions=[
            LlmAdvisoryAllowedAction.REVIEW_CLOSED_TRADE,
            LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
        ],
        delivery_policy=[LlmAdvisoryDeliveryChannel.FEISHU_PUSH],
        severity="info",
        strategy_family_ids=_strategy_family_ids(artifact),
        dedupe_key=_dedupe_key("review_due", review_id, artifact.get("reason"), []),
    )


def _delivery_policy(
    *,
    notification: dict[str, Any],
    status: str,
) -> list[LlmAdvisoryDeliveryChannel]:
    reason = _string(notification.get("reason"), "")
    if notification.get("owner_notify") is False:
        return [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    if reason in OWNER_NOTIFICATION_BLOCKED_REASONS:
        return [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    if notification.get("notification_result") == "NOTIFY":
        return [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    if status in {"processing", "fresh_signal_detected", "fresh_signal_processing"}:
        return [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    return [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]


def _watcher_delivery_policy(
    *,
    status: str,
    notification: dict[str, Any],
) -> list[LlmAdvisoryDeliveryChannel]:
    if status in WATCHER_NOISE_STATUSES:
        return [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    if notification.get("required") is False:
        return [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]
    if status in WATCHER_SIGNAL_STATUSES or "blocked" in status or "anomaly" in status:
        return [LlmAdvisoryDeliveryChannel.FEISHU_PUSH]
    return _delivery_policy(notification=notification, status=status)


def _watcher_event_type(status: str) -> LlmConsumableEventType:
    if "protection" in status and "anomaly" in status:
        return LlmConsumableEventType.PROTECTION_ANOMALY_DETECTED
    if "blocked" in status:
        return LlmConsumableEventType.FINAL_GATE_BLOCKED
    if status in WATCHER_SIGNAL_STATUSES:
        return LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED
    return LlmConsumableEventType.DAILY_AUDIT_DIGEST


def _allowed_actions_for_event(
    event_type: LlmConsumableEventType,
    *,
    blockers: list[str],
) -> list[LlmAdvisoryAllowedAction]:
    if event_type == LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED:
        return [
            LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
            LlmAdvisoryAllowedAction.EXPLAIN_MARKET_CONTEXT,
        ]
    if event_type in {
        LlmConsumableEventType.FINAL_GATE_BLOCKED,
        LlmConsumableEventType.PROTECTION_ANOMALY_DETECTED,
    }:
        return [
            LlmAdvisoryAllowedAction.EXPLAIN_BLOCKER,
            LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT,
        ]
    return _allowed_actions_for_digest(blockers=blockers)


def _allowed_actions_for_digest(*, blockers: list[str]) -> list[LlmAdvisoryAllowedAction]:
    actions = [LlmAdvisoryAllowedAction.SUMMARIZE_AUDIT]
    if blockers:
        actions.append(LlmAdvisoryAllowedAction.EXPLAIN_BLOCKER)
    return actions


def _watcher_status(artifact: dict[str, Any]) -> str:
    for key in ("status", "latest_status"):
        value = artifact.get(key)
        if value:
            return str(value)
    for key in (
        "wakeup_evidence",
        "operator_evidence",
        "latest_summary",
    ):
        nested = _dict(artifact.get(key))
        value = nested.get("status")
        if value:
            return str(value)
    return "unknown"


def _first_signal_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if isinstance(value.get("signal_summary"), dict):
            return _dict(value.get("signal_summary"))
        for nested in value.values():
            result = _first_signal_summary(nested)
            if result:
                return result
    if isinstance(value, list):
        for item in value:
            result = _first_signal_summary(item)
            if result:
                return result
    return {}


def _strategy_family_ids(value: Any) -> list[str]:
    ids = _walk_string_values(value, {"strategy_family_id", "strategy_group_id"})
    ids.extend(_walk_string_list_values(value, {"strategy_family_ids", "strategy_group_ids"}))
    return _dedupe(ids)


def _first_string_for_keys(value: Any, keys: Iterable[str]) -> str | None:
    matches = _walk_string_values(value, set(keys))
    return matches[0] if matches else None


def _walk_string_values(value: Any, keys: set[str]) -> list[str]:
    results: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in keys and isinstance(nested, str) and nested:
                results.append(nested)
            results.extend(_walk_string_values(nested, keys))
    elif isinstance(value, list):
        for item in value:
            results.extend(_walk_string_values(item, keys))
    return results


def _walk_string_list_values(value: Any, keys: set[str]) -> list[str]:
    results: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in keys and isinstance(nested, list):
                results.extend(str(item) for item in nested if item)
            else:
                results.extend(_walk_string_list_values(nested, keys))
    elif isinstance(value, list):
        for item in value:
            results.extend(_walk_string_list_values(item, keys))
    return results


def _safe_fragment(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if _is_forbidden_context_key(key_text):
                continue
            result[key_text] = _safe_fragment(nested)
        return result
    if isinstance(value, list):
        return [_safe_fragment(item) for item in value]
    return value


def _is_forbidden_context_key(key: str) -> bool:
    normalized = _normalize_context_key(key)
    if key.lower() in FORBIDDEN_CONTEXT_KEYS:
        return True
    if normalized in FORBIDDEN_CONTEXT_KEY_NORMALIZED:
        return True
    return any(item in normalized for item in SENSITIVE_CONTEXT_KEY_SUBSTRINGS)


def _normalize_context_key(key: str) -> str:
    return "".join(character.lower() for character in key if character.isalnum())


def _pick(value: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: value[key] for key in keys if key in value}


def _severity(*, status: str, blockers: list[str]) -> str:
    lowered = status.lower()
    if "hard_safety" in lowered or "forbidden" in lowered:
        return "critical"
    if blockers or "blocked" in lowered or "unavailable" in lowered:
        return "warning"
    if "processing" in lowered or "fresh_signal" in lowered:
        return "notice"
    return "info"


def _dedupe_key(
    source: str,
    status: Any,
    reason: Any,
    blockers: list[str],
) -> str:
    blocker_part = ",".join(_dedupe(blockers)) or "none"
    reason_part = _string(reason, "none")
    return f"{source}:{_string(status, 'unknown')}:{reason_part}:{blocker_part}"


def _source_id(artifact: dict[str, Any], *, default: str) -> str:
    return _string(
        artifact.get("event_id")
        or artifact.get("artifact_id")
        or artifact.get("report_id")
        or artifact.get("id")
        or artifact.get("generated_at_utc")
        or artifact.get("created_at_utc"),
        default,
    )[:128]


def _source_suffix(artifact: dict[str, Any], fallback: str) -> str:
    return _source_id(artifact, default=fallback).replace(":", "-").replace("/", "-")[:80]


def _source_refs(source_ref: str | None) -> list[str]:
    return [source_ref] if source_ref else []


def _string(value: Any, default: str | None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item)]
    return [str(value)] if str(value) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
