"""External/manual close consumer for reconciliation read models."""

from __future__ import annotations

from typing import Any, Optional

from src.infrastructure.logger import logger


EXTERNAL_CLOSE_DETECTED = "EXTERNAL_CLOSE_DETECTED"
POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED = "POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED"


class ExternalCloseMonitor:
    """Handle local-active/exchange-flat reconciliation facts.

    This is deliberately conservative. It updates only the local position
    projection to unresolved-closed, blocks future entries for the symbol, and
    emits audit context. It never places, cancels, edits, or closes exchange
    orders.
    """

    def __init__(
        self,
        *,
        execution_orchestrator: Any,
        position_projection_service: Any,
        trace_service: Optional[Any] = None,
    ) -> None:
        self._execution_orchestrator = execution_orchestrator
        self._position_projection_service = position_projection_service
        self._trace_service = trace_service
        self._handled_keys: set[tuple[str, str, str]] = set()

    async def handle_read_model_result(self, result: Any, *, source: str) -> None:
        for mismatch in list(getattr(result, "mismatches", []) or []):
            if getattr(mismatch, "mismatch_type", None) != "local_position_missing_on_exchange":
                continue
            if getattr(mismatch, "severity", None) not in {"SEVERE", "CRITICAL"}:
                continue
            symbol = getattr(mismatch, "symbol", None) or getattr(result, "symbol", "unknown")
            local_ref = getattr(mismatch, "local_ref", None) or symbol
            key = (symbol, local_ref, source)
            metadata = self._metadata(mismatch, symbol, source)
            closed_positions = await self._position_projection_service.mark_external_close_unresolved(
                symbol=symbol,
                reason=POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
                source=source,
                metadata=metadata,
            )
            self._block_symbol(symbol, metadata)
            self._emit_trace(symbol, metadata)
            if key not in self._handled_keys:
                self._handled_keys.add(key)
                logger.error(
                    "External close detected from reconciliation: symbol=%s local_ref=%s "
                    "closed_positions=%s source=%s reason=%s metadata=%s",
                    symbol,
                    local_ref,
                    [getattr(position, "id", None) for position in closed_positions],
                    source,
                    POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
                    metadata,
                )

    def _metadata(self, mismatch: Any, symbol: str, source: str) -> dict[str, Any]:
        base_metadata = getattr(mismatch, "metadata", None) or {}
        return {
            "symbol": symbol,
            "source": source,
            "mismatch_type": getattr(mismatch, "mismatch_type", None),
            "local_ref": getattr(mismatch, "local_ref", None),
            "exchange_ref": getattr(mismatch, "exchange_ref", None),
            "local_position_id": base_metadata.get("local_position_id"),
            "local_qty": base_metadata.get("local_qty"),
            "exchange_qty": base_metadata.get("exchange_qty"),
            "reason": POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
            "event_type": EXTERNAL_CLOSE_DETECTED,
            "action": "block_new_entries",
            "pnl_status": "unresolved_no_reliable_fill",
        }

    def _block_symbol(self, symbol: str, metadata: dict[str, Any]) -> None:
        blocker = getattr(
            self._execution_orchestrator,
            "block_symbol_for_protection_health",
            None,
        )
        if blocker is None:
            logger.error(
                "External close monitor cannot block symbol: helper unavailable symbol=%s",
                symbol,
            )
            return
        blocker(symbol, POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED, metadata)

    def _emit_trace(self, symbol: str, metadata: dict[str, Any]) -> None:
        if self._trace_service is None:
            return
        try:
            self._trace_service.emit_risk_decision(
                lifecycle_id=f"external_close:{symbol}",
                event_type="control.external_close_detected",
                decision="deny_new_entries",
                reason=POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
                metadata=metadata,
                config_hash=metadata.get("config_hash"),
            )
        except Exception as exc:
            logger.warning("External close trace emit failed: %s", exc, exc_info=True)
