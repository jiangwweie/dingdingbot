"""Durable runtime campaign state gate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Optional

from src.infrastructure.logger import logger
from src.infrastructure.repository_ports import (
    CampaignStateSnapshot,
    CampaignStateTransitionLog,
)


CAMPAIGN_STATE_BLOCK_REASON = "CAMPAIGN_STATE_NOT_ARMED"
CAMPAIGN_STATE_SCOPE_KEY = "runtime:default"


class CampaignRuntimeState(str, Enum):
    OBSERVE = "observe"
    ARMED = "armed"
    PAUSED = "paused"
    PROFIT_PROTECT = "profit_protect"
    LOSS_LOCKED = "loss_locked"
    HARD_LOCKED = "hard_locked"
    CLOSED = "closed"


class CampaignRuntimeEvent(str, Enum):
    ENTRY_FILLED = "entry_filled"
    PROFIT_PROTECT_TRIGGERED = "profit_protect_triggered"
    STOP_LOSS_FILLED = "stop_loss_filled"
    POSITION_CLOSED = "position_closed"
    RISK_CRITICAL = "risk_critical"


class CampaignTransitionTrigger(str, Enum):
    NOOP = "noop"
    OWNER_ARM = "owner_arm"
    OWNER_PAUSE = "owner_pause"
    OWNER_RESUME = "owner_resume"
    OWNER_REVIEW_RESET = "owner_review_reset"
    OWNER_HARD_LOCK = "owner_hard_lock"
    ENTRY_FILLED = CampaignRuntimeEvent.ENTRY_FILLED.value
    PROFIT_PROTECT_TRIGGERED = CampaignRuntimeEvent.PROFIT_PROTECT_TRIGGERED.value
    STOP_LOSS_FILLED = CampaignRuntimeEvent.STOP_LOSS_FILLED.value
    POSITION_CLOSED = CampaignRuntimeEvent.POSITION_CLOSED.value
    RISK_CRITICAL = CampaignRuntimeEvent.RISK_CRITICAL.value


@dataclass(frozen=True)
class CampaignTransitionRule:
    current_state: CampaignRuntimeState
    target_state: CampaignRuntimeState
    trigger: CampaignTransitionTrigger
    reason_code: str
    description: str
    requires_owner_review: bool = False
    requires_flat_proof: bool = False
    allows_risk_reducing_close: bool = False


@dataclass(frozen=True)
class CampaignTransitionInput:
    target_state: CampaignRuntimeState | str
    trigger: CampaignTransitionTrigger | str
    reason: Optional[str]
    updated_by: str
    occurred_at_ms: Optional[int] = None
    active_strategy_contract_id: Optional[str] = None
    active_session_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CampaignTransitionRecord:
    sequence_number: int
    previous_state: CampaignRuntimeState
    target_state: CampaignRuntimeState
    trigger: CampaignTransitionTrigger
    reason: Optional[str]
    updated_by: str
    occurred_at_ms: int
    accepted: bool
    rule_reason_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    active_strategy_contract_id: Optional[str] = None
    active_session_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def next_state(self) -> CampaignRuntimeState:
        return self.target_state if self.accepted else self.previous_state

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "sequence_number": self.sequence_number,
            "previous_state": self.previous_state.value,
            "target_state": self.target_state.value,
            "next_state": self.next_state.value,
            "trigger": self.trigger.value,
            "reason": self.reason,
            "updated_by": self.updated_by,
            "occurred_at_ms": self.occurred_at_ms,
            "accepted": self.accepted,
            "rule_reason_code": self.rule_reason_code,
            "rejection_reason": self.rejection_reason,
            "active_strategy_contract_id": self.active_strategy_contract_id,
            "active_session_id": self.active_session_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CampaignReplayResult:
    initial_state: CampaignRuntimeState
    final_state: CampaignRuntimeState
    accepted: bool
    records: tuple[CampaignTransitionRecord, ...]
    rejection_reason: Optional[str] = None


@dataclass(frozen=True)
class CampaignReplayEvidence:
    scope_key: str
    initial_state: CampaignRuntimeState
    replay_final_state: CampaignRuntimeState
    snapshot_state: Optional[CampaignRuntimeState]
    matches_snapshot: bool
    accepted: bool
    transition_count: int
    rejected_transition_count: int
    records: tuple[CampaignTransitionRecord, ...]
    rejection_reason: Optional[str] = None


_TRANSITION_TABLE: tuple[CampaignTransitionRule, ...] = (
    CampaignTransitionRule(
        CampaignRuntimeState.OBSERVE,
        CampaignRuntimeState.ARMED,
        CampaignTransitionTrigger.OWNER_ARM,
        "owner_arm_to_bounded_session",
        "Owner arms one bounded campaign session.",
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.OBSERVE,
        CampaignRuntimeState.PAUSED,
        CampaignTransitionTrigger.OWNER_PAUSE,
        "owner_pause_before_session",
        "Owner pauses campaign before an armed session exists.",
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.OBSERVE,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.OWNER_HARD_LOCK,
        "owner_hard_lock",
        "Owner applies a manual campaign hard lock.",
        requires_owner_review=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.OBSERVE,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.RISK_CRITICAL,
        "risk_critical_hard_lock",
        "Runtime critical risk event hard-locks the campaign.",
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.ARMED,
        CampaignTransitionTrigger.ENTRY_FILLED,
        "entry_filled_state_retained",
        "Entry fill confirms exposure under the armed session.",
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.PAUSED,
        CampaignTransitionTrigger.OWNER_PAUSE,
        "owner_pause_armed_session",
        "Owner pauses an armed session.",
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignTransitionTrigger.PROFIT_PROTECT_TRIGGERED,
        "profit_threshold_reduce_close_required",
        "Profit threshold activates reduce-or-close requirement.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignTransitionTrigger.STOP_LOSS_FILLED,
        "stop_loss_filled_loss_lock",
        "Stop-loss fill locks the campaign against new entries.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.OWNER_HARD_LOCK,
        "owner_hard_lock",
        "Owner applies a manual campaign hard lock.",
        requires_owner_review=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.RISK_CRITICAL,
        "risk_critical_hard_lock",
        "Runtime critical risk event hard-locks the campaign.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.CLOSED,
        CampaignTransitionTrigger.POSITION_CLOSED,
        "runtime_close_flat_proof",
        "Runtime-managed close ends the campaign exposure.",
        requires_flat_proof=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.OBSERVE,
        CampaignTransitionTrigger.OWNER_REVIEW_RESET,
        "owner_review_reset_to_observe",
        "Owner review resets paused campaign to observe.",
        requires_owner_review=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.ARMED,
        CampaignTransitionTrigger.OWNER_RESUME,
        "owner_resume_armed_session",
        "Owner resumes a paused bounded session.",
        requires_owner_review=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.OWNER_HARD_LOCK,
        "owner_hard_lock",
        "Owner applies a manual campaign hard lock.",
        requires_owner_review=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.RISK_CRITICAL,
        "risk_critical_hard_lock",
        "Runtime critical risk event hard-locks the campaign.",
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignTransitionTrigger.PROFIT_PROTECT_TRIGGERED,
        "profit_protect_event_state_retained",
        "Repeated profit protection event keeps campaign in profit protection.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignRuntimeState.PAUSED,
        CampaignTransitionTrigger.OWNER_PAUSE,
        "owner_pause_profit_protect",
        "Owner pauses while profit protection is active.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.OWNER_HARD_LOCK,
        "owner_hard_lock",
        "Owner applies a manual campaign hard lock.",
        requires_owner_review=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.RISK_CRITICAL,
        "risk_critical_hard_lock",
        "Runtime critical risk event hard-locks the campaign.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignRuntimeState.CLOSED,
        CampaignTransitionTrigger.POSITION_CLOSED,
        "runtime_close_flat_proof",
        "Runtime-managed close ends the campaign exposure.",
        requires_flat_proof=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignTransitionTrigger.STOP_LOSS_FILLED,
        "stop_loss_event_state_retained",
        "Repeated stop-loss event keeps campaign loss-locked.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.OWNER_HARD_LOCK,
        "owner_hard_lock",
        "Owner applies a manual campaign hard lock.",
        requires_owner_review=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.RISK_CRITICAL,
        "risk_critical_hard_lock",
        "Runtime critical risk event hard-locks the campaign.",
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignRuntimeState.CLOSED,
        CampaignTransitionTrigger.POSITION_CLOSED,
        "runtime_close_flat_proof",
        "Runtime-managed close ends the loss-locked campaign.",
        requires_flat_proof=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.HARD_LOCKED,
        CampaignRuntimeState.CLOSED,
        CampaignTransitionTrigger.POSITION_CLOSED,
        "reviewed_risk_reducing_close_flat_proof",
        "Reviewed risk-reducing close ends hard-locked exposure.",
        requires_owner_review=True,
        requires_flat_proof=True,
        allows_risk_reducing_close=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.CLOSED,
        CampaignRuntimeState.OBSERVE,
        CampaignTransitionTrigger.OWNER_REVIEW_RESET,
        "owner_review_reset_after_flat_campaign",
        "Owner review resets a closed flat campaign to observe.",
        requires_owner_review=True,
        requires_flat_proof=True,
    ),
    CampaignTransitionRule(
        CampaignRuntimeState.CLOSED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignTransitionTrigger.RISK_CRITICAL,
        "post_close_risk_critical_hard_lock",
        "Post-close critical risk evidence hard-locks the campaign.",
    ),
)


@dataclass(frozen=True)
class CampaignGateDecision:
    state: str
    allowed_new_entry: bool
    reason: str
    reason_message: str
    checked_at_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


def get_campaign_transition_table() -> tuple[CampaignTransitionRule, ...]:
    return _TRANSITION_TABLE


def replay_campaign_transitions(
    *,
    initial_state: CampaignRuntimeState | str,
    transitions: Iterable[CampaignTransitionInput],
) -> CampaignReplayResult:
    current_state = _parse_campaign_state(initial_state)
    records: list[CampaignTransitionRecord] = []
    rejection_reason: Optional[str] = None

    for sequence_number, transition in enumerate(transitions, start=1):
        target_state = _parse_campaign_state(transition.target_state)
        trigger = _parse_campaign_trigger(transition.trigger)
        record = _build_transition_record(
            sequence_number=sequence_number,
            current_state=current_state,
            target_state=target_state,
            trigger=trigger,
            reason=transition.reason,
            updated_by=transition.updated_by,
            occurred_at_ms=transition.occurred_at_ms or _now_ms(),
            active_strategy_contract_id=transition.active_strategy_contract_id,
            active_session_id=transition.active_session_id,
            metadata=transition.metadata,
        )
        records.append(record)
        if not record.accepted:
            rejection_reason = record.rejection_reason
            break
        current_state = record.next_state

    return CampaignReplayResult(
        initial_state=_parse_campaign_state(initial_state),
        final_state=current_state,
        accepted=rejection_reason is None,
        records=tuple(records),
        rejection_reason=rejection_reason,
    )


def replay_campaign_transition_logs(
    *,
    scope_key: str,
    initial_state: CampaignRuntimeState | str,
    transitions: Iterable[CampaignStateTransitionLog],
    snapshot_state: CampaignRuntimeState | str | None = None,
) -> CampaignReplayEvidence:
    current_state = _parse_campaign_state(initial_state)
    parsed_snapshot_state = (
        _parse_campaign_state(snapshot_state) if snapshot_state is not None else None
    )
    records: list[CampaignTransitionRecord] = []
    rejection_reason: Optional[str] = None
    rejected_count = 0

    for transition in sorted(transitions, key=lambda item: item.sequence_number):
        if transition.scope_key != scope_key:
            rejection_reason = (
                f"Ledger scope mismatch: expected {scope_key}, got {transition.scope_key}"
            )
            break
        expected = _build_transition_record(
            sequence_number=transition.sequence_number,
            current_state=current_state,
            target_state=_parse_campaign_state(transition.target_status),
            trigger=_parse_campaign_trigger(transition.trigger),
            reason=transition.reason,
            updated_by=transition.updated_by,
            occurred_at_ms=transition.occurred_at_ms,
            active_strategy_contract_id=transition.active_strategy_contract_id,
            active_session_id=transition.active_session_id,
            metadata=dict(transition.metadata or {}),
        )
        persisted_next = _parse_campaign_state(transition.next_status)
        if (
            expected.accepted != transition.accepted
            or expected.next_state != persisted_next
        ):
            rejection_reason = (
                "Ledger replay mismatch at sequence "
                f"{transition.sequence_number}: expected accepted={expected.accepted} "
                f"next={expected.next_state.value}, persisted accepted={transition.accepted} "
                f"next={persisted_next.value}"
            )
            records.append(
                replace(
                    expected,
                    accepted=False,
                    rejection_reason=rejection_reason,
                )
            )
            break
        records.append(expected)
        if transition.accepted:
            current_state = persisted_next
        else:
            rejected_count += 1

    matches_snapshot = (
        parsed_snapshot_state is None or current_state == parsed_snapshot_state
    )
    accepted = rejection_reason is None and matches_snapshot
    if rejection_reason is None and not matches_snapshot:
        rejection_reason = (
            "Ledger replay final state does not match snapshot: "
            f"replay={current_state.value}, snapshot={parsed_snapshot_state.value}"
        )
    return CampaignReplayEvidence(
        scope_key=scope_key,
        initial_state=_parse_campaign_state(initial_state),
        replay_final_state=current_state,
        snapshot_state=parsed_snapshot_state,
        matches_snapshot=matches_snapshot,
        accepted=accepted,
        transition_count=len(records),
        rejected_transition_count=rejected_count,
        records=tuple(records),
        rejection_reason=rejection_reason,
    )


class CampaignStateService:
    """Fail-closed persisted state machine for campaign runtime control."""

    def __init__(
        self,
        *,
        repository: Optional[Any],
        scope_key: str = CAMPAIGN_STATE_SCOPE_KEY,
    ) -> None:
        self._repository = repository
        self._scope_key = scope_key
        self._state: Optional[CampaignStateSnapshot] = None
        self._audit_records: list[CampaignTransitionRecord] = []

    async def initialize(self) -> None:
        if self._repository is None:
            logger.critical(
                "[CampaignState] Repository missing; new entries fail closed."
            )
            self._state = self._default_snapshot(
                status=CampaignRuntimeState.HARD_LOCKED.value,
                reason="CAMPAIGN_STATE_REPOSITORY_MISSING",
                updated_by="system",
                source="process_fail_closed",
            )
            return

        await self._repository.initialize()
        snapshot = await self._repository.get_state(self._scope_key)
        if snapshot is None:
            snapshot = await self._repository.set_state(
                scope_key=self._scope_key,
                status=CampaignRuntimeState.OBSERVE.value,
                reason="startup_default_observe",
                updated_by="system",
                updated_at_ms=self._now_ms(),
                active_strategy_contract_id=None,
                active_session_id=None,
            )
        self._state = snapshot

    def get_state(self) -> CampaignStateSnapshot:
        if self._state is None:
            return self._default_snapshot(
                status=CampaignRuntimeState.HARD_LOCKED.value,
                reason="CAMPAIGN_STATE_NOT_INITIALIZED",
                updated_by="system",
                source="process_fail_closed",
            )
        return self._state

    def get_transition_audit_records(self) -> tuple[CampaignTransitionRecord, ...]:
        return tuple(self._audit_records)

    def get_transition_table(self) -> tuple[CampaignTransitionRule, ...]:
        return get_campaign_transition_table()

    async def get_transition_ledger(
        self,
        *,
        limit: int = 500,
    ) -> tuple[CampaignStateTransitionLog, ...]:
        list_transitions = getattr(self._repository, "list_transitions", None)
        if self._repository is None or not callable(list_transitions):
            return tuple(_record_to_transition_log(self._scope_key, record) for record in self._audit_records)
        return tuple(
            await list_transitions(
                self._scope_key,
                limit=limit,
            )
        )

    async def build_replay_evidence(
        self,
        *,
        initial_state: CampaignRuntimeState | str = CampaignRuntimeState.OBSERVE,
        limit: int = 500,
    ) -> CampaignReplayEvidence:
        snapshot = await self._refresh_state()
        transitions = await self.get_transition_ledger(limit=limit)
        return replay_campaign_transition_logs(
            scope_key=self._scope_key,
            initial_state=initial_state,
            transitions=transitions,
            snapshot_state=snapshot.status,
        )

    async def evaluate_new_entry(
        self,
        *,
        symbol: str,
        strategy_contract_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> CampaignGateDecision:
        checked_at_ms = self._now_ms()
        snapshot = await self._refresh_state()
        metadata = {
            "scope_key": snapshot.scope_key,
            "symbol": symbol,
            "status": snapshot.status,
            "active_strategy_contract_id": snapshot.active_strategy_contract_id,
            "active_session_id": snapshot.active_session_id,
            "requested_strategy_contract_id": strategy_contract_id,
            "requested_session_id": session_id,
        }
        if snapshot.status != CampaignRuntimeState.ARMED.value:
            return CampaignGateDecision(
                state=snapshot.status,
                allowed_new_entry=False,
                reason=CAMPAIGN_STATE_BLOCK_REASON,
                reason_message=(
                    "Campaign state is not armed; new entries are blocked. "
                    f"state={snapshot.status}, state_reason={snapshot.reason or 'unspecified'}"
                ),
                checked_at_ms=checked_at_ms,
                metadata=metadata,
            )
        return CampaignGateDecision(
            state=snapshot.status,
            allowed_new_entry=True,
            reason="CAMPAIGN_STATE_ARMED",
            reason_message="Campaign state is armed for new entries.",
            checked_at_ms=checked_at_ms,
            metadata=metadata,
        )

    async def set_state(
        self,
        *,
        status: str,
        reason: Optional[str],
        updated_by: str,
        active_strategy_contract_id: Optional[str] = None,
        active_session_id: Optional[str] = None,
        trigger: CampaignTransitionTrigger | str | None = None,
        metadata: Optional[dict[str, Any]] = None,
        symbol: Optional[str] = None,
        profile_id: Optional[str] = None,
        position_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> CampaignStateSnapshot:
        target = self._parse_state(status)
        current = await self._refresh_state()
        current_state = self._parse_state(current.status)
        if trigger is None and target in {
            CampaignRuntimeState.CLOSED,
            CampaignRuntimeState.PROFIT_PROTECT,
            CampaignRuntimeState.LOSS_LOCKED,
        }:
            raise ValueError(
                "explicit campaign transition trigger is required for "
                f"{target.value}"
            )
        transition_trigger = (
            _parse_campaign_trigger(trigger)
            if trigger is not None
            else self._infer_owner_trigger(current_state, target)
        )
        transition_metadata = self._build_metadata(
            metadata=metadata,
            symbol=symbol,
            profile_id=profile_id,
            position_id=position_id,
            signal_id=signal_id,
            order_id=order_id,
        )
        record = _build_transition_record(
            sequence_number=len(self._audit_records) + 1,
            current_state=current_state,
            target_state=target,
            trigger=transition_trigger,
            reason=reason,
            updated_by=updated_by,
            occurred_at_ms=self._now_ms(),
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            metadata=transition_metadata,
        )
        if not record.accepted:
            persisted_record = await self._persist_transition_record(record)
            self._audit_records.append(persisted_record)
            logger.warning(
                "[CampaignState] Rejected campaign state transition: %s",
                persisted_record.to_log_dict(),
            )
            raise ValueError(
                persisted_record.rejection_reason
                or (
                    "Invalid campaign state transition: "
                    f"{current_state.value}->{target.value}"
                )
            )

        if self._repository is None:
            raise RuntimeError("Campaign state repository is unavailable")

        set_state_with_transition = getattr(
            self._repository,
            "set_state_with_transition",
            None,
        )
        if callable(set_state_with_transition):
            transition_log = _record_to_transition_log(self._scope_key, record)
            snapshot, persisted_transition = await set_state_with_transition(
                scope_key=self._scope_key,
                status=target.value,
                reason=reason,
                updated_by=updated_by,
                updated_at_ms=self._now_ms(),
                active_strategy_contract_id=active_strategy_contract_id,
                active_session_id=active_session_id,
                transition=transition_log,
            )
            record = _transition_log_to_record(persisted_transition)
        else:
            snapshot = await self._repository.set_state(
                scope_key=self._scope_key,
                status=target.value,
                reason=reason,
                updated_by=updated_by,
                updated_at_ms=self._now_ms(),
                active_strategy_contract_id=active_strategy_contract_id,
                active_session_id=active_session_id,
            )
            record = await self._persist_transition_record(record)
        self._state = snapshot
        self._audit_records.append(record)
        logger.warning(
            "[CampaignState] Updated runtime campaign state: %s -> %s by=%s reason=%s",
            current.status,
            snapshot.status,
            updated_by,
            reason,
        )
        logger.warning(
            "[CampaignState] Audit transition record: %s",
            record.to_log_dict(),
        )
        return snapshot

    async def _persist_transition_record(
        self,
        record: CampaignTransitionRecord,
    ) -> CampaignTransitionRecord:
        record_transition = getattr(self._repository, "record_transition", None)
        if self._repository is None or not callable(record_transition):
            return record
        transition_log = _record_to_transition_log(self._scope_key, record)
        try:
            persisted_transition = await record_transition(transition_log)
        except Exception as exc:
            logger.error(
                "[CampaignState] Campaign transition ledger write failed: %s",
                exc,
                exc_info=True,
            )
            raise
        return _transition_log_to_record(persisted_transition)

    async def apply_runtime_event(
        self,
        *,
        event: CampaignRuntimeEvent | str,
        reason: Optional[str],
        updated_by: str = "runtime",
        active_strategy_contract_id: Optional[str] = None,
        active_session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        symbol: Optional[str] = None,
        profile_id: Optional[str] = None,
        position_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> CampaignStateSnapshot:
        """Advance campaign state from a runtime event.

        This method only mutates the durable campaign state row. It does not
        place, cancel, resize, or otherwise mutate exchange orders.
        """
        runtime_event = (
            event if isinstance(event, CampaignRuntimeEvent) else CampaignRuntimeEvent(event)
        )
        target = {
            CampaignRuntimeEvent.ENTRY_FILLED: CampaignRuntimeState.ARMED,
            CampaignRuntimeEvent.PROFIT_PROTECT_TRIGGERED: CampaignRuntimeState.PROFIT_PROTECT,
            CampaignRuntimeEvent.STOP_LOSS_FILLED: CampaignRuntimeState.LOSS_LOCKED,
            CampaignRuntimeEvent.POSITION_CLOSED: CampaignRuntimeState.CLOSED,
            CampaignRuntimeEvent.RISK_CRITICAL: CampaignRuntimeState.HARD_LOCKED,
        }[runtime_event]
        return await self.set_state(
            status=target.value,
            reason=reason or runtime_event.value,
            updated_by=updated_by,
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            trigger=runtime_event.value,
            metadata=metadata,
            symbol=symbol,
            profile_id=profile_id,
            position_id=position_id,
            signal_id=signal_id,
            order_id=order_id,
        )

    async def _refresh_state(self) -> CampaignStateSnapshot:
        if self._repository is None:
            return self.get_state()
        try:
            snapshot = await self._repository.get_state(self._scope_key)
        except Exception as exc:
            logger.error(
                "Campaign state read failed; new entries fail closed: %s",
                exc,
                exc_info=True,
            )
            self._state = self._default_snapshot(
                status=CampaignRuntimeState.HARD_LOCKED.value,
                reason="CAMPAIGN_STATE_READ_FAILED",
                updated_by="system",
                source="process_fail_closed",
            )
            return self._state
        if snapshot is None:
            self._state = self._default_snapshot(
                status=CampaignRuntimeState.HARD_LOCKED.value,
                reason="CAMPAIGN_STATE_ROW_MISSING",
                updated_by="system",
                source="process_fail_closed",
            )
            return self._state
        self._state = snapshot
        return snapshot

    def _default_snapshot(
        self,
        *,
        status: str,
        reason: Optional[str],
        updated_by: str,
        source: str,
    ) -> CampaignStateSnapshot:
        return CampaignStateSnapshot(
            scope_key=self._scope_key,
            status=status,
            reason=reason,
            updated_by=updated_by,
            updated_at_ms=self._now_ms(),
            active_strategy_contract_id=None,
            active_session_id=None,
            source=source,
        )

    @staticmethod
    def _parse_state(status: str) -> CampaignRuntimeState:
        return _parse_campaign_state(status)

    @staticmethod
    def _now_ms() -> int:
        return _now_ms()

    @staticmethod
    def _infer_owner_trigger(
        current_state: CampaignRuntimeState,
        target_state: CampaignRuntimeState,
    ) -> CampaignTransitionTrigger:
        if current_state == target_state:
            return CampaignTransitionTrigger.NOOP
        if target_state == CampaignRuntimeState.ARMED:
            if current_state == CampaignRuntimeState.PAUSED:
                return CampaignTransitionTrigger.OWNER_RESUME
            return CampaignTransitionTrigger.OWNER_ARM
        if target_state == CampaignRuntimeState.PAUSED:
            return CampaignTransitionTrigger.OWNER_PAUSE
        if target_state == CampaignRuntimeState.OBSERVE:
            return CampaignTransitionTrigger.OWNER_REVIEW_RESET
        if target_state == CampaignRuntimeState.HARD_LOCKED:
            return CampaignTransitionTrigger.OWNER_HARD_LOCK
        if target_state == CampaignRuntimeState.CLOSED:
            return CampaignTransitionTrigger.POSITION_CLOSED
        if target_state == CampaignRuntimeState.PROFIT_PROTECT:
            return CampaignTransitionTrigger.PROFIT_PROTECT_TRIGGERED
        if target_state == CampaignRuntimeState.LOSS_LOCKED:
            return CampaignTransitionTrigger.STOP_LOSS_FILLED
        return CampaignTransitionTrigger.NOOP

    @staticmethod
    def _build_metadata(
        *,
        metadata: Optional[dict[str, Any]],
        symbol: Optional[str],
        profile_id: Optional[str],
        position_id: Optional[str],
        signal_id: Optional[str],
        order_id: Optional[str],
    ) -> dict[str, Any]:
        transition_metadata = dict(metadata or {})
        for key, value in {
            "symbol": symbol,
            "profile_id": profile_id,
            "position_id": position_id,
            "signal_id": signal_id,
            "order_id": order_id,
        }.items():
            if value is not None:
                transition_metadata[key] = value
        return transition_metadata


def _parse_campaign_state(status: CampaignRuntimeState | str) -> CampaignRuntimeState:
    if isinstance(status, CampaignRuntimeState):
        return status
    try:
        return CampaignRuntimeState(status)
    except ValueError as exc:
        raise ValueError(f"Unknown campaign state: {status}") from exc


def _parse_campaign_trigger(
    trigger: CampaignTransitionTrigger | CampaignRuntimeEvent | str,
) -> CampaignTransitionTrigger:
    if isinstance(trigger, CampaignTransitionTrigger):
        return trigger
    if isinstance(trigger, CampaignRuntimeEvent):
        return CampaignTransitionTrigger(trigger.value)
    try:
        return CampaignTransitionTrigger(trigger)
    except ValueError as exc:
        raise ValueError(f"Unknown campaign transition trigger: {trigger}") from exc


def _record_to_transition_log(
    scope_key: str,
    record: CampaignTransitionRecord,
) -> CampaignStateTransitionLog:
    return CampaignStateTransitionLog(
        scope_key=scope_key,
        sequence_number=record.sequence_number,
        previous_status=record.previous_state.value,
        target_status=record.target_state.value,
        next_status=record.next_state.value,
        trigger=record.trigger.value,
        reason=record.reason,
        updated_by=record.updated_by,
        occurred_at_ms=record.occurred_at_ms,
        accepted=record.accepted,
        rule_reason_code=record.rule_reason_code,
        rejection_reason=record.rejection_reason,
        active_strategy_contract_id=record.active_strategy_contract_id,
        active_session_id=record.active_session_id,
        metadata=dict(record.metadata),
    )


def _transition_log_to_record(
    transition: CampaignStateTransitionLog,
) -> CampaignTransitionRecord:
    return CampaignTransitionRecord(
        sequence_number=transition.sequence_number,
        previous_state=_parse_campaign_state(transition.previous_status),
        target_state=_parse_campaign_state(transition.target_status),
        trigger=_parse_campaign_trigger(transition.trigger),
        reason=transition.reason,
        updated_by=transition.updated_by,
        occurred_at_ms=transition.occurred_at_ms,
        accepted=transition.accepted,
        rule_reason_code=transition.rule_reason_code,
        rejection_reason=transition.rejection_reason,
        active_strategy_contract_id=transition.active_strategy_contract_id,
        active_session_id=transition.active_session_id,
        metadata=dict(transition.metadata or {}),
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _find_transition_rule(
    *,
    current_state: CampaignRuntimeState,
    target_state: CampaignRuntimeState,
    trigger: CampaignTransitionTrigger,
) -> Optional[CampaignTransitionRule]:
    for rule in _TRANSITION_TABLE:
        if (
            rule.current_state == current_state
            and rule.target_state == target_state
            and rule.trigger == trigger
        ):
            return rule
    return None


def _build_transition_record(
    *,
    sequence_number: int,
    current_state: CampaignRuntimeState,
    target_state: CampaignRuntimeState,
    trigger: CampaignTransitionTrigger,
    reason: Optional[str],
    updated_by: str,
    occurred_at_ms: int,
    active_strategy_contract_id: Optional[str],
    active_session_id: Optional[str],
    metadata: dict[str, Any],
) -> CampaignTransitionRecord:
    if current_state == target_state and trigger == CampaignTransitionTrigger.NOOP:
        return CampaignTransitionRecord(
            sequence_number=sequence_number,
            previous_state=current_state,
            target_state=target_state,
            trigger=trigger,
            reason=reason,
            updated_by=updated_by,
            occurred_at_ms=occurred_at_ms,
            accepted=True,
            rule_reason_code="noop_state_retained",
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            metadata=dict(metadata),
        )

    rule = _find_transition_rule(
        current_state=current_state,
        target_state=target_state,
        trigger=trigger,
    )
    if rule is None:
        return CampaignTransitionRecord(
            sequence_number=sequence_number,
            previous_state=current_state,
            target_state=target_state,
            trigger=trigger,
            reason=reason,
            updated_by=updated_by,
            occurred_at_ms=occurred_at_ms,
            accepted=False,
            rejection_reason=(
                "Invalid campaign state transition: "
                f"{current_state.value}->{target_state.value} "
                f"via {trigger.value}"
            ),
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            metadata=dict(metadata),
        )
    if rule.requires_flat_proof and not _metadata_has_flat_proof(metadata):
        return CampaignTransitionRecord(
            sequence_number=sequence_number,
            previous_state=current_state,
            target_state=target_state,
            trigger=trigger,
            reason=reason,
            updated_by=updated_by,
            occurred_at_ms=occurred_at_ms,
            accepted=False,
            rejection_reason=(
                "Campaign transition requires flat proof: "
                f"{current_state.value}->{target_state.value} via {trigger.value}"
            ),
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            metadata=dict(metadata),
        )
    if rule.requires_owner_review and not _metadata_has_owner_review(metadata):
        return CampaignTransitionRecord(
            sequence_number=sequence_number,
            previous_state=current_state,
            target_state=target_state,
            trigger=trigger,
            reason=reason,
            updated_by=updated_by,
            occurred_at_ms=occurred_at_ms,
            accepted=False,
            rejection_reason=(
                "Campaign transition requires owner review evidence: "
                f"{current_state.value}->{target_state.value} via {trigger.value}"
            ),
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            metadata=dict(metadata),
        )
    return CampaignTransitionRecord(
        sequence_number=sequence_number,
        previous_state=current_state,
        target_state=target_state,
        trigger=trigger,
        reason=reason,
        updated_by=updated_by,
        occurred_at_ms=occurred_at_ms,
        accepted=True,
        rule_reason_code=rule.reason_code,
        active_strategy_contract_id=active_strategy_contract_id,
        active_session_id=active_session_id,
        metadata=dict(metadata),
    )


def _metadata_has_flat_proof(metadata: dict[str, Any]) -> bool:
    flat_proof = metadata.get("flat_proof")
    if isinstance(flat_proof, dict):
        return bool(flat_proof.get("all_flat"))
    if flat_proof is not None:
        return bool(flat_proof)
    final_inventory = metadata.get("final_inventory")
    if isinstance(final_inventory, dict):
        return bool(final_inventory.get("all_flat"))
    return bool(metadata.get("all_flat"))


def _metadata_has_owner_review(metadata: dict[str, Any]) -> bool:
    if bool(metadata.get("owner_review")):
        return True
    if bool(metadata.get("owner_review_verified")):
        return True
    return bool(metadata.get("owner_review_decision_id"))
