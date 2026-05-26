"""Application service for Bounded Risk Campaign governance."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional, Protocol

from src.domain.bounded_risk_campaign import (
    BrcAttemptStatus,
    BrcCampaignStatus,
    BrcDecisionResult,
    BrcInvariantCheck,
    BrcNextCampaignEligibility,
    BrcNextEligibilityDecision,
    BrcOperatorAction,
    BrcOperatorActionLedger,
    BrcOperatorDecisionResult,
    BrcOperatorExecutionPlan,
    BrcOperatorIntentDraft,
    BrcOperatorPlanStep,
    BrcOperatorRunResult,
    BrcReviewPacket,
    BoundedRiskCampaign,
    CampaignAttempt,
    CampaignOutcome,
    MockPnlEvent,
    MockPnlSource,
    PlaybookSwitchDecision,
    RiskCapitalBucket,
    RiskChangeDirection,
    RiskEnvelope,
    default_playbook_catalog,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


class BrcCampaignRepositoryPort(Protocol):
    async def initialize(self) -> None:
        ...

    async def get_current_campaign(self) -> Optional[BoundedRiskCampaign]:
        ...

    async def get_latest_campaign(self) -> Optional[BoundedRiskCampaign]:
        ...

    async def save_campaign(self, campaign: BoundedRiskCampaign) -> BoundedRiskCampaign:
        ...

    async def append_switch_decision(
        self,
        decision: PlaybookSwitchDecision,
    ) -> PlaybookSwitchDecision:
        ...

    async def append_campaign_event(
        self,
        *,
        campaign_id: str,
        event_type: str,
        occurred_at_ms: int,
        symbol: Optional[str] = None,
        attempt_id: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ...

    async def append_mock_pnl_event(self, event: MockPnlEvent) -> MockPnlEvent:
        ...

    async def list_switch_decisions(self, campaign_id: str) -> list[PlaybookSwitchDecision]:
        ...

    async def list_campaign_events(self, campaign_id: str) -> list[dict[str, Any]]:
        ...

    async def list_mock_pnl_events(self, campaign_id: str) -> list[MockPnlEvent]:
        ...

    async def save_operator_action(
        self,
        action: BrcOperatorActionLedger,
    ) -> BrcOperatorActionLedger:
        ...

    async def get_operator_action(self, action_id: str) -> Optional[BrcOperatorActionLedger]:
        ...

    async def list_operator_actions(
        self,
        *,
        campaign_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[BrcOperatorActionLedger]:
        ...


class BrcRuleViolation(ValueError):
    """Raised when a BRC hard rule blocks a requested action."""


@dataclass(frozen=True)
class AttemptOpenRecord:
    intent_id: Optional[str]
    signal_id: Optional[str]
    amount: Decimal
    notional: Optional[Decimal]


@dataclass(frozen=True)
class AttemptCloseRecord:
    close_order_id: Optional[str]
    exchange_order_id: Optional[str]


class BoundedRiskCampaignService:
    """Coordinates BRC state without placing orders or touching account balances."""

    CONTROLLED_TESTNET_PLAYBOOK_ID = "PB-004-BRC-CONTROLLED-TESTNET"
    SYMBOL_SEQUENCE = ("ETH/USDT:USDT", "BTC/USDT:USDT")
    READ_ONLY_CONFIRMATION_PHRASE = "CONFIRM_READ_ONLY_BRC"

    def __init__(self, repository: BrcCampaignRepositoryPort) -> None:
        self._repo = repository
        self._catalog = default_playbook_catalog()

    async def initialize(self) -> None:
        await self._repo.initialize()

    async def create_campaign(
        self,
        *,
        bucket_id: str,
        authorized_amount: Decimal,
        max_campaign_loss: Decimal,
        profit_protect_trigger: Decimal,
        reason: str,
        currency: str = "USDT",
    ) -> BoundedRiskCampaign:
        existing = await self._repo.get_current_campaign()
        if existing is not None and existing.status != BrcCampaignStatus.ENDED:
            raise BrcRuleViolation(f"active BRC campaign already exists: {existing.campaign_id}")
        now = _now_ms()
        campaign = BoundedRiskCampaign(
            campaign_id=f"brc-{uuid.uuid4().hex[:12]}",
            bucket=RiskCapitalBucket(
                bucket_id=bucket_id,
                currency=currency,
                authorized_amount=authorized_amount,
                refill_allowed=False,
            ),
            risk_envelope=RiskEnvelope(
                max_campaign_loss=max_campaign_loss,
                profit_protect_trigger=profit_protect_trigger,
            ),
            current_playbook_id="PB-000-OBSERVE-ONLY",
            status=BrcCampaignStatus.OBSERVE,
            created_at_ms=now,
            updated_at_ms=now,
        )
        campaign = await self._repo.save_campaign(campaign)
        await self._repo.append_campaign_event(
            campaign_id=campaign.campaign_id,
            event_type="campaign_created",
            occurred_at_ms=now,
            reason=reason,
            metadata={
                "bucket_id": bucket_id,
                "authorized_amount": str(authorized_amount),
                "max_campaign_loss": str(max_campaign_loss),
                "profit_protect_trigger": str(profit_protect_trigger),
                "initial_playbook_id": campaign.current_playbook_id,
            },
        )
        return campaign

    async def get_current_campaign(self) -> Optional[BoundedRiskCampaign]:
        return await self._repo.get_current_campaign()

    async def get_latest_campaign(self) -> Optional[BoundedRiskCampaign]:
        getter = getattr(self._repo, "get_latest_campaign", None)
        if callable(getter):
            return await getter()
        return await self._repo.get_current_campaign()

    async def require_current_campaign(self) -> BoundedRiskCampaign:
        campaign = await self.get_current_campaign()
        if campaign is None:
            raise BrcRuleViolation("no active BRC campaign")
        return campaign

    async def require_latest_campaign(self) -> BoundedRiskCampaign:
        campaign = await self.get_latest_campaign()
        if campaign is None:
            raise BrcRuleViolation("no BRC campaign found")
        return campaign

    async def switch_playbook(
        self,
        *,
        new_playbook_id: str,
        reason_category: str,
        reason_text: str,
        evidence_refs: list[str],
        risk_change_direction: RiskChangeDirection = RiskChangeDirection.SAME_RISK,
    ) -> PlaybookSwitchDecision:
        campaign = await self.require_current_campaign()
        now = _now_ms()
        decision_result = BrcDecisionResult.ALLOWED
        blocked_reason = None

        if new_playbook_id not in self._catalog:
            decision_result = BrcDecisionResult.BLOCKED
            blocked_reason = f"unknown playbook: {new_playbook_id}"
        elif campaign.status == BrcCampaignStatus.LOSS_LOCKED:
            decision_result = BrcDecisionResult.BLOCKED
            blocked_reason = "loss_locked campaign cannot switch playbooks"
        elif (
            new_playbook_id == self.CONTROLLED_TESTNET_PLAYBOOK_ID
            and not self._catalog[new_playbook_id].allows_controlled_testnet
        ):
            decision_result = BrcDecisionResult.BLOCKED
            blocked_reason = "playbook is not allowed for controlled testnet"
        elif not evidence_refs:
            decision_result = BrcDecisionResult.REVIEW_REQUIRED
            blocked_reason = "evidence_refs required for playbook switch"

        decision = PlaybookSwitchDecision(
            switch_id=f"brc-switch-{uuid.uuid4().hex[:12]}",
            campaign_id=campaign.campaign_id,
            previous_playbook_id=campaign.current_playbook_id,
            new_playbook_id=new_playbook_id,
            switched_at_ms=now,
            reason_category=reason_category,
            reason_text=reason_text,
            evidence_refs=list(evidence_refs),
            risk_change_direction=risk_change_direction,
            campaign_pnl_at_switch=campaign.realized_pnl,
            attempt_count_at_switch=campaign.attempt_count,
            campaign_status_at_switch=campaign.status,
            decision_result=decision_result,
            blocked_reason=blocked_reason,
            inferred_fields={
                "loss_counter_reset": False,
                "campaign_pnl_carried": str(campaign.realized_pnl),
                "max_attempts": campaign.risk_envelope.max_attempts,
                "remaining_attempts": max(
                    campaign.risk_envelope.max_attempts - campaign.attempt_count,
                    0,
                ),
            },
        )
        await self._repo.append_switch_decision(decision)
        if decision_result != BrcDecisionResult.ALLOWED:
            return decision

        updated = campaign.model_copy(
            update={
                "current_playbook_id": new_playbook_id,
                "updated_at_ms": now,
            }
        )
        await self._repo.save_campaign(updated)
        await self._repo.append_campaign_event(
            campaign_id=updated.campaign_id,
            event_type="playbook_switched",
            occurred_at_ms=now,
            reason=reason_text,
            metadata={
                "from_playbook": campaign.current_playbook_id,
                "to_playbook": new_playbook_id,
                "decision_result": decision_result.value,
                "risk_change_direction": risk_change_direction.value,
            },
        )
        return decision

    async def arm_attempt(self, *, symbol: str, reason: str) -> CampaignAttempt:
        campaign = await self.require_current_campaign()
        self._ensure_can_attempt(campaign, symbol=symbol)
        now = _now_ms()
        attempt = CampaignAttempt(
            attempt_id=f"brc-attempt-{campaign.attempt_count + 1}",
            symbol=symbol,
            status=BrcAttemptStatus.ARMED,
            armed_at_ms=now,
        )
        updated = campaign.model_copy(
            update={
                "status": BrcCampaignStatus.ACTIVE,
                "attempt_count": campaign.attempt_count + 1,
                "attempts": [*campaign.attempts, attempt],
                "updated_at_ms": now,
            }
        )
        await self._repo.save_campaign(updated)
        await self._repo.append_campaign_event(
            campaign_id=updated.campaign_id,
            event_type="attempt_armed",
            occurred_at_ms=now,
            symbol=symbol,
            attempt_id=attempt.attempt_id,
            reason=reason,
            metadata={"attempt_count": updated.attempt_count},
        )
        return attempt

    async def record_attempt_entry(
        self,
        *,
        symbol: str,
        record: AttemptOpenRecord,
    ) -> CampaignAttempt:
        campaign = await self.require_current_campaign()
        index, attempt = self._require_last_attempt(campaign, symbol=symbol)
        if attempt.status != BrcAttemptStatus.ARMED:
            raise BrcRuleViolation(f"attempt must be armed before entry; got {attempt.status.value}")
        now = _now_ms()
        updated_attempt = attempt.model_copy(
            update={
                "status": BrcAttemptStatus.ENTRY_FILLED,
                "entry_at_ms": now,
                "intent_id": record.intent_id,
                "signal_id": record.signal_id,
                "amount": record.amount,
                "notional": record.notional,
            }
        )
        attempts = list(campaign.attempts)
        attempts[index] = updated_attempt
        await self._repo.save_campaign(campaign.model_copy(update={"attempts": attempts, "updated_at_ms": now}))
        await self._repo.append_campaign_event(
            campaign_id=campaign.campaign_id,
            event_type="attempt_entry_recorded",
            occurred_at_ms=now,
            symbol=symbol,
            attempt_id=attempt.attempt_id,
            metadata={
                "intent_id": record.intent_id,
                "signal_id": record.signal_id,
                "amount": str(record.amount),
                "notional": str(record.notional) if record.notional is not None else None,
            },
        )
        return updated_attempt

    async def record_attempt_close(
        self,
        *,
        symbol: str,
        record: AttemptCloseRecord,
    ) -> CampaignAttempt:
        campaign = await self.require_current_campaign()
        index, attempt = self._require_last_attempt(campaign, symbol=symbol)
        if attempt.status != BrcAttemptStatus.ENTRY_FILLED:
            raise BrcRuleViolation("attempt must have an entry before close")
        now = _now_ms()
        updated_attempt = attempt.model_copy(
            update={
                "status": BrcAttemptStatus.CLOSED,
                "closed_at_ms": now,
                "close_order_id": record.close_order_id,
                "exchange_order_id": record.exchange_order_id,
            }
        )
        attempts = list(campaign.attempts)
        attempts[index] = updated_attempt
        await self._repo.save_campaign(campaign.model_copy(update={"attempts": attempts, "updated_at_ms": now}))
        await self._repo.append_campaign_event(
            campaign_id=campaign.campaign_id,
            event_type="attempt_closed",
            occurred_at_ms=now,
            symbol=symbol,
            attempt_id=attempt.attempt_id,
            metadata={
                "close_order_id": record.close_order_id,
                "exchange_order_id": record.exchange_order_id,
            },
        )
        return updated_attempt

    async def inject_mock_pnl(
        self,
        *,
        amount: Decimal,
        source: MockPnlSource,
        reason: str,
    ) -> MockPnlEvent:
        campaign = await self.require_current_campaign()
        now = _now_ms()
        cumulative = campaign.realized_pnl + amount
        triggered_state: Optional[BrcCampaignStatus] = None
        status = campaign.status
        if cumulative <= -campaign.risk_envelope.max_campaign_loss:
            status = BrcCampaignStatus.LOSS_LOCKED
            triggered_state = BrcCampaignStatus.LOSS_LOCKED
        elif cumulative >= campaign.risk_envelope.profit_protect_trigger:
            status = BrcCampaignStatus.PROFIT_PROTECT
            triggered_state = BrcCampaignStatus.PROFIT_PROTECT

        event = MockPnlEvent(
            event_id=f"brc-mock-pnl-{uuid.uuid4().hex[:12]}",
            campaign_id=campaign.campaign_id,
            amount=amount,
            cumulative_pnl=cumulative,
            source=source,
            reason=reason,
            occurred_at_ms=now,
            triggered_state=triggered_state,
        )
        updated = campaign.model_copy(
            update={
                "realized_pnl": cumulative,
                "status": status,
                "updated_at_ms": now,
            }
        )
        await self._repo.save_campaign(updated)
        await self._repo.append_mock_pnl_event(event)
        await self._repo.append_campaign_event(
            campaign_id=campaign.campaign_id,
            event_type="mock_pnl_injected",
            occurred_at_ms=now,
            reason=reason,
            metadata={
                "amount": str(amount),
                "cumulative_pnl": str(cumulative),
                "source": source.value,
                "triggered_state": triggered_state.value if triggered_state else None,
                "exchange_balance_mutated": False,
                "daily_risk_mutated": False,
            },
        )
        return event

    async def finalize(
        self,
        *,
        outcome: CampaignOutcome,
        reason: str,
        final_flat: bool,
    ) -> BoundedRiskCampaign:
        campaign = await self.require_current_campaign()
        if not final_flat:
            raise BrcRuleViolation("cannot finalize BRC campaign until final inventory is flat")
        if outcome == CampaignOutcome.ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED:
            if campaign.status != BrcCampaignStatus.LOSS_LOCKED:
                raise BrcRuleViolation("loss-locked rehearsal outcome requires BRC loss_locked state")
            if campaign.attempt_count != campaign.risk_envelope.max_attempts:
                raise BrcRuleViolation("loss-locked rehearsal outcome requires two closed attempts")
            if any(attempt.status != BrcAttemptStatus.CLOSED for attempt in campaign.attempts):
                raise BrcRuleViolation("all BRC attempts must be closed before finalization")
        now = _now_ms()
        updated = campaign.model_copy(
            update={
                "status": BrcCampaignStatus.ENDED,
                "outcome": outcome,
                "finalized_at_ms": now,
                "updated_at_ms": now,
            }
        )
        await self._repo.save_campaign(updated)
        await self._repo.append_campaign_event(
            campaign_id=campaign.campaign_id,
            event_type="campaign_finalized",
            occurred_at_ms=now,
            reason=reason,
            metadata={"outcome": outcome.value, "final_flat": final_flat},
        )
        return updated

    async def build_evidence_packet(self) -> dict[str, Any]:
        campaign = await self.require_current_campaign()
        return await self._build_evidence_packet_for(campaign)

    async def build_latest_evidence_packet(self) -> dict[str, Any]:
        campaign = await self.require_latest_campaign()
        return await self._build_evidence_packet_for(campaign)

    async def build_review_packet(
        self,
        *,
        final_inventory: Optional[dict[str, Any]] = None,
    ) -> BrcReviewPacket:
        campaign = await self.require_latest_campaign()
        evidence = await self._build_evidence_packet_for(campaign)
        if final_inventory is not None:
            evidence["final_inventory"] = final_inventory
        switches = evidence["switch_decisions"]
        mock_pnl_events = evidence["mock_pnl_events"]
        profit_protect_triggered = any(
            event.get("triggered_state") == BrcCampaignStatus.PROFIT_PROTECT.value
            for event in mock_pnl_events
        )
        loss_lock_triggered = campaign.status == BrcCampaignStatus.LOSS_LOCKED or any(
            event.get("triggered_state") == BrcCampaignStatus.LOSS_LOCKED.value
            for event in mock_pnl_events
        )
        all_attempts_closed = all(
            attempt.status == BrcAttemptStatus.CLOSED for attempt in campaign.attempts
        )
        final_inventory_flat = None
        if final_inventory is not None:
            final_inventory_flat = bool(final_inventory.get("all_flat"))
        invariant_checks = self._build_invariant_checks(
            campaign=campaign,
            switch_decisions=switches,
            final_inventory_flat=final_inventory_flat,
        )
        return BrcReviewPacket(
            campaign_id=campaign.campaign_id,
            status=campaign.status,
            outcome=campaign.outcome,
            current_playbook_id=campaign.current_playbook_id,
            realized_pnl=campaign.realized_pnl,
            authorized_amount=campaign.bucket.authorized_amount,
            max_campaign_loss=campaign.risk_envelope.max_campaign_loss,
            profit_protect_trigger=campaign.risk_envelope.profit_protect_trigger,
            attempt_count=campaign.attempt_count,
            max_attempts=campaign.risk_envelope.max_attempts,
            switch_count=len(switches),
            mock_pnl_event_count=len(mock_pnl_events),
            profit_protect_triggered=profit_protect_triggered,
            loss_lock_triggered=loss_lock_triggered,
            all_attempts_closed=all_attempts_closed,
            final_inventory_flat=final_inventory_flat,
            invariant_checks=invariant_checks,
            evidence=evidence,
        )

    def draft_operator_intent(self, *, source_text: str) -> BrcOperatorIntentDraft:
        normalized = source_text.strip().lower()
        if not normalized:
            raise BrcRuleViolation("operator intent text is required")

        if any(token in normalized for token in ("review", "复盘", "报告", "packet")):
            return BrcOperatorIntentDraft(
                source_text=source_text,
                action=BrcOperatorAction.READ_REVIEW_PACKET,
                confidence=Decimal("0.90"),
                endpoint_path="/api/runtime/test/brc/review-packet",
                executable_without_owner_confirmation=True,
            )
        if any(
            token in normalized
            for token in ("eligibility", "eligible", "下一轮", "下轮", "能不能", "是否可以")
        ):
            return BrcOperatorIntentDraft(
                source_text=source_text,
                action=BrcOperatorAction.READ_NEXT_ELIGIBILITY,
                confidence=Decimal("0.88"),
                endpoint_path="/api/runtime/test/brc/next-eligibility",
                executable_without_owner_confirmation=True,
            )
        if any(token in normalized for token in ("evidence", "证据", "验收", "evidence packet")):
            return BrcOperatorIntentDraft(
                source_text=source_text,
                action=BrcOperatorAction.READ_EVIDENCE,
                confidence=Decimal("0.86"),
                endpoint_path="/api/runtime/test/brc/evidence",
                executable_without_owner_confirmation=True,
            )
        return BrcOperatorIntentDraft(
            source_text=source_text,
            action=BrcOperatorAction.UNKNOWN,
            confidence=Decimal("0"),
            blocked_reason=(
                "unrecognized BRC operator intent; R2 only drafts read-only "
                "review, eligibility, and evidence actions"
            ),
        )

    def build_operator_execution_plan(
        self,
        *,
        source_text: str,
    ) -> BrcOperatorExecutionPlan:
        draft = self.draft_operator_intent(source_text=source_text)
        if draft.action == BrcOperatorAction.UNKNOWN or draft.endpoint_path is None:
            return BrcOperatorExecutionPlan(
                plan_id=f"brc-plan-{uuid.uuid4().hex[:12]}",
                source_text=source_text,
                draft=draft,
                steps=[],
                executable=False,
                confirmation_phrase=self.READ_ONLY_CONFIRMATION_PHRASE,
                blocked_reason=draft.blocked_reason or "operator action is not executable",
            )
        if draft.mutation_intended:
            return BrcOperatorExecutionPlan(
                plan_id=f"brc-plan-{uuid.uuid4().hex[:12]}",
                source_text=source_text,
                draft=draft,
                steps=[],
                executable=False,
                confirmation_phrase=self.READ_ONLY_CONFIRMATION_PHRASE,
                blocked_reason="BRC-R2 runner allows read-only actions only",
            )
        step = BrcOperatorPlanStep(
            step_id="step-1",
            action=draft.action,
            http_method=draft.http_method,
            endpoint_path=draft.endpoint_path,
            mutation_intended=False,
            owner_confirmation_required=True,
        )
        return BrcOperatorExecutionPlan(
            plan_id=f"brc-plan-{uuid.uuid4().hex[:12]}",
            source_text=source_text,
            draft=draft,
            steps=[step],
            executable=True,
            confirmation_phrase=self.READ_ONLY_CONFIRMATION_PHRASE,
        )

    async def create_operator_action_plan(
        self,
        *,
        source_text: str,
    ) -> BrcOperatorActionLedger:
        plan = self.build_operator_execution_plan(source_text=source_text)
        campaign = await self.get_latest_campaign()
        now = _now_ms()
        action = BrcOperatorActionLedger(
            action_id=f"brc-op-{uuid.uuid4().hex[:12]}",
            campaign_id=campaign.campaign_id if campaign is not None else None,
            plan_id=plan.plan_id,
            source_text=source_text,
            draft_action=plan.draft.action,
            http_method=plan.steps[0].http_method if plan.steps else plan.draft.http_method,
            endpoint_path=plan.steps[0].endpoint_path if plan.steps else plan.draft.endpoint_path,
            executable=plan.executable,
            confirmation_phrase_id=self.READ_ONLY_CONFIRMATION_PHRASE,
            confirmation_required=True,
            confirmation_matched=False,
            confirmed_by=None,
            decision_result=(
                BrcOperatorDecisionResult.PLANNED
                if plan.executable
                else BrcOperatorDecisionResult.BLOCKED
            ),
            blocked_reason=plan.blocked_reason,
            plan_json=plan.model_dump(mode="json"),
            created_at_ms=now,
        )
        return await self._repo.save_operator_action(action)

    async def get_operator_action(self, action_id: str) -> Optional[BrcOperatorActionLedger]:
        return await self._repo.get_operator_action(action_id)

    async def list_operator_actions(
        self,
        *,
        campaign_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[BrcOperatorActionLedger]:
        return await self._repo.list_operator_actions(campaign_id=campaign_id, limit=limit)

    async def run_operator_read_action(
        self,
        *,
        source_text: str,
        confirmation_phrase: str,
        final_inventory: Optional[dict[str, Any]] = None,
    ) -> BrcOperatorRunResult:
        action = await self.create_operator_action_plan(source_text=source_text)
        return await self.run_operator_action_by_id(
            action_id=action.action_id,
            confirmation_phrase=confirmation_phrase,
            final_inventory=final_inventory,
        )

    async def run_operator_action_by_id(
        self,
        *,
        action_id: str,
        confirmation_phrase: str,
        final_inventory: Optional[dict[str, Any]] = None,
        confirmed_by: str = "owner",
    ) -> BrcOperatorRunResult:
        action_record = await self._repo.get_operator_action(action_id)
        if action_record is None:
            raise BrcRuleViolation(f"unknown BRC operator action: {action_id}")
        plan = BrcOperatorExecutionPlan.model_validate(action_record.plan_json)
        now = _now_ms()
        if not plan.executable:
            blocked = action_record.model_copy(
                update={
                    "decision_result": BrcOperatorDecisionResult.BLOCKED,
                    "blocked_reason": plan.blocked_reason or "operator plan is blocked",
                    "confirmed_by": confirmed_by,
                    "executed_at_ms": now,
                }
            )
            await self._repo.save_operator_action(blocked)
            raise BrcRuleViolation(blocked.blocked_reason or "operator plan is blocked")
        if confirmation_phrase != self.READ_ONLY_CONFIRMATION_PHRASE:
            blocked = action_record.model_copy(
                update={
                    "decision_result": BrcOperatorDecisionResult.BLOCKED,
                    "blocked_reason": "Owner confirmation phrase mismatch",
                    "confirmation_matched": False,
                    "confirmed_by": confirmed_by,
                    "executed_at_ms": now,
                }
            )
            await self._repo.save_operator_action(blocked)
            raise BrcRuleViolation("Owner confirmation phrase mismatch")

        action = plan.draft.action
        if action == BrcOperatorAction.READ_REVIEW_PACKET:
            packet = await self.build_review_packet(final_inventory=final_inventory)
            result = {"review_packet": packet.model_dump(mode="json")}
        elif action == BrcOperatorAction.READ_NEXT_ELIGIBILITY:
            eligibility = await self.evaluate_next_campaign_eligibility(
                final_inventory=final_inventory,
            )
            result = {"eligibility": eligibility.model_dump(mode="json")}
        elif action == BrcOperatorAction.READ_EVIDENCE:
            evidence = await self.build_latest_evidence_packet()
            if final_inventory is not None:
                evidence["final_inventory"] = final_inventory
            result = {"evidence": evidence}
        else:
            raise BrcRuleViolation(f"unsupported BRC operator action: {action.value}")

        run_result = BrcOperatorRunResult(
            plan=plan,
            executed=True,
            action=action,
            result=result,
        )
        result_summary = {
            "action": action.value,
            "result_keys": sorted(result.keys()),
            "mutation_executed": False,
            "withdrawal_executed": False,
            "live_ready": False,
        }
        executed = action_record.model_copy(
            update={
                "decision_result": BrcOperatorDecisionResult.EXECUTED,
                "confirmation_matched": True,
                "confirmed_by": confirmed_by,
                "result_json": run_result.model_dump(mode="json"),
                "result_summary_json": result_summary,
                "mutation_executed": False,
                "withdrawal_executed": False,
                "live_ready": False,
                "executed_at_ms": now,
            }
        )
        await self._repo.save_operator_action(executed)
        return run_result

    async def evaluate_next_campaign_eligibility(
        self,
        *,
        final_inventory: Optional[dict[str, Any]] = None,
    ) -> BrcNextCampaignEligibility:
        campaign = await self.get_latest_campaign()
        if campaign is None:
            return BrcNextCampaignEligibility(
                decision=BrcNextEligibilityDecision.OBSERVE_ONLY,
                reason="no prior BRC campaign; start in observe-only until Owner authorizes a bounded risk bucket",
                owner_review_required=True,
                next_campaign_allowed=False,
                required_actions=[
                    "review or create a risk capital bucket",
                    "Owner must authorize the next campaign envelope",
                    "start from PB-000-OBSERVE-ONLY",
                ],
            )

        if final_inventory is not None and not bool(final_inventory.get("all_flat")):
            return BrcNextCampaignEligibility(
                decision=BrcNextEligibilityDecision.BLOCKED,
                reason="final inventory is not flat",
                campaign_id=campaign.campaign_id,
                latest_status=campaign.status,
                latest_outcome=campaign.outcome,
                blocked_reasons=["final ETH/BTC inventory is not flat"],
                required_actions=["restore flat inventory before any next campaign review"],
            )

        if campaign.status != BrcCampaignStatus.ENDED:
            return BrcNextCampaignEligibility(
                decision=BrcNextEligibilityDecision.BLOCKED,
                reason="current BRC campaign is still open",
                campaign_id=campaign.campaign_id,
                latest_status=campaign.status,
                latest_outcome=campaign.outcome,
                blocked_reasons=["open campaign must be finalized or manually stopped first"],
                required_actions=[
                    "complete current campaign review packet",
                    "finalize or manually stop the current campaign",
                ],
            )

        if campaign.outcome == CampaignOutcome.ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED:
            return BrcNextCampaignEligibility(
                decision=BrcNextEligibilityDecision.OWNER_REVIEW_REQUIRED,
                reason="latest BRC ended through loss-lock rehearsal; next campaign requires Owner review and a fresh risk bucket decision",
                campaign_id=campaign.campaign_id,
                latest_status=campaign.status,
                latest_outcome=campaign.outcome,
                owner_review_required=True,
                cooldown_required=True,
                next_campaign_allowed=False,
                required_actions=[
                    "review loss-lock evidence packet",
                    "confirm no refill of the same risk bucket",
                    "authorize a new campaign envelope before any next testnet attempt",
                ],
            )

        return BrcNextCampaignEligibility(
            decision=BrcNextEligibilityDecision.OWNER_REVIEW_REQUIRED,
            reason="latest BRC campaign ended; next campaign requires explicit Owner review",
            campaign_id=campaign.campaign_id,
            latest_status=campaign.status,
            latest_outcome=campaign.outcome,
            owner_review_required=True,
            next_campaign_allowed=False,
            required_actions=[
                "review final campaign outcome",
                "confirm next campaign risk bucket and playbook",
            ],
        )

    async def _build_evidence_packet_for(
        self,
        campaign: BoundedRiskCampaign,
    ) -> dict[str, Any]:
        switches = await self._repo.list_switch_decisions(campaign.campaign_id)
        events = await self._repo.list_campaign_events(campaign.campaign_id)
        mock_pnl_events = await self._repo.list_mock_pnl_events(campaign.campaign_id)
        return {
            "campaign": campaign.model_dump(mode="json"),
            "playbook_catalog": {
                key: value.model_dump(mode="json") for key, value in self._catalog.items()
            },
            "switch_decisions": [decision.model_dump(mode="json") for decision in switches],
            "campaign_events": events,
            "mock_pnl_events": [event.model_dump(mode="json") for event in mock_pnl_events],
            "invariants": {
                "mock_pnl_exchange_balance_mutated": False,
                "mock_pnl_daily_risk_mutated": False,
                "loss_counter_reset_on_switch": False,
                "program_withdrawal_enabled": False,
                "real_live_enabled": False,
            },
        }

    @staticmethod
    def _build_invariant_checks(
        *,
        campaign: BoundedRiskCampaign,
        switch_decisions: list[dict[str, Any]],
        final_inventory_flat: Optional[bool],
    ) -> list[BrcInvariantCheck]:
        active_attempts = [
            attempt
            for attempt in campaign.attempts
            if attempt.status in {BrcAttemptStatus.ARMED, BrcAttemptStatus.ENTRY_FILLED}
        ]
        checks = [
            BrcInvariantCheck(
                name="attempt_count_within_risk_envelope",
                passed=campaign.attempt_count <= campaign.risk_envelope.max_attempts,
                detail=f"{campaign.attempt_count}/{campaign.risk_envelope.max_attempts}",
            ),
            BrcInvariantCheck(
                name="max_one_active_attempt",
                passed=len(active_attempts) <= campaign.risk_envelope.max_simultaneous_positions,
                detail=f"active_attempts={len(active_attempts)}",
            ),
            BrcInvariantCheck(
                name="loss_counter_not_reset_on_switch",
                passed=all(
                    decision.get("inferred_fields", {}).get("loss_counter_reset") is False
                    for decision in switch_decisions
                ),
                detail="switch decisions preserve campaign pnl continuity",
            ),
            BrcInvariantCheck(
                name="program_withdrawal_disabled",
                passed=True,
                detail="BRC evidence only; no withdrawal or transfer endpoint is enabled",
            ),
            BrcInvariantCheck(
                name="real_live_disabled",
                passed=True,
                detail="real live remains unauthorized and outside BRC R2",
            ),
        ]
        if campaign.status == BrcCampaignStatus.ENDED:
            checks.append(
                BrcInvariantCheck(
                    name="ended_campaign_attempts_closed",
                    passed=all(
                        attempt.status == BrcAttemptStatus.CLOSED
                        for attempt in campaign.attempts
                    ),
                    detail="ended campaigns must not keep active BRC attempts",
                )
            )
        if final_inventory_flat is not None:
            checks.append(
                BrcInvariantCheck(
                    name="final_inventory_flat",
                    passed=final_inventory_flat,
                    detail=f"final_inventory.all_flat={final_inventory_flat}",
                )
            )
        return checks

    def _ensure_can_attempt(self, campaign: BoundedRiskCampaign, *, symbol: str) -> None:
        if campaign.current_playbook_id != self.CONTROLLED_TESTNET_PLAYBOOK_ID:
            raise BrcRuleViolation("controlled testnet attempt requires PB-004-BRC-CONTROLLED-TESTNET")
        if campaign.status == BrcCampaignStatus.LOSS_LOCKED:
            raise BrcRuleViolation("loss_locked campaign blocks new attempts")
        if campaign.attempt_count >= campaign.risk_envelope.max_attempts:
            raise BrcRuleViolation("risk envelope blocks third attempt")
        if symbol not in campaign.risk_envelope.allowed_symbols:
            raise BrcRuleViolation(f"symbol not allowed by risk envelope: {symbol}")
        expected = self.SYMBOL_SEQUENCE[campaign.attempt_count]
        if symbol != expected:
            raise BrcRuleViolation(f"BRC sequence requires {expected} before {symbol}")
        last_attempt = campaign.last_attempt
        if last_attempt is not None and last_attempt.status != BrcAttemptStatus.CLOSED:
            raise BrcRuleViolation("previous BRC attempt must be closed before arming the next one")

    @staticmethod
    def _require_last_attempt(
        campaign: BoundedRiskCampaign,
        *,
        symbol: str,
    ) -> tuple[int, CampaignAttempt]:
        if not campaign.attempts:
            raise BrcRuleViolation("no armed BRC attempt")
        index = len(campaign.attempts) - 1
        attempt = campaign.attempts[index]
        if attempt.symbol != symbol:
            raise BrcRuleViolation(f"last BRC attempt is for {attempt.symbol}, not {symbol}")
        return index, attempt
