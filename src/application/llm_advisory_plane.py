"""Event-driven LLM advisory plane.

This service is deliberately outside the execution chain. It consumes typed
events and structured packets, persists advisory output, and may push a Feishu
notification. Owner confirmation still belongs to the canonical console/runtime
governance path.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Protocol

import aiohttp

from src.application.bounded_risk_campaign_service import BrcRuleViolation
from src.domain.llm_advisory import (
    LlmAdvisoryAllowedAction,
    LlmAdvisoryDeliveryChannel,
    LlmAdvisoryInboxItem,
    LlmAdvisoryInboxSummary,
    LlmAdvisoryRecommendation,
    LlmAdvisoryRecommendationType,
    LlmAdvisoryResult,
    LlmAdvisoryStatus,
    LlmConsumableEvent,
    LlmFeishuCardType,
)
from src.application.llm_advisory_cards import format_feishu_advisory_markdown
from src.application.llm_advisory_safety import evaluate_llm_advisory_output_safety
from src.domain.strategy_semantics import (
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


PROMPT_VERSION = "llm_advisory_plane_v1"


def _now_ms() -> int:
    return int(time.time() * 1000)


class LlmAdvisoryRepositoryPort(Protocol):
    async def initialize(self) -> None:
        ...

    async def save_event(self, event: LlmConsumableEvent) -> LlmConsumableEvent:
        ...

    async def get_event(self, event_id: str) -> Optional[LlmConsumableEvent]:
        ...

    async def list_events(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> list[LlmConsumableEvent]:
        ...

    async def save_recommendation(
        self,
        recommendation: LlmAdvisoryRecommendation,
    ) -> LlmAdvisoryRecommendation:
        ...

    async def get_recommendation(
        self,
        recommendation_id: str,
    ) -> Optional[LlmAdvisoryRecommendation]:
        ...

    async def list_recommendations(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[LlmAdvisoryRecommendation]:
        ...


class LlmAdvisoryProvider(Protocol):
    provider_name: str
    model_name: Optional[str]

    async def generate(
        self,
        *,
        event: LlmConsumableEvent,
        registered_strategy_family_ids: set[str],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LlmAdvisoryPushResult:
    channel: LlmAdvisoryDeliveryChannel
    delivered: bool
    delivered_at_ms: Optional[int] = None
    error: Optional[str] = None


class LlmAdvisoryPushPort(Protocol):
    async def push(
        self,
        *,
        event: LlmConsumableEvent,
        recommendation: LlmAdvisoryRecommendation,
    ) -> LlmAdvisoryPushResult:
        ...


@dataclass(frozen=True)
class OpenAICompatibleLlmAdvisoryProvider:
    """OpenAI-compatible advisory provider using the existing BRC LLM env."""

    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: int = 20
    provider_name: str = "openai_compatible"

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLlmAdvisoryProvider":
        if os.getenv("BRC_LLM_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise BrcRuleViolation("BRC LLM provider disabled")
        base_url = (
            os.getenv("BRC_LLM_BASE_URL", "").strip()
            or os.getenv("llm_openai_url", "").strip()
        )
        api_key = (
            os.getenv("BRC_LLM_API_KEY", "").strip()
            or os.getenv("llm_openai_key", "").strip()
        )
        model = os.getenv("BRC_LLM_MODEL", "").strip()
        if not base_url or not api_key or not model:
            raise BrcRuleViolation("BRC LLM provider env is incomplete")
        timeout = int(os.getenv("BRC_LLM_TIMEOUT_SECONDS", "20"))
        return cls(base_url=base_url, api_key=api_key, model_name=model, timeout_seconds=timeout)

    async def generate(
        self,
        *,
        event: LlmConsumableEvent,
        registered_strategy_family_ids: set[str],
    ) -> dict[str, Any]:
        url = self.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions" if url.endswith("/v1") else f"{url}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _advisory_system_prompt(registered_strategy_family_ids)},
                {
                    "role": "user",
                    "content": json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                text = await response.text()
                if response.status >= 400:
                    raise BrcRuleViolation(f"BRC LLM advisory provider failed with HTTP {response.status}")
        parsed = json.loads(text)
        content = parsed["choices"][0]["message"]["content"]
        return json.loads(content)


@dataclass(frozen=True)
class NotificationServiceAdvisoryPush:
    """Push LLM advisory output through the runtime notification service."""

    notification_service: Any

    async def push(
        self,
        *,
        event: LlmConsumableEvent,
        recommendation: LlmAdvisoryRecommendation,
    ) -> LlmAdvisoryPushResult:
        if self.notification_service is None:
            return LlmAdvisoryPushResult(
                channel=LlmAdvisoryDeliveryChannel.FEISHU_PUSH,
                delivered=False,
                error="notification service is unavailable",
            )
        message = format_feishu_advisory_message(event=event, recommendation=recommendation)
        try:
            send_advisory_message = getattr(self.notification_service, "send_advisory_message", None)
            if callable(send_advisory_message):
                await send_advisory_message(message)
            else:
                await self.notification_service.send_system_alert(
                    "BRC_LLM_ADVISORY",
                    message,
                )
        except Exception as exc:
            return LlmAdvisoryPushResult(
                channel=LlmAdvisoryDeliveryChannel.FEISHU_PUSH,
                delivered=False,
                error=str(exc),
            )
        return LlmAdvisoryPushResult(
            channel=LlmAdvisoryDeliveryChannel.FEISHU_PUSH,
            delivered=True,
            delivered_at_ms=_now_ms(),
        )


class LlmAdvisoryPlaneService:
    """Coordinates advisory events, LLM generation, ledger persistence, and push."""

    def __init__(
        self,
        *,
        repository: LlmAdvisoryRepositoryPort,
        provider: Optional[LlmAdvisoryProvider] = None,
        push_service: Optional[LlmAdvisoryPushPort] = None,
        semantics_catalog: Optional[StrategySemanticsCatalog] = None,
    ) -> None:
        self._repo = repository
        self._provider = provider
        self._push_service = push_service
        self._catalog = semantics_catalog or initial_strategy_semantics_catalog()
        self._registered_strategy_family_ids = _registered_strategy_family_ids(self._catalog)

    async def initialize(self) -> None:
        await self._repo.initialize()

    @property
    def registered_strategy_family_ids(self) -> set[str]:
        return set(self._registered_strategy_family_ids)

    async def consume_event(self, event: LlmConsumableEvent) -> LlmAdvisoryResult:
        self._validate_event_strategy_ids(event)
        event = await self._repo.save_event(event)
        recommendation = await self._generate_recommendation(event)
        recommendation = await self._repo.save_recommendation(recommendation)
        if (
            recommendation.status == LlmAdvisoryStatus.GENERATED
            and LlmAdvisoryDeliveryChannel.FEISHU_PUSH in event.delivery_policy
        ):
            recommendation = await self._push_feishu(event=event, recommendation=recommendation)
        return LlmAdvisoryResult(event=event, recommendation=recommendation)

    async def get_event(self, event_id: str) -> Optional[LlmConsumableEvent]:
        return await self._repo.get_event(event_id)

    async def list_events(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> list[LlmConsumableEvent]:
        return await self._repo.list_events(limit=limit, event_type=event_type)

    async def get_recommendation(
        self,
        recommendation_id: str,
    ) -> Optional[LlmAdvisoryRecommendation]:
        return await self._repo.get_recommendation(recommendation_id)

    async def list_recommendations(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[LlmAdvisoryRecommendation]:
        return await self._repo.list_recommendations(
            limit=limit,
            event_type=event_type,
            status=status,
        )

    async def inbox_summary(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> LlmAdvisoryInboxSummary:
        recommendations = await self.list_recommendations(
            limit=limit,
            event_type=event_type,
            status=status,
        )
        items = [
            LlmAdvisoryInboxItem(
                recommendation_id=item.recommendation_id,
                event_id=item.event_id,
                event_type=item.event_type,
                source_type=item.source_type,
                source_id=item.source_id,
                status=item.status,
                recommendation_type=item.recommendation_type,
                feishu_card_type=item.feishu_card_type,
                summary=item.summary,
                recommended_strategy_family_ids=list(item.recommended_strategy_family_ids),
                missing_facts=list(item.missing_facts),
                risk_notes=list(item.risk_notes),
                pushed_to_feishu_at_ms=item.pushed_to_feishu_at_ms,
                push_error=item.push_error,
                created_at_ms=item.created_at_ms,
            )
            for item in recommendations
        ]
        return LlmAdvisoryInboxSummary(
            status_counts=_count_by([item.status.value for item in items]),
            event_type_counts=_count_by([item.event_type.value for item in items]),
            pending_push_failure_count=sum(
                1 for item in items if item.status == LlmAdvisoryStatus.PUSH_FAILED
            ),
            items=items,
        )

    async def _generate_recommendation(
        self,
        event: LlmConsumableEvent,
    ) -> LlmAdvisoryRecommendation:
        now = _now_ms()
        try:
            provider = self._provider or OpenAICompatibleLlmAdvisoryProvider.from_env()
            payload = await provider.generate(
                event=event,
                registered_strategy_family_ids=self._registered_strategy_family_ids,
            )
            return self._recommendation_from_payload(
                event=event,
                payload=payload,
                provider_name=provider.provider_name,
                model_name=provider.model_name,
                now=now,
            )
        except Exception as exc:
            return LlmAdvisoryRecommendation(
                recommendation_id=f"llm-adv-{uuid.uuid4().hex[:12]}",
                event_id=event.event_id,
                event_type=event.event_type,
                source_type=event.source_type,
                source_id=event.source_id,
                recommendation_type=LlmAdvisoryRecommendationType.UNKNOWN,
                status=LlmAdvisoryStatus.BLOCKED,
                summary=f"LLM advisory generation blocked: {exc}",
                confidence=Decimal("0"),
                reason_codes=["llm_advisory_generation_blocked"],
                provider_name="llm_advisory_plane",
                model_name=None,
                prompt_version=PROMPT_VERSION,
                raw_response_summary={"error": str(exc)},
                delivery_channels=list(event.delivery_policy),
                owner_action_route="/console",
                created_at_ms=now,
                updated_at_ms=now,
            )

    def _recommendation_from_payload(
        self,
        *,
        event: LlmConsumableEvent,
        payload: dict[str, Any],
        provider_name: str,
        model_name: Optional[str],
        now: int,
    ) -> LlmAdvisoryRecommendation:
        recommended = _string_list(payload.get("recommended_strategy_family_ids"))
        observe_only = _string_list(payload.get("observe_only_strategy_family_ids"))
        safety_report = evaluate_llm_advisory_output_safety(payload)
        unknown = sorted(
            set(recommended + observe_only).difference(self._registered_strategy_family_ids)
        )
        status = LlmAdvisoryStatus.GENERATED
        reason_codes = _string_list(payload.get("reason_codes"))
        summary = str(payload.get("summary") or "LLM advisory generated")
        recommendation_type = _enum_or_default(
            LlmAdvisoryRecommendationType,
            payload.get("recommendation_type"),
            LlmAdvisoryRecommendationType.UNKNOWN,
        )
        if safety_report.status == "blocked":
            status = LlmAdvisoryStatus.BLOCKED
            reason_codes = [*reason_codes, *safety_report.blocked_reason_codes]
            summary = (
                "LLM advisory blocked because provider output contained "
                "execution-like or fund-movement instructions."
            )
            recommended = []
            observe_only = []
        if unknown:
            status = LlmAdvisoryStatus.BLOCKED
            reason_codes = [*reason_codes, "unregistered_strategy_family_recommended"]
            summary = (
                "LLM advisory blocked because it recommended unregistered "
                f"strategy families: {', '.join(unknown)}"
            )
            recommended = [item for item in recommended if item not in unknown]
            observe_only = [item for item in observe_only if item not in unknown]

        confidence = Decimal(str(payload.get("confidence", "0")))
        raw_summary = {
            "keys": sorted(str(key) for key in payload.keys()),
            "recommended_strategy_family_ids": recommended,
            "observe_only_strategy_family_ids": observe_only,
            "recommendation_type": recommendation_type.value,
            "safety_status": safety_report.status,
            "blocked_keys": safety_report.blocked_keys,
        }
        return LlmAdvisoryRecommendation(
            recommendation_id=f"llm-adv-{uuid.uuid4().hex[:12]}",
            event_id=event.event_id,
            event_type=event.event_type,
            source_type=event.source_type,
            source_id=event.source_id,
            recommendation_type=recommendation_type,
            status=status,
            summary=summary,
            confidence=confidence,
            recommended_strategy_family_ids=recommended,
            observe_only_strategy_family_ids=observe_only,
            reason_codes=reason_codes,
            risk_notes=_string_list(payload.get("risk_notes")),
            missing_facts=_string_list(payload.get("missing_facts")),
            research_idea_notes=_string_list(payload.get("research_idea_notes")),
            review_notes=_string_list(payload.get("review_notes")),
            feishu_card_type=_enum_or_default(
                LlmFeishuCardType,
                payload.get("feishu_card_type"),
                LlmFeishuCardType.GENERIC_ADVISORY,
            ),
            provider_name=provider_name,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            raw_response_summary=raw_summary,
            delivery_channels=list(event.delivery_policy),
            owner_action_route="/console",
            created_at_ms=now,
            updated_at_ms=now,
        )

    async def _push_feishu(
        self,
        *,
        event: LlmConsumableEvent,
        recommendation: LlmAdvisoryRecommendation,
    ) -> LlmAdvisoryRecommendation:
        if self._push_service is None:
            updated = recommendation.model_copy(
                update={
                    "status": LlmAdvisoryStatus.PUSH_FAILED,
                    "push_error": "Feishu push service is unavailable",
                    "updated_at_ms": _now_ms(),
                }
            )
            return await self._repo.save_recommendation(updated)
        result = await self._push_service.push(event=event, recommendation=recommendation)
        updated = recommendation.model_copy(
            update={
                "status": LlmAdvisoryStatus.PUSHED if result.delivered else LlmAdvisoryStatus.PUSH_FAILED,
                "pushed_to_feishu_at_ms": result.delivered_at_ms,
                "push_error": result.error,
                "updated_at_ms": _now_ms(),
            }
        )
        return await self._repo.save_recommendation(updated)

    def _validate_event_strategy_ids(self, event: LlmConsumableEvent) -> None:
        unknown = sorted(set(event.strategy_family_ids).difference(self._registered_strategy_family_ids))
        if unknown:
            raise BrcRuleViolation(
                "LLM advisory event references unregistered strategy families: "
                + ", ".join(unknown)
            )


def format_feishu_advisory_message(
    *,
    event: LlmConsumableEvent,
    recommendation: LlmAdvisoryRecommendation,
) -> str:
    return format_feishu_advisory_markdown(event=event, recommendation=recommendation)


def _advisory_system_prompt(registered_strategy_family_ids: set[str]) -> str:
    return (
        "You are the BRC Owner Copilot advisory engine. Consume only the provided "
        "typed event and context packet. Return JSON only with keys: "
        "recommendation_type, summary, confidence, recommended_strategy_family_ids, "
        "observe_only_strategy_family_ids, reason_codes, risk_notes, missing_facts, "
        "research_idea_notes. You may recommend only registered strategy families: "
        f"{', '.join(sorted(registered_strategy_family_ids))}. Unknown ideas must "
        "go into research_idea_notes, not recommended_strategy_family_ids. Never "
        "authorize strategy execution, sizing, leverage, side override, order "
        "creation, execution intent creation, live trading, transfer, or withdrawal."
    )


def _registered_strategy_family_ids(catalog: StrategySemanticsCatalog) -> set[str]:
    result: set[str] = set()
    for binding in catalog.bindings:
        result.add(binding.strategy_family_id)
        result.add(binding.canonical_family_id)
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [str(value)]
    return [str(item) for item in value if str(item)]


def _enum_or_default(enum_type, value: Any, default):
    if value is None:
        return default
    try:
        return enum_type(str(value))
    except Exception:
        return default


def _count_by(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result
