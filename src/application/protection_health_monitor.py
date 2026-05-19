"""Protection-health detection consumer for reconciliation read models."""

from __future__ import annotations

import inspect
import time
from collections import deque
from typing import Any, Optional

from src.infrastructure.logger import logger


PROTECTION_MISSING_EXCHANGE_SL = "PROTECTION_MISSING_EXCHANGE_SL"
PROTECTION_EXCHANGE_POSITION_UNTRACKED = "PROTECTION_EXCHANGE_POSITION_UNTRACKED"
PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE = "PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE"
PROTECTION_ORPHAN_REDUCE_ONLY_ORDER = "PROTECTION_ORPHAN_REDUCE_ONLY_ORDER"

PROTECTION_HEALTH_REASON_CODES = {
    PROTECTION_MISSING_EXCHANGE_SL,
    PROTECTION_EXCHANGE_POSITION_UNTRACKED,
    PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
}


class ProtectionHealthMonitor:
    """Convert critical protection read-model facts into new-entry blocks.

    The monitor is intentionally action-limited: it blocks future entries,
    emits trace/alerts, and logs recovery context. It does not cancel orders,
    remount protection, close positions, or call exchange mutation paths.
    """

    def __init__(
        self,
        *,
        execution_orchestrator: Any,
        trace_service: Optional[Any] = None,
        notifier: Optional[Any] = None,
        max_alert_dedupe_keys: int = 1024,
    ) -> None:
        self._execution_orchestrator = execution_orchestrator
        self._trace_service = trace_service
        self._notifier = notifier
        self._max_alert_dedupe_keys = max(1, max_alert_dedupe_keys)
        self._alert_dedupe_keys: set[tuple[Any, ...]] = set()
        self._alert_dedupe_order: deque[tuple[Any, ...]] = deque()

    async def handle_read_model_result(self, result: Any, *, source: str) -> None:
        """Handle one reconciliation read model result."""
        for mismatch in list(getattr(result, "mismatches", []) or []):
            reason_code = self._extract_reason_code(mismatch)
            if reason_code is None:
                continue
            if getattr(mismatch, "severity", None) != "CRITICAL":
                continue

            symbol = getattr(mismatch, "symbol", None) or getattr(result, "symbol", "unknown")
            metadata = self._build_metadata(mismatch, reason_code, source)
            self._block_symbol(symbol, reason_code, metadata)
            self._emit_trace(symbol, reason_code, metadata)
            await self._send_p0_alert_once(symbol, reason_code, metadata)
            logger.error(
                "Protection health critical mismatch detected: symbol=%s, reason=%s, source=%s, metadata=%s",
                symbol,
                reason_code,
                source,
                metadata,
            )

    def _extract_reason_code(self, mismatch: Any) -> Optional[str]:
        metadata = getattr(mismatch, "metadata", None) or {}
        reason_code = metadata.get("protection_reason_code") or getattr(mismatch, "reason", None)
        if reason_code in PROTECTION_HEALTH_REASON_CODES:
            return reason_code
        return None

    def _block_symbol(self, symbol: str, reason_code: str, metadata: dict[str, Any]) -> None:
        blocker = getattr(
            self._execution_orchestrator,
            "block_symbol_for_protection_health",
            None,
        )
        if blocker is None:
            logger.error(
                "Protection health monitor cannot block symbol: missing orchestrator helper, symbol=%s, reason=%s",
                symbol,
                reason_code,
            )
            return
        blocker(symbol, reason_code, metadata)

    def _emit_trace(self, symbol: str, reason_code: str, metadata: dict[str, Any]) -> None:
        if self._trace_service is None:
            return

        try:
            self._trace_service.emit_risk_decision(
                lifecycle_id=f"protection_health:{symbol}",
                event_type="control.protection_health_block",
                decision="deny_new_entries",
                reason=reason_code,
                metadata=metadata,
                config_hash=metadata.get("config_hash"),
            )
        except Exception as exc:  # pragma: no cover - TraceService normally swallows sink failures.
            logger.warning("Protection health trace emit failed: %s", exc, exc_info=True)

    async def _send_p0_alert_once(
        self,
        symbol: str,
        reason_code: str,
        metadata: dict[str, Any],
    ) -> None:
        if self._notifier is None:
            return

        dedupe_key = (
            symbol,
            reason_code,
            metadata.get("local_position_id"),
            metadata.get("local_order_id"),
            metadata.get("exchange_order_id"),
            metadata.get("exchange_position_qty"),
        )
        if dedupe_key in self._alert_dedupe_keys:
            return

        self._remember_alert_dedupe_key(dedupe_key)
        title = f"[P0] Protection health block: {symbol}"
        message = (
            f"New entries blocked for {symbol}; reason={reason_code}; "
            f"manual_recovery={metadata.get('manual_recovery')}"
        )
        try:
            result = self._notifier(title, message)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.error("Protection health P0 alert failed: %s", exc, exc_info=True)

    def _remember_alert_dedupe_key(self, dedupe_key: tuple[Any, ...]) -> None:
        self._alert_dedupe_keys.add(dedupe_key)
        self._alert_dedupe_order.append(dedupe_key)
        while len(self._alert_dedupe_order) > self._max_alert_dedupe_keys:
            oldest = self._alert_dedupe_order.popleft()
            self._alert_dedupe_keys.discard(oldest)

    def _build_metadata(self, mismatch: Any, reason_code: str, source: str) -> dict[str, Any]:
        raw_metadata = dict(getattr(mismatch, "metadata", None) or {})
        safe_metadata = {
            "symbol": getattr(mismatch, "symbol", raw_metadata.get("symbol")),
            "mismatch_type": getattr(mismatch, "mismatch_type", None),
            "local_position_id": raw_metadata.get("local_position_id")
            or getattr(mismatch, "local_ref", None),
            "exchange_position_qty": raw_metadata.get("exchange_position_qty"),
            "local_order_id": raw_metadata.get("local_order_id")
            or getattr(mismatch, "local_ref", None),
            "exchange_order_id": raw_metadata.get("exchange_order_id")
            or getattr(mismatch, "exchange_ref", None),
            "reduce_only": raw_metadata.get("reduce_only"),
            "source": source,
            "reason_code": reason_code,
            "detected_at_ms": int(time.time() * 1000),
            "manual_recovery": raw_metadata.get(
                "manual_recovery",
                "Inspect local position/order state and exchange positions/open orders before clearing the block.",
            ),
        }
        for optional_key in ("position_side", "exchange_order_type", "order_role", "config_hash"):
            if optional_key in raw_metadata:
                safe_metadata[optional_key] = raw_metadata[optional_key]
        return {key: value for key, value in safe_metadata.items() if value is not None}
