"""Protection-health detection consumer for reconciliation read models."""

from __future__ import annotations

import inspect
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from src.infrastructure.logger import logger


PROTECTION_MISSING_EXCHANGE_SL = "PROTECTION_MISSING_EXCHANGE_SL"
PROTECTION_EXCHANGE_POSITION_UNTRACKED = "PROTECTION_EXCHANGE_POSITION_UNTRACKED"
PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE = "PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE"
PROTECTION_ORPHAN_REDUCE_ONLY_ORDER = "PROTECTION_ORPHAN_REDUCE_ONLY_ORDER"

PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED_ENV = "PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED"
PROTECTION_HEALTH_MAX_EXTERNAL_ALERTS_PER_CHECK_ENV = (
    "PROTECTION_HEALTH_MAX_EXTERNAL_ALERTS_PER_CHECK"
)
PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE = (
    "DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE"
)
PROTECTION_POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED = (
    "POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED"
)
PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE = "PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE"

PROTECTION_HEALTH_REASON_CODES = {
    PROTECTION_MISSING_EXCHANGE_SL,
    PROTECTION_EXCHANGE_POSITION_UNTRACKED,
    PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
    PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED,
    PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE,
}


@dataclass
class _ProtectionHealthGroup:
    symbol: str
    reason_code: str
    source: str
    action: str
    severity: str
    count: int = 0
    sample_local_order_ids: list[str] = field(default_factory=list)
    sample_exchange_order_ids: list[str] = field(default_factory=list)
    has_local_position: bool = False
    has_exchange_position: bool = False
    mismatch_types: set[str] = field(default_factory=set)
    manual_recovery: Optional[str] = None


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
        external_alerts_enabled: Optional[bool] = None,
        max_external_alerts_per_check: Optional[int] = None,
    ) -> None:
        self._execution_orchestrator = execution_orchestrator
        self._trace_service = trace_service
        self._notifier = notifier
        self._max_alert_dedupe_keys = max(1, max_alert_dedupe_keys)
        self._external_alerts_enabled = (
            _env_bool(PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED_ENV, default=False)
            if external_alerts_enabled is None
            else external_alerts_enabled
        )
        self._max_external_alerts_per_check = max(
            1,
            max_external_alerts_per_check
            if max_external_alerts_per_check is not None
            else _env_int(PROTECTION_HEALTH_MAX_EXTERNAL_ALERTS_PER_CHECK_ENV, default=5),
        )
        self._alert_dedupe_keys: set[tuple[Any, ...]] = set()
        self._alert_dedupe_order: deque[tuple[Any, ...]] = deque()

    async def handle_read_model_result(self, result: Any, *, source: str) -> None:
        """Handle one reconciliation read model result."""
        groups: dict[tuple[str, str, str], _ProtectionHealthGroup] = {}
        for mismatch in list(getattr(result, "mismatches", []) or []):
            reason_code = self._extract_reason_code(mismatch)
            if reason_code is None:
                continue
            symbol = getattr(mismatch, "symbol", None) or getattr(result, "symbol", "unknown")
            metadata = self._build_metadata(mismatch, reason_code, source)
            action = "block_new_entries" if getattr(mismatch, "severity", None) == "CRITICAL" else "report_only"
            group_key = (symbol, reason_code, action)
            group = groups.get(group_key)
            if group is None:
                group = _ProtectionHealthGroup(
                    symbol=symbol,
                    reason_code=reason_code,
                    source=source,
                    action=action,
                    severity=getattr(mismatch, "severity", "UNKNOWN"),
                    manual_recovery=metadata.get("manual_recovery"),
                )
                groups[group_key] = group
            self._add_to_group(group, metadata)

        self._clear_healed_symbols(result, groups)

        external_sent = 0
        for group in groups.values():
            summary = self._group_to_summary(group)
            if group.action == "block_new_entries":
                self._block_symbol(group.symbol, group.reason_code, summary)
            self._emit_trace(group.symbol, group.reason_code, summary)
            if group.action == "block_new_entries":
                external_sent += await self._send_summary_p0_alert_once(
                    group,
                    summary,
                    external_sent=external_sent,
                )
                logger.error(
                    "Protection health critical summary: symbol=%s, reason=%s, source=%s, count=%s, action=%s, samples=%s",
                    group.symbol,
                    group.reason_code,
                    group.source,
                    group.count,
                    group.action,
                    summary,
                )
            else:
                logger.warning(
                    "Protection health data hygiene summary: symbol=%s, reason=%s, source=%s, count=%s, action=%s, samples=%s",
                    group.symbol,
                    group.reason_code,
                    group.source,
                    group.count,
                    group.action,
                    summary,
                )

    def _clear_healed_symbols(
        self,
        result: Any,
        groups: dict[tuple[str, str, str], _ProtectionHealthGroup],
    ) -> None:
        symbols = {
            getattr(result, "symbol", None),
            *[
                getattr(mismatch, "symbol", None)
                for mismatch in list(getattr(result, "mismatches", []) or [])
            ],
        }
        symbols = {symbol for symbol in symbols if symbol}
        blocked_symbols = {
            group.symbol
            for group in groups.values()
            if group.action == "block_new_entries"
        }
        clearer = getattr(
            self._execution_orchestrator,
            "clear_protection_health_block",
            None,
        )
        if clearer is None:
            return
        for symbol in sorted(symbols - blocked_symbols):
            clearer(symbol)
            logger.warning(
                "Protection health block cleared after healed read model: symbol=%s",
                symbol,
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
                event_type=(
                    "control.protection_health_block"
                    if metadata.get("action") == "block_new_entries"
                    else "risk.protection_health_check"
                ),
                decision=(
                    "deny_new_entries"
                    if metadata.get("action") == "block_new_entries"
                    else "report_only"
                ),
                reason=reason_code,
                metadata=metadata,
                config_hash=metadata.get("config_hash"),
            )
        except Exception as exc:  # pragma: no cover - TraceService normally swallows sink failures.
            logger.warning("Protection health trace emit failed: %s", exc, exc_info=True)

    async def _send_summary_p0_alert_once(
        self,
        group: _ProtectionHealthGroup,
        metadata: dict[str, Any],
        *,
        external_sent: int,
    ) -> int:
        if not self._external_alerts_enabled or self._notifier is None:
            return 0
        if external_sent >= self._max_external_alerts_per_check:
            logger.error(
                "Protection health external alert cap reached: source=%s, cap=%s, skipped_reason=%s",
                group.source,
                self._max_external_alerts_per_check,
                group.reason_code,
            )
            return 0

        dedupe_key = (
            group.source,
            group.symbol,
            group.reason_code,
            group.action,
            group.has_local_position,
            group.has_exchange_position,
        )
        if dedupe_key in self._alert_dedupe_keys:
            return 0

        self._remember_alert_dedupe_key(dedupe_key)
        title = f"[P0] Protection health block: {group.symbol}"
        message = (
            f"New entries blocked for {group.symbol}; "
            f"reason={group.reason_code}; count={group.count}; "
            f"has_local_position={group.has_local_position}; "
            f"has_exchange_position={group.has_exchange_position}; "
            f"sample_local_order_ids={metadata.get('sample_local_order_ids', [])}; "
            f"manual_recovery={metadata.get('manual_recovery')}"
        )
        try:
            result = self._notifier(title, message)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.error("Protection health P0 alert failed: %s", exc, exc_info=True)
        return 1

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

    def _add_to_group(self, group: _ProtectionHealthGroup, metadata: dict[str, Any]) -> None:
        group.count += 1
        group.has_local_position = group.has_local_position or bool(
            metadata.get("has_local_position")
        )
        group.has_exchange_position = group.has_exchange_position or bool(
            metadata.get("has_exchange_position")
        )
        mismatch_type = metadata.get("mismatch_type")
        if mismatch_type:
            group.mismatch_types.add(mismatch_type)
        _append_sample(group.sample_local_order_ids, metadata.get("local_order_id"))
        _append_sample(group.sample_exchange_order_ids, metadata.get("exchange_order_id"))
        if not group.manual_recovery:
            group.manual_recovery = metadata.get("manual_recovery")

    def _group_to_summary(self, group: _ProtectionHealthGroup) -> dict[str, Any]:
        return {
            "symbol": group.symbol,
            "reason_code": group.reason_code,
            "source": group.source,
            "action": group.action,
            "severity": group.severity,
            "count": group.count,
            "sample_local_order_ids": group.sample_local_order_ids,
            "sample_exchange_order_ids": group.sample_exchange_order_ids,
            "has_local_position": group.has_local_position,
            "has_exchange_position": group.has_exchange_position,
            "mismatch_types": sorted(group.mismatch_types),
            "manual_recovery": group.manual_recovery,
            "detected_at_ms": int(time.time() * 1000),
        }


def _append_sample(samples: list[str], value: Any) -> None:
    if value is None:
        return
    text = str(value)
    if text and text not in samples and len(samples) < 10:
        samples.append(text)


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer env for %s=%s; using default=%s", name, value, default)
        return default
