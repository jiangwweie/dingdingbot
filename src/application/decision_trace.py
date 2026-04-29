"""Minimal decision trace backbone for lifecycle traceability."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.logger import logger


class TraceEvent(BaseModel):
    """Minimal trace event envelope for runtime decisions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    trace_id: str = Field(..., description="Unique trace identifier for this event")
    lifecycle_id: str = Field(..., description="Logical lifecycle identifier")
    event_type: str = Field(..., description="Event type, such as risk.pre_order_check")
    decision: str = Field(..., description="Decision outcome, such as allow or deny")
    reason: Optional[str] = Field(default=None, description="Short decision reason code")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Structured decision context")
    config_hash: Optional[str] = Field(default=None, description="Resolved runtime config hash if available")
    emitted_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class TraceSink(Protocol):
    """Sink protocol for writing trace events."""

    def emit(self, event: TraceEvent) -> None:
        """Persist a trace event."""


class TraceService:
    """Best-effort trace service that fans events out to sinks."""

    def __init__(self, sinks: Optional[Sequence[TraceSink]] = None):
        self._sinks = list(sinks or [])

    def emit(self, event: TraceEvent) -> None:
        """Emit one event to all configured sinks without affecting callers on failure."""
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Trace sink emit failed: {exc}")

    def emit_risk_decision(
        self,
        *,
        lifecycle_id: Optional[str],
        decision: str,
        reason: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
        config_hash: Optional[str] = None,
        event_type: str = "risk.pre_order_check",
    ) -> TraceEvent:
        """Create and emit a normalized risk decision event."""
        event = TraceEvent(
            trace_id=uuid.uuid4().hex,
            lifecycle_id=lifecycle_id or self.build_lifecycle_id(event_type),
            event_type=event_type,
            decision=decision,
            reason=reason,
            metadata=metadata or {},
            config_hash=config_hash,
        )
        self.emit(event)
        return event

    @staticmethod
    def build_lifecycle_id(prefix: str) -> str:
        """Build a simple lifecycle id for callers without one yet."""
        return f"{prefix}:{uuid.uuid4().hex}"
