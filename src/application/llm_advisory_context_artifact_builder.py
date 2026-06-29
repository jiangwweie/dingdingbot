"""LLM advisory context artifact builders.

These helpers translate already-trusted BRC runtime facts into the structured
artifact consumed by the advisory plane. They do not fetch exchange facts or
create any execution authority.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmAdvisoryContextArtifact,
    LlmConsumableEvent,
    LlmConsumableEventType,
)
from src.domain.right_tail_review import RightTailReviewSummary


def build_llm_advisory_context_artifact(
    *,
    raw_artifact: dict[str, Any] | None = None,
    now_ms: int,
    default_artifact_id: str | None = None,
    market: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    strategies: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    external_facts: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
) -> LlmAdvisoryContextArtifact:
    artifact = dict(raw_artifact or {})
    return LlmAdvisoryContextArtifact(
        artifact_id=str(
            artifact.get("artifact_id")
            or default_artifact_id
            or f"llm-artifact-{uuid.uuid4().hex[:12]}"
        ),
        artifact_type=str(artifact.get("artifact_type") or "llm_advisory_context_artifact"),
        produced_at_ms=int(artifact.get("produced_at_ms") or now_ms),
        market=_merge_dict(artifact.get("market"), market),
        runtime=_merge_dict(artifact.get("runtime"), runtime),
        strategies=_merge_dict(artifact.get("strategies"), strategies),
        audit=_merge_dict(artifact.get("audit"), audit),
        external_facts=_merge_dict(artifact.get("external_facts"), external_facts),
        review=_merge_dict(artifact.get("review"), review),
        safety={
            "llm_is_fact_consumer_only": True,
            "llm_not_execution_authority": True,
            "feishu_push_only": True,
            "owner_action_must_reenter_console": True,
            **dict(artifact.get("safety") or {}),
        },
        source_refs=_merge_refs(artifact.get("source_refs"), source_refs),
    )


def build_llm_advisory_event(
    *,
    event_type: LlmConsumableEventType,
    source_type: str,
    source_id: str,
    now_ms: int,
    context_artifact: LlmAdvisoryContextArtifact,
    allowed_llm_actions: list[LlmAdvisoryAllowedAction],
    delivery_policy: list[LlmAdvisoryDeliveryChannel] | None = None,
    event_id: str | None = None,
    severity: str = "info",
    symbol: str | None = None,
    timeframe: str | None = None,
    strategy_family_ids: list[str] | None = None,
    dedupe_key: str | None = None,
    occurred_at_ms: int | None = None,
) -> LlmConsumableEvent:
    return LlmConsumableEvent(
        event_id=event_id or f"llm-event-{uuid.uuid4().hex[:12]}",
        event_type=event_type,
        source_type=source_type,
        source_id=source_id,
        severity=severity,
        symbol=symbol,
        timeframe=timeframe,
        strategy_family_ids=list(strategy_family_ids or []),
        dedupe_key=dedupe_key,
        occurred_at_ms=occurred_at_ms or now_ms,
        context_artifact=context_artifact,
        allowed_llm_actions=list(allowed_llm_actions),
        delivery_policy=list(delivery_policy or [LlmAdvisoryDeliveryChannel.LEDGER_ONLY]),
        created_at_ms=now_ms,
    )


def build_trade_review_context_artifact(
    *,
    summary: RightTailReviewSummary,
    now_ms: int,
    artifact_id: str | None = None,
    runtime: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
) -> LlmAdvisoryContextArtifact:
    return build_llm_advisory_context_artifact(
        now_ms=now_ms,
        default_artifact_id=artifact_id,
        runtime=runtime,
        audit=audit,
        review={
            "right_tail_review": summary.model_dump(mode="json"),
            "objective": "bounded_downside_right_tail_capture",
            "not_stable_yield": True,
            "manual_owner_withdrawal_outside_system": True,
        },
        source_refs=source_refs,
    )


def _merge_dict(left: Any, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    merged.update(dict(right or {}))
    return merged


def _merge_refs(left: Any, right: list[str] | None) -> list[str]:
    refs = [str(item) for item in list(left or [])]
    refs.extend(str(item) for item in list(right or []))
    seen: set[str] = set()
    result: list[str] = []
    for item in refs:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
