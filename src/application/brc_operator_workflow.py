"""LangGraph-shaped BRC LLM operator workflow.

LangGraph is an orchestration/checkpointing dependency only. BRC PG ledgers
remain the durable fact source and the BRC service remains the policy boundary.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional, Protocol

import aiohttp
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.bounded_risk_campaign_service import (
    BoundedRiskCampaignService,
    BrcRuleViolation,
)
from src.domain.bounded_risk_campaign import (
    BrcLlmIntent,
    BrcLlmIntentAction,
    BrcOperatorDecisionResult,
    BrcWorkflowRun,
    BrcWorkflowStatus,
)


READ_ONLY_CONFIRMATION = "CONFIRM_READ_ONLY_BRC"
TESTNET_REHEARSAL_CONFIRMATION = "CONFIRM_BRC_TESTNET_REHEARSAL"
PROMPT_VERSION = "brc_llm_operator_v1"
WORKFLOW_NODE_NAMES = [
    "parse_owner_text",
    "validate_policy",
    "persist_llm_intent",
    "build_action_plan",
    "wait_owner_confirmation",
    "execute_allowed_action",
    "persist_result",
    "build_next_gate",
]
TESTNET_REHEARSAL_SOURCE_TOKENS = (
    "testnet",
    "test net",
    "rehearsal",
    "测试网",
    "演练",
    "彩排",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _compile_langgraph_workflow() -> Optional[Any]:
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    def _pass_through(state: dict[str, Any]) -> dict[str, Any]:
        return state

    graph = StateGraph(dict)
    for node_name in WORKFLOW_NODE_NAMES:
        graph.add_node(node_name, _pass_through)
    graph.set_entry_point(WORKFLOW_NODE_NAMES[0])
    for index, node_name in enumerate(WORKFLOW_NODE_NAMES[:-1]):
        graph.add_edge(node_name, WORKFLOW_NODE_NAMES[index + 1])
    graph.add_edge(WORKFLOW_NODE_NAMES[-1], END)
    return graph.compile()


class BrcLlmProvider(Protocol):
    provider_name: str
    model_name: Optional[str]

    async def classify(self, *, source_text: str) -> dict[str, Any]:
        ...


class BrcTestnetRehearsalWorkflowResult(BaseModel):
    """Validated result envelope for the fixed BRC testnet rehearsal executor."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(min_length=1)
    final_inventory: dict[str, Any]
    workflow_run_id: Optional[str] = None
    confirmation_phrase_id: Optional[str] = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    evidence: Optional[dict[str, Any]] = None
    review_artifact: Optional[dict[str, Any]] = None
    review_outcome: Optional[dict[str, Any]] = None
    mutation_executed: bool = True
    withdrawal_executed: bool = False
    live_ready: bool = False

    @model_validator(mode="after")
    def _validate_testnet_rehearsal_boundary(self) -> "BrcTestnetRehearsalWorkflowResult":
        if not bool(self.final_inventory.get("all_flat")):
            raise ValueError("BRC testnet rehearsal result requires final flat inventory")
        if not self.mutation_executed:
            raise ValueError("BRC testnet rehearsal result must record testnet mutation execution")
        if self.withdrawal_executed:
            raise ValueError("BRC testnet rehearsal result cannot execute withdrawals")
        if self.live_ready:
            raise ValueError("BRC testnet rehearsal result is never live-ready")
        return self


@dataclass(frozen=True)
class OpenAICompatibleBrcLlmProvider:
    """Minimal OpenAI-compatible chat completions adapter using env config."""

    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: int = 20
    provider_name: str = "openai_compatible"

    @classmethod
    def from_env(cls) -> "OpenAICompatibleBrcLlmProvider":
        if os.getenv("BRC_LLM_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise BrcRuleViolation("BRC LLM provider disabled")
        base_url = os.getenv("BRC_LLM_BASE_URL", "").strip()
        api_key = os.getenv("BRC_LLM_API_KEY", "").strip()
        model = os.getenv("BRC_LLM_MODEL", "").strip()
        if not base_url or not api_key or not model:
            raise BrcRuleViolation("BRC LLM provider env is incomplete")
        timeout = int(os.getenv("BRC_LLM_TIMEOUT_SECONDS", "20"))
        return cls(base_url=base_url, api_key=api_key, model_name=model, timeout_seconds=timeout)

    async def classify(self, *, source_text: str) -> dict[str, Any]:
        url = self.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions" if url.endswith("/v1") else f"{url}/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": source_text},
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
                    raise BrcRuleViolation(f"BRC LLM provider failed with HTTP {response.status}")
        parsed = json.loads(text)
        content = parsed["choices"][0]["message"]["content"]
        return json.loads(content)


def _system_prompt() -> str:
    return (
        "Classify Owner text for a Bounded Risk Campaign operator gateway. "
        "Return JSON only with keys action, confidence, reason_text. Allowed "
        "actions: read_review_artifact, read_next_eligibility, read_evidence, "
        "request_testnet_rehearsal, unknown. Never choose live/mainnet, "
        "withdrawal, transfer, strategy execution, autonomous order, sizing, "
        "leverage, side, or symbol override."
    )


class BrcOperatorWorkflow:
    """BRC R3 operator workflow with optional LangGraph checkpoint support."""

    def __init__(
        self,
        *,
        campaign_service: BoundedRiskCampaignService,
        provider: Optional[BrcLlmProvider] = None,
    ) -> None:
        self._campaign_service = campaign_service
        self._provider = provider
        self._langgraph_app = _compile_langgraph_workflow()
        self.langgraph_available = self._langgraph_app is not None

    async def create_workflow(self, *, source_text: str) -> BrcWorkflowRun:
        source_text = source_text.strip()
        if not source_text:
            raise BrcRuleViolation("BRC LLM workflow source text is required")
        workflow_run_id = f"brc-wf-{uuid.uuid4().hex[:12]}"
        now = _now_ms()
        blocked_reason = self._forbidden_text_reason(source_text)
        provider_name = "policy_precheck"
        model_name = None
        action = BrcLlmIntentAction.UNKNOWN
        confidence = Decimal("0")
        reason_text = blocked_reason or "pending LLM classification"
        raw_summary: dict[str, Any] = {
            "langgraph_available": self.langgraph_available,
            "raw_output_persisted": False,
        }

        if blocked_reason is None:
            try:
                provider = self._provider or OpenAICompatibleBrcLlmProvider.from_env()
                provider_name = provider.provider_name
                model_name = provider.model_name
                llm_payload = await provider.classify(source_text=source_text)
                action = BrcLlmIntentAction(str(llm_payload.get("action", "unknown")))
                confidence = Decimal(str(llm_payload.get("confidence", "0")))
                reason_text = str(llm_payload.get("reason_text") or "LLM classified Owner text")
                raw_summary.update(
                    {
                        "keys": sorted(str(key) for key in llm_payload.keys()),
                        "action": action.value,
                        "confidence": str(confidence),
                    }
                )
                blocked_reason = self._policy_block_reason(action=action, source_text=source_text)
            except Exception as exc:
                blocked_reason = str(exc)
                provider_name = provider_name or "openai_compatible"
                action = BrcLlmIntentAction.UNKNOWN
                confidence = Decimal("0")
                reason_text = "LLM classification failed"

        decision_result = (
            BrcOperatorDecisionResult.BLOCKED
            if blocked_reason or action == BrcLlmIntentAction.UNKNOWN
            else BrcOperatorDecisionResult.PLANNED
        )
        if action == BrcLlmIntentAction.UNKNOWN and blocked_reason is None:
            blocked_reason = "BRC LLM intent is unknown"

        intent = BrcLlmIntent(
            intent_id=f"brc-llm-{uuid.uuid4().hex[:12]}",
            workflow_run_id=workflow_run_id,
            source_text=source_text,
            action=action,
            confidence=confidence,
            reason_text=reason_text,
            provider_name=provider_name,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            raw_response_summary=raw_summary,
            decision_result=decision_result,
            blocked_reason=blocked_reason,
            created_at_ms=now,
        )
        await self._campaign_service.save_llm_intent(intent)
        run = BrcWorkflowRun(
            workflow_run_id=workflow_run_id,
            llm_intent_id=intent.intent_id,
            source_text=source_text,
            action=action,
            status=(
                BrcWorkflowStatus.BLOCKED
                if decision_result == BrcOperatorDecisionResult.BLOCKED
                else BrcWorkflowStatus.AWAITING_CONFIRMATION
            ),
            confirmation_phrase_id=self._confirmation_phrase(action),
            confirmation_required=True,
            blocked_reason=blocked_reason,
            workflow_state_json={
                "nodes": WORKFLOW_NODE_NAMES,
                "langgraph_available": self.langgraph_available,
                "fact_source": "brc_pg_tables",
            },
            langgraph_checkpoint_ref=f"thread:{workflow_run_id}",
            created_at_ms=now,
            updated_at_ms=now,
            completed_at_ms=now if decision_result == BrcOperatorDecisionResult.BLOCKED else None,
        )
        return await self._campaign_service.save_workflow_run(run)

    async def get_workflow(self, workflow_run_id: str) -> Optional[BrcWorkflowRun]:
        return await self._campaign_service.get_workflow_run(workflow_run_id)

    async def get_intent(self, intent_id: str) -> Optional[BrcLlmIntent]:
        return await self._campaign_service.get_llm_intent(intent_id)

    async def list_workflows(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[BrcWorkflowRun]:
        return await self._campaign_service.list_workflow_runs(limit=limit, status=status)

    async def confirm_workflow(
        self,
        *,
        workflow_run_id: str,
        confirmation_phrase: str,
        confirmed_by: str,
        final_inventory: Optional[dict[str, Any]] = None,
        testnet_rehearsal_executor: Optional[Callable[[str], Awaitable[dict[str, Any]]]] = None,
    ) -> BrcWorkflowRun:
        run = await self._campaign_service.get_workflow_run(workflow_run_id)
        if run is None:
            raise BrcRuleViolation(f"unknown BRC workflow: {workflow_run_id}")
        now = _now_ms()
        if run.status != BrcWorkflowStatus.AWAITING_CONFIRMATION:
            raise BrcRuleViolation(f"BRC workflow is already {run.status.value}")
        if confirmation_phrase != run.confirmation_phrase_id:
            blocked = run.model_copy(
                update={
                    "status": BrcWorkflowStatus.BLOCKED,
                    "blocked_reason": "Owner confirmation phrase mismatch",
                    "confirmation_matched": False,
                    "confirmed_by": confirmed_by,
                    "updated_at_ms": now,
                    "completed_at_ms": now,
                }
            )
            await self._campaign_service.save_workflow_run(blocked)
            raise BrcRuleViolation("Owner confirmation phrase mismatch")

        running = run.model_copy(
            update={
                "status": BrcWorkflowStatus.RUNNING,
                "confirmation_matched": True,
                "confirmed_by": confirmed_by,
                "updated_at_ms": now,
            }
        )
        await self._campaign_service.save_workflow_run(running)
        try:
            result = await self._execute_action(
                run=running,
                final_inventory=final_inventory,
                testnet_rehearsal_executor=testnet_rehearsal_executor,
            )
        except Exception as exc:
            failed = running.model_copy(
                update={
                    "status": BrcWorkflowStatus.FAILED,
                    "blocked_reason": str(exc),
                    "updated_at_ms": _now_ms(),
                    "completed_at_ms": _now_ms(),
                }
            )
            await self._campaign_service.save_workflow_run(failed)
            raise

        completed_at = _now_ms()
        completed = running.model_copy(
            update={
                "status": BrcWorkflowStatus.COMPLETED,
                "result_json": result,
                "result_summary_json": {
                    "action": running.action.value,
                    "result_keys": sorted(result.keys()),
                    "mutation_executed": running.action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL,
                    "withdrawal_executed": False,
                    "live_ready": False,
                },
                "mutation_executed": running.action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL,
                "withdrawal_executed": False,
                "live_ready": False,
                "updated_at_ms": completed_at,
                "completed_at_ms": completed_at,
            }
        )
        return await self._campaign_service.save_workflow_run(completed)

    async def _execute_action(
        self,
        *,
        run: BrcWorkflowRun,
        final_inventory: Optional[dict[str, Any]],
        testnet_rehearsal_executor: Optional[Callable[[str], Awaitable[dict[str, Any]]]],
    ) -> dict[str, Any]:
        if run.action == BrcLlmIntentAction.READ_REVIEW_ARTIFACT:
            artifact = await self._campaign_service.build_review_artifact(final_inventory=final_inventory)
            return {"review_artifact": artifact.model_dump(mode="json")}
        if run.action == BrcLlmIntentAction.READ_NEXT_ELIGIBILITY:
            eligibility = await self._campaign_service.evaluate_next_campaign_eligibility(
                final_inventory=final_inventory,
            )
            return {"eligibility": eligibility.model_dump(mode="json")}
        if run.action == BrcLlmIntentAction.READ_EVIDENCE:
            evidence = await self._campaign_service.build_latest_evidence_artifact()
            if final_inventory is not None:
                evidence["final_inventory"] = final_inventory
            return {"evidence": evidence}
        if run.action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL:
            if testnet_rehearsal_executor is None:
                raise BrcRuleViolation("BRC testnet rehearsal executor unavailable")
            result = await testnet_rehearsal_executor(run.workflow_run_id)
            try:
                validated = BrcTestnetRehearsalWorkflowResult.model_validate(result)
            except Exception as exc:
                raise BrcRuleViolation(
                    f"invalid BRC testnet rehearsal result: {exc}"
                ) from exc
            if (
                validated.workflow_run_id is not None
                and validated.workflow_run_id != run.workflow_run_id
            ):
                raise BrcRuleViolation("BRC testnet rehearsal result workflow id mismatch")
            return validated.model_dump(mode="json")
        raise BrcRuleViolation(f"unsupported BRC LLM workflow action: {run.action.value}")

    @staticmethod
    def _confirmation_phrase(action: BrcLlmIntentAction) -> str:
        if action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL:
            return TESTNET_REHEARSAL_CONFIRMATION
        return READ_ONLY_CONFIRMATION

    @staticmethod
    def _forbidden_text_reason(source_text: str) -> Optional[str]:
        normalized = source_text.lower()
        forbidden_tokens = (
            "mainnet",
            "real live",
            "实盘",
            "主网",
            "提现",
            "withdraw",
            "transfer",
            "转账",
            "leverage",
            "杠杆",
            "all in",
            "自动下单",
            "自动交易",
        )
        for token in forbidden_tokens:
            if token in normalized:
                return f"BRC LLM workflow blocks forbidden intent token: {token}"
        return None

    @staticmethod
    def _policy_block_reason(*, action: BrcLlmIntentAction, source_text: str) -> Optional[str]:
        if action == BrcLlmIntentAction.UNKNOWN:
            return "BRC LLM intent is unknown"
        if action not in {
            BrcLlmIntentAction.READ_REVIEW_ARTIFACT,
            BrcLlmIntentAction.READ_NEXT_ELIGIBILITY,
            BrcLlmIntentAction.READ_EVIDENCE,
            BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL,
        }:
            return f"BRC LLM action is not allowed: {action.value}"
        if (
            action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL
            and not BrcOperatorWorkflow._source_explicitly_requests_testnet_rehearsal(source_text)
        ):
            return (
                "BRC testnet rehearsal intent requires explicit Owner text "
                "mentioning testnet/rehearsal"
            )
        return BrcOperatorWorkflow._forbidden_text_reason(source_text)

    @staticmethod
    def _source_explicitly_requests_testnet_rehearsal(source_text: str) -> bool:
        normalized = source_text.lower()
        return any(token in normalized for token in TESTNET_REHEARSAL_SOURCE_TOKENS)
