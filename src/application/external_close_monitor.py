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
        order_lifecycle: Optional[Any] = None,
        trace_service: Optional[Any] = None,
    ) -> None:
        self._execution_orchestrator = execution_orchestrator
        self._position_projection_service = position_projection_service
        self._order_lifecycle = order_lifecycle
        self._trace_service = trace_service
        self._handled_keys: set[tuple[str, str, str]] = set()

    async def handle_read_model_result(self, result: Any, *, source: str) -> bool:
        state_changed = False
        for mismatch in list(getattr(result, "mismatches", []) or []):
            mismatch_type = getattr(mismatch, "mismatch_type", None)
            if mismatch_type == "protection_local_sl_missing_on_exchange":
                state_changed = (
                    await self._handle_closed_position_stale_protection_mismatch(
                        mismatch,
                        source=source,
                    )
                    or state_changed
                )
                continue
            if mismatch_type != "local_position_missing_on_exchange":
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
            if closed_positions:
                state_changed = True
            stale_metadata, terminalized_count = await self._handle_stale_local_protection_orders(
                closed_positions,
                source=source,
                reason=POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
            )
            metadata.update(stale_metadata)
            if terminalized_count:
                state_changed = True
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
        return state_changed

    async def _handle_closed_position_stale_protection_mismatch(
        self,
        mismatch: Any,
        *,
        source: str,
    ) -> bool:
        metadata = getattr(mismatch, "metadata", None) or {}
        if metadata.get("has_local_position") or metadata.get("has_exchange_position"):
            return False
        local_order_id = metadata.get("local_order_id") or getattr(mismatch, "local_ref", None)
        if not local_order_id or self._order_lifecycle is None:
            return False
        get_order = getattr(self._order_lifecycle, "get_order", None)
        terminalizer = getattr(
            self._order_lifecycle,
            "mark_stale_protection_orders_after_external_close",
            None,
        )
        if get_order is None or terminalizer is None:
            return False
        try:
            order = await get_order(local_order_id)
        except Exception as exc:
            logger.warning(
                "Closed-position stale protection lookup failed: order_id=%s error=%s",
                local_order_id,
                exc,
                exc_info=True,
            )
            return False
        signal_id = getattr(order, "signal_id", None) if order is not None else None
        if not signal_id:
            return False
        try:
            terminalized = await terminalizer(
                signal_id,
                source=source,
                reason="CLOSED_POSITION_STALE_LOCAL_PROTECTION",
                metadata={
                    "local_order_id": local_order_id,
                    "mismatch_type": getattr(mismatch, "mismatch_type", None),
                    "reason": getattr(mismatch, "reason", None),
                },
            )
        except Exception as exc:
            logger.error(
                "Closed-position stale protection hygiene failed: signal_id=%s error=%s",
                signal_id,
                exc,
                exc_info=True,
            )
            return False
        if terminalized:
            logger.warning(
                "Closed-position stale local protection orders terminalized: "
                "signal_id=%s source=%s order_ids=%s",
                signal_id,
                source,
                [getattr(order, "id", "unknown") for order in terminalized],
            )
            return True
        return False

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

    async def _handle_stale_local_protection_orders(
        self,
        closed_positions: list[Any],
        *,
        source: str,
        reason: str,
    ) -> tuple[dict[str, Any], int]:
        if self._order_lifecycle is None:
            return {
                "stale_local_protection_order_ids": [],
                "stale_local_protection_order_count": 0,
                "stale_local_protection_status": "not_checked",
            }, 0

        stale_order_ids: list[str] = []
        stale_exchange_order_ids: list[str] = []
        stale_signal_ids: list[str] = []
        for position in closed_positions:
            signal_id = getattr(position, "signal_id", None)
            if not signal_id:
                continue
            stale_signal_ids.append(signal_id)
            try:
                orders = await self._order_lifecycle.get_orders_by_signal(signal_id)
            except Exception as exc:
                logger.warning(
                    "External close stale protection order lookup failed: signal_id=%s error=%s",
                    signal_id,
                    exc,
                    exc_info=True,
                )
                continue
            for order in orders:
                role = getattr(order, "order_role", None)
                status = getattr(order, "status", None)
                if (
                    role is not None
                    and getattr(role, "value", role) in {"SL", "TP1", "TP2", "TP3", "TP4", "TP5"}
                    and getattr(status, "value", status) in {"OPEN", "SUBMITTED", "PARTIALLY_FILLED"}
                ):
                    stale_order_ids.append(getattr(order, "id", "unknown"))
                    exchange_order_id = getattr(order, "exchange_order_id", None)
                    if exchange_order_id:
                        stale_exchange_order_ids.append(str(exchange_order_id))

        terminalized_order_ids: list[str] = []
        terminalized_count = 0
        terminalizer = getattr(
            self._order_lifecycle,
            "mark_stale_protection_orders_after_external_close",
            None,
        )
        if terminalizer is not None:
            for signal_id in sorted(set(stale_signal_ids)):
                try:
                    terminalized = await terminalizer(
                        signal_id,
                        source=source,
                        reason=reason,
                        metadata={
                            "stale_local_protection_order_ids": stale_order_ids[:10],
                            "stale_local_protection_exchange_order_ids": stale_exchange_order_ids[:10],
                        },
                    )
                except Exception as exc:
                    logger.error(
                        "External close local protection order hygiene failed: "
                        "signal_id=%s error=%s",
                        signal_id,
                        exc,
                        exc_info=True,
                    )
                    continue
                ids = [getattr(order, "id", "unknown") for order in terminalized]
                terminalized_order_ids.extend(ids)
                terminalized_count += len(ids)

        return {
            "stale_local_protection_order_ids": stale_order_ids[:10],
            "stale_local_protection_exchange_order_ids": stale_exchange_order_ids[:10],
            "stale_local_protection_order_count": len(stale_order_ids),
            "stale_local_protection_status": (
                "stale_after_external_close" if stale_order_ids else "none"
            ),
            "stale_local_protection_action": (
                "terminalized_local_only"
                if terminalized_count
                else ("manual_data_hygiene_required" if stale_order_ids else "none")
            ),
            "terminalized_local_protection_order_ids": terminalized_order_ids[:10],
            "terminalized_local_protection_order_count": terminalized_count,
        }, terminalized_count

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
