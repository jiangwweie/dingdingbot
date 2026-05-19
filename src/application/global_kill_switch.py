"""Global Kill Switch v0: stop all new entries without touching existing orders."""

from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.application.decision_trace import TraceService
from src.infrastructure.logger import logger
from src.infrastructure.repository_ports import (
    GlobalKillSwitchRepositoryPort,
    GlobalKillSwitchStateSnapshot,
)


KILL_SWITCH_BLOCK_REASON = "KILL_SWITCH"
GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON = "GKS_STATE_UNAVAILABLE"
GLOBAL_KILL_SWITCH_MISSING_REASON = "GKS_STATE_MISSING"
GLOBAL_KILL_SWITCH_CORRUPT_REASON = "GKS_STATE_CORRUPT"
GLOBAL_KILL_SWITCH_CONFLICTING_REASON = "GKS_STATE_CONFLICTING"

_FAIL_CLOSED_STATE_REASONS = {
    GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON,
    GLOBAL_KILL_SWITCH_MISSING_REASON,
    GLOBAL_KILL_SWITCH_CORRUPT_REASON,
    GLOBAL_KILL_SWITCH_CONFLICTING_REASON,
    "GKS_INIT_FAILED",
}


class GlobalKillSwitchState(BaseModel):
    """Runtime-readable GKS state."""

    active: bool = Field(..., description="Whether all new entries are blocked")
    reason: Optional[str] = Field(default=None, description="Owner/operator reason")
    updated_by: str = Field(default="system", description="Last writer")
    updated_at_ms: int = Field(..., description="Last update timestamp in milliseconds")
    source: str = Field(default="memory", description="State source")


class GlobalKillSwitchService:
    """Minimal stop-all-new-entries service with PG persistence and memory cache."""

    def __init__(
        self,
        repository: Optional[GlobalKillSwitchRepositoryPort] = None,
        *,
        trace_service: Optional[TraceService] = None,
        notifier: Optional[Any] = None,
    ) -> None:
        self._repository = repository
        self._trace_service = trace_service
        self._notifier = notifier
        self._state = GlobalKillSwitchState(
            active=False,
            reason=None,
            updated_by="system",
            updated_at_ms=self._now_ms(),
            source="memory_default",
        )

    async def initialize(self) -> None:
        """Restore persisted state using live-safe fail-closed semantics."""
        if self._repository is None:
            self._state = self._fail_closed_state(
                reason=GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON,
                source="repository_unavailable_fail_closed",
            )
            logger.critical(
                "[GKS-v0][HIGH] No repository configured; new entries are blocked fail-closed."
            )
            return

        try:
            await self._repository.initialize()
            snapshot = await self._repository.get_state()
        except Exception as exc:
            self._state = self._fail_closed_state(
                reason=GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON,
                source="read_failure_fail_closed",
            )
            await self._alert_high(
                "GKS state restore failed",
                "Global Kill Switch state could not be read from PG; "
                "new entries are blocked fail-closed for this process.",
                exc,
            )
            return

        if snapshot is None:
            self._state = self._fail_closed_state(
                reason=GLOBAL_KILL_SWITCH_MISSING_REASON,
                source="missing_row_fail_closed",
            )
            logger.critical(
                "[GKS-v0][HIGH] PG row missing; new entries are blocked fail-closed."
            )
            return

        invalid_reason = self._validate_snapshot(snapshot)
        if invalid_reason is not None:
            self._state = self._fail_closed_state(
                reason=invalid_reason,
                source="invalid_state_fail_closed",
            )
            logger.critical(
                "[GKS-v0][HIGH] Invalid PG state; new entries are blocked fail-closed: "
                "reason=%s, snapshot=%s",
                invalid_reason,
                snapshot,
            )
            return

        self._state = self._from_snapshot(snapshot)
        logger.info(
            "[GKS-v0] Restored Global Kill Switch state: "
            f"active={self._state.active}, source={self._state.source}, "
            f"updated_at_ms={self._state.updated_at_ms}"
        )

    def get_state(self) -> GlobalKillSwitchState:
        """Return the in-memory cache."""
        return self._state.model_copy(deep=True)

    def is_active(self) -> bool:
        return bool(self._state.active)

    async def set_state(
        self,
        *,
        active: bool,
        reason: Optional[str],
        updated_by: str,
    ) -> GlobalKillSwitchState:
        """Persist then cache a state change. Persistence failure is not downgraded."""
        updated_at_ms = self._now_ms()
        if self._repository is None:
            self._state = GlobalKillSwitchState(
                active=active,
                reason=reason,
                updated_by=updated_by,
                updated_at_ms=updated_at_ms,
                source="memory_only",
            )
            logger.warning(
                "[GKS-v0] State changed without PG repository: "
                f"active={active}. This is not live-ready."
            )
            return self.get_state()

        try:
            snapshot = await self._repository.set_state(
                active=active,
                reason=reason,
                updated_by=updated_by,
                updated_at_ms=updated_at_ms,
            )
        except Exception as exc:
            await self._alert_high(
                "GKS persistence failure",
                "Global Kill Switch toggle failed to persist to PG; "
                "in-memory state was not changed.",
                exc,
            )
            raise

        self._state = self._from_snapshot(snapshot)
        logger.warning(
            "[GKS-v0] Global Kill Switch toggled: "
            f"active={self._state.active}, updated_by={self._state.updated_by}, "
            f"reason={self._state.reason}"
        )
        return self.get_state()

    def emit_check_trace(
        self,
        *,
        intent_id: str,
        signal: Any,
        decision: str,
        reason: Optional[str],
    ) -> None:
        if self._trace_service is None:
            return
        self._trace_service.emit_risk_decision(
            lifecycle_id=f"intent:{intent_id}",
            event_type="risk.global_kill_switch_check",
            decision=decision,
            reason=reason,
            metadata={
                "active": self._state.active,
                "state_reason": self._state.reason,
                "state_source": self._state.source,
                "state_updated_at_ms": self._state.updated_at_ms,
                "symbol": getattr(signal, "symbol", None),
                "strategy_name": getattr(signal, "strategy_name", None),
            },
        )

    async def _alert_high(self, title: str, message: str, exc: Exception) -> None:
        logger.critical("[GKS-v0][HIGH] %s: %s error=%s", title, message, exc, exc_info=True)
        if self._notifier is None:
            return
        try:
            result = self._notifier(title, f"[HIGH] {message} error={exc}")
            if hasattr(result, "__await__"):
                await result
        except Exception as alert_exc:
            logger.error("[GKS-v0] HIGH alert delivery failed: %s", alert_exc, exc_info=True)

    @staticmethod
    def _from_snapshot(snapshot: GlobalKillSwitchStateSnapshot) -> GlobalKillSwitchState:
        return GlobalKillSwitchState(
            active=snapshot.active,
            reason=snapshot.reason,
            updated_by=snapshot.updated_by,
            updated_at_ms=snapshot.updated_at_ms,
            source=snapshot.source,
        )

    @classmethod
    def _validate_snapshot(
        cls,
        snapshot: GlobalKillSwitchStateSnapshot,
    ) -> Optional[str]:
        if not isinstance(getattr(snapshot, "active", None), bool):
            return GLOBAL_KILL_SWITCH_CORRUPT_REASON
        reason = getattr(snapshot, "reason", None)
        if reason is not None and not isinstance(reason, str):
            return GLOBAL_KILL_SWITCH_CORRUPT_REASON
        updated_by = getattr(snapshot, "updated_by", None)
        if not isinstance(updated_by, str) or not updated_by.strip():
            return GLOBAL_KILL_SWITCH_CORRUPT_REASON
        updated_at_ms = getattr(snapshot, "updated_at_ms", None)
        if not isinstance(updated_at_ms, int) or updated_at_ms <= 0:
            return GLOBAL_KILL_SWITCH_CORRUPT_REASON
        source = getattr(snapshot, "source", None)
        if not isinstance(source, str) or not source.strip():
            return GLOBAL_KILL_SWITCH_CORRUPT_REASON
        if snapshot.active is False and reason in _FAIL_CLOSED_STATE_REASONS:
            return GLOBAL_KILL_SWITCH_CONFLICTING_REASON
        return None

    @classmethod
    def _fail_closed_state(cls, *, reason: str, source: str) -> GlobalKillSwitchState:
        return GlobalKillSwitchState(
            active=True,
            reason=reason,
            updated_by="system",
            updated_at_ms=cls._now_ms(),
            source=source,
        )

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
