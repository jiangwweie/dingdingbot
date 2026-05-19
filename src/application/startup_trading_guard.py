"""Startup trading guard: require an explicit arm before new entries."""

from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.application.decision_trace import TraceService
from src.infrastructure.logger import logger


STARTUP_TRADING_GUARD_BLOCK_REASON = "STARTUP_TRADING_GUARD_NOT_ARMED"


class StartupTradingGuardState(BaseModel):
    """Runtime-readable startup guard state."""

    armed: bool = Field(..., description="Whether new entries may proceed past startup guard")
    reason: Optional[str] = Field(default=None, description="Operator/startup reason")
    updated_by: str = Field(default="system", description="Last writer")
    updated_at_ms: int = Field(..., description="Last update timestamp in milliseconds")
    source: str = Field(default="startup_default_block", description="State source")


class StartupTradingGuardService:
    """Fail-closed process-local guard for startup and restart safety."""

    def __init__(
        self,
        *,
        trace_service: Optional[TraceService] = None,
        config_hash: Optional[str] = None,
        default_armed: bool = False,
        reason: Optional[str] = STARTUP_TRADING_GUARD_BLOCK_REASON,
    ) -> None:
        self._trace_service = trace_service
        self._config_hash = config_hash
        self._state = StartupTradingGuardState(
            armed=default_armed,
            reason=None if default_armed else reason,
            updated_by="system",
            updated_at_ms=self._now_ms(),
            source="startup_default_armed" if default_armed else "startup_default_block",
        )
        if not default_armed:
            logger.warning(
                "[StartupTradingGuard] New entries blocked until manual arm: reason=%s",
                self._state.reason,
            )

    def get_state(self) -> StartupTradingGuardState:
        return self._state.model_copy(deep=True)

    def is_armed(self) -> bool:
        return bool(self._state.armed)

    def get_block_reason(self) -> str:
        return self._state.reason or STARTUP_TRADING_GUARD_BLOCK_REASON

    def manual_arm(
        self,
        *,
        updated_by: str,
        reason: Optional[str] = None,
    ) -> StartupTradingGuardState:
        previous_state = self.get_state()
        self._state = StartupTradingGuardState(
            armed=True,
            reason=reason,
            updated_by=updated_by,
            updated_at_ms=self._now_ms(),
            source="manual_arm",
        )
        new_state = self.get_state()
        self._emit_control_trace(
            event_type="control.startup_trading_guard_arm",
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            source="manual_arm",
        )
        logger.warning(
            "[StartupTradingGuard] Manually armed for new entries: updated_by=%s, reason=%s",
            updated_by,
            reason,
        )
        return self.get_state()

    def block(
        self,
        *,
        updated_by: str = "system",
        reason: Optional[str] = STARTUP_TRADING_GUARD_BLOCK_REASON,
        source: str = "manual_block",
    ) -> StartupTradingGuardState:
        previous_state = self.get_state()
        self._state = StartupTradingGuardState(
            armed=False,
            reason=reason or STARTUP_TRADING_GUARD_BLOCK_REASON,
            updated_by=updated_by,
            updated_at_ms=self._now_ms(),
            source=source,
        )
        new_state = self.get_state()
        self._emit_control_trace(
            event_type="control.startup_trading_guard_block",
            previous_state=previous_state,
            new_state=new_state,
            reason=self._state.reason,
            source=source,
        )
        logger.warning(
            "[StartupTradingGuard] New entries blocked: source=%s, reason=%s",
            source,
            self._state.reason,
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
            event_type="risk.startup_trading_guard_check",
            decision=decision,
            reason=reason,
            metadata={
                "armed": self._state.armed,
                "state_reason": self._state.reason,
                "state_source": self._state.source,
                "state_updated_at_ms": self._state.updated_at_ms,
                "symbol": getattr(signal, "symbol", None),
                "strategy_name": getattr(signal, "strategy_name", None),
            },
        )

    def _emit_control_trace(
        self,
        *,
        event_type: str,
        previous_state: StartupTradingGuardState,
        new_state: StartupTradingGuardState,
        reason: Optional[str],
        source: str,
    ) -> None:
        if self._trace_service is None:
            return
        self._trace_service.emit_risk_decision(
            lifecycle_id="control:startup_trading_guard",
            event_type=event_type,
            decision="allow" if new_state.armed else "deny",
            reason=reason,
            config_hash=self._config_hash,
            metadata={
                "previous_state": previous_state.model_dump(mode="json"),
                "new_state": new_state.model_dump(mode="json"),
                "source": source,
                "reason": reason,
                "timestamp": new_state.updated_at_ms,
            },
        )

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
