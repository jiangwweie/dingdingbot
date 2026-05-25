"""Durable runtime campaign state gate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.infrastructure.logger import logger
from src.infrastructure.repository_ports import CampaignStateSnapshot


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


_ALLOWED_TRANSITIONS: dict[CampaignRuntimeState, set[CampaignRuntimeState]] = {
    CampaignRuntimeState.OBSERVE: {
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.HARD_LOCKED,
    },
    CampaignRuntimeState.ARMED: {
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignRuntimeState.LOSS_LOCKED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignRuntimeState.CLOSED,
    },
    CampaignRuntimeState.PAUSED: {
        CampaignRuntimeState.OBSERVE,
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.HARD_LOCKED,
    },
    CampaignRuntimeState.PROFIT_PROTECT: {
        CampaignRuntimeState.PAUSED,
        CampaignRuntimeState.HARD_LOCKED,
        CampaignRuntimeState.CLOSED,
    },
    CampaignRuntimeState.LOSS_LOCKED: {
        CampaignRuntimeState.HARD_LOCKED,
        CampaignRuntimeState.CLOSED,
    },
    CampaignRuntimeState.HARD_LOCKED: {
        CampaignRuntimeState.CLOSED,
    },
    CampaignRuntimeState.CLOSED: {
        CampaignRuntimeState.OBSERVE,
    },
}


@dataclass(frozen=True)
class CampaignGateDecision:
    state: str
    allowed_new_entry: bool
    reason: str
    reason_message: str
    checked_at_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


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
    ) -> CampaignStateSnapshot:
        target = self._parse_state(status)
        current = await self._refresh_state()
        current_state = self._parse_state(current.status)
        if target not in _ALLOWED_TRANSITIONS[current_state] and target != current_state:
            raise ValueError(
                f"Invalid campaign state transition: {current_state.value}->{target.value}"
            )

        if self._repository is None:
            raise RuntimeError("Campaign state repository is unavailable")

        snapshot = await self._repository.set_state(
            scope_key=self._scope_key,
            status=target.value,
            reason=reason,
            updated_by=updated_by,
            updated_at_ms=self._now_ms(),
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
        )
        self._state = snapshot
        logger.warning(
            "[CampaignState] Updated runtime campaign state: %s -> %s by=%s reason=%s",
            current.status,
            snapshot.status,
            updated_by,
            reason,
        )
        return snapshot

    async def apply_runtime_event(
        self,
        *,
        event: CampaignRuntimeEvent | str,
        reason: Optional[str],
        updated_by: str = "runtime",
        active_strategy_contract_id: Optional[str] = None,
        active_session_id: Optional[str] = None,
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
        try:
            return CampaignRuntimeState(status)
        except ValueError as exc:
            raise ValueError(f"Unknown campaign state: {status}") from exc

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
