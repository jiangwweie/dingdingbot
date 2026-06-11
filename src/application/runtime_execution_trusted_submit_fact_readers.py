"""Read-only source readers for runtime trusted submit fact snapshots."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsSourceType,
    TrialReadinessAccountFactsSource,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanStatus,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedFactFreshness,
    RuntimeExecutionTrustedSubmitFactSource,
)


DEFAULT_LOCAL_FACT_MAX_AGE_MS = 5 * 60 * 1000


class TrialReadinessAccountTrustedSubmitFactReader:
    """Adapt trial-readiness account facts into trusted submit facts."""

    def __init__(
        self,
        account_facts_source: TrialReadinessAccountFactsSource | None,
        *,
        max_age_ms: int = DEFAULT_LOCAL_FACT_MAX_AGE_MS,
    ) -> None:
        self._account_facts_source = account_facts_source
        self._max_age_ms = max_age_ms

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        execution_intent_id: str,
        runtime_instance_id: str | None,
        order_candidate_id: str | None,
        symbol: str,
        side: str | None,
        now_ms: int,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        if self._account_facts_source is None:
            return _missing_source(
                key,
                source_id="trial_readiness_account_facts_source_unavailable",
                source_type="trial_readiness_account_facts",
                now_ms=now_ms,
                metadata={"reason": "account_facts_source_unavailable"},
            )
        facts = await self._account_facts_source.read_trial_readiness_account_facts(
            candidate_id=order_candidate_id or execution_intent_id,
            symbol=symbol,
            side=side or "unknown",
            generated_at_ms=now_ms,
        )
        source_type = getattr(facts.source_type, "value", str(facts.source_type))
        read_only = bool(facts.read_only_guarantee) and (
            facts.external_call_type in {"none", "read_only_account_query"}
        )
        freshness = _account_freshness_to_trusted(
            facts.freshness_status,
            timestamp_ms=facts.timestamp_ms,
        )
        if facts.source_type == AccountFactsSourceType.UNAVAILABLE:
            freshness = RuntimeExecutionTrustedFactFreshness.MISSING
        max_age_ms = (
            self._max_age_ms
            if freshness == RuntimeExecutionTrustedFactFreshness.FRESH
            else None
        )
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=facts.source_id or "trial_readiness_account_facts",
            source_type=f"trial_readiness_account_facts:{source_type}",
            trusted=read_only,
            freshness=freshness,
            observed_at_ms=facts.timestamp_ms,
            max_age_ms=max_age_ms,
            read_only=read_only,
            metadata={
                "runtime_instance_id": runtime_instance_id,
                "account_equity_present": facts.account_equity is not None,
                "available_margin_present": facts.available_margin is not None,
                "reconciliation_status": getattr(
                    facts.reconciliation_status,
                    "value",
                    str(facts.reconciliation_status),
                ),
                "readiness_blockers": list(facts.readiness_blockers()),
                "external_call_performed": facts.external_call_performed,
                "external_call_type": facts.external_call_type,
            },
        )


class LocalActivePositionTrustedSubmitFactReader:
    """Read active-position facts from a local projection repository."""

    def __init__(
        self,
        active_position_source: Any,
        *,
        max_age_ms: int = DEFAULT_LOCAL_FACT_MAX_AGE_MS,
        limit: int = 100,
    ) -> None:
        self._active_position_source = active_position_source
        self._max_age_ms = max_age_ms
        self._limit = limit

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        symbol: str,
        now_ms: int,
        **_kwargs: Any,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        list_active = getattr(self._active_position_source, "list_active", None)
        if not callable(list_active):
            return _missing_source(
                key,
                source_id="local_active_position_source_unavailable",
                source_type="local_position_projection",
                now_ms=now_ms,
                metadata={"reason": "list_active_unavailable"},
            )
        try:
            positions = await list_active(symbol=symbol, limit=self._limit)
        except Exception as exc:  # pragma: no cover - repository owned.
            return _missing_source(
                key,
                source_id="local_active_position_read_failed",
                source_type="local_position_projection",
                now_ms=now_ms,
                metadata={"read_error": type(exc).__name__},
            )
        return _fresh_source(
            key,
            source_id=f"local-active-position:{symbol}:{len(positions)}",
            source_type="local_position_projection",
            now_ms=now_ms,
            max_age_ms=self._max_age_ms,
            metadata={
                "symbol": symbol,
                "active_position_count": len(positions),
                "position_refs": _object_refs(positions),
            },
        )


class LocalOpenOrderTrustedSubmitFactReader:
    """Read local open-order facts from the order repository."""

    def __init__(
        self,
        order_source: Any,
        *,
        max_age_ms: int = DEFAULT_LOCAL_FACT_MAX_AGE_MS,
    ) -> None:
        self._order_source = order_source
        self._max_age_ms = max_age_ms

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        symbol: str,
        now_ms: int,
        **_kwargs: Any,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        get_open_orders = getattr(self._order_source, "get_open_orders", None)
        if not callable(get_open_orders):
            return _missing_source(
                key,
                source_id="local_open_order_source_unavailable",
                source_type="local_order_repository",
                now_ms=now_ms,
                metadata={"reason": "get_open_orders_unavailable"},
            )
        try:
            orders = await get_open_orders(symbol)
        except Exception as exc:  # pragma: no cover - repository owned.
            return _missing_source(
                key,
                source_id="local_open_order_read_failed",
                source_type="local_order_repository",
                now_ms=now_ms,
                metadata={"read_error": type(exc).__name__},
            )
        return _fresh_source(
            key,
            source_id=f"local-open-order:{symbol}:{len(orders)}",
            source_type="local_order_repository",
            now_ms=now_ms,
            max_age_ms=self._max_age_ms,
            metadata={
                "symbol": symbol,
                "open_order_count": len(orders),
                "open_order_refs": _object_refs(orders),
            },
        )


class RuntimeProtectionPlanTrustedSubmitFactReader:
    """Read the recorded runtime protection plan for an intent."""

    def __init__(
        self,
        protection_plan_repository: Any,
        *,
        max_age_ms: int = DEFAULT_LOCAL_FACT_MAX_AGE_MS,
    ) -> None:
        self._protection_plan_repository = protection_plan_repository
        self._max_age_ms = max_age_ms

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        execution_intent_id: str,
        now_ms: int,
        **_kwargs: Any,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        get = getattr(self._protection_plan_repository, "get", None)
        if not callable(get):
            return _missing_source(
                key,
                source_id="runtime_protection_plan_repository_unavailable",
                source_type="runtime_protection_plan",
                now_ms=now_ms,
                metadata={"reason": "protection_plan_repository_unavailable"},
            )
        plan_id = f"runtime-protection-plan-{execution_intent_id}"
        plan = await get(plan_id)
        if plan is None:
            return _missing_source(
                key,
                source_id=plan_id,
                source_type="runtime_protection_plan",
                now_ms=now_ms,
                metadata={"reason": "protection_plan_not_found"},
            )
        status_value = getattr(getattr(plan, "status", None), "value", None)
        ready = (
            getattr(plan, "status", None)
            == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER
        )
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=plan_id,
            source_type="runtime_protection_plan",
            freshness=(
                RuntimeExecutionTrustedFactFreshness.FRESH
                if ready
                else RuntimeExecutionTrustedFactFreshness.STALE
            ),
            observed_at_ms=getattr(plan, "created_at_ms", now_ms),
            max_age_ms=self._max_age_ms if ready else None,
            metadata={
                "protection_plan_status": (
                    status_value or str(getattr(plan, "status", "unknown"))
                ),
                "requires_protection": getattr(plan, "requires_protection", None),
                "stop_price_reference_present": (
                    getattr(plan, "stop_price_reference", None) is not None
                ),
                "take_profit_reference_count": len(
                    getattr(plan, "take_profit_references", []) or []
                ),
                "blockers": list(getattr(plan, "blockers", []) or []),
            },
        )


class ConfiguredMarketRuleTrustedSubmitFactReader:
    """Read market-rule facts from an injected read-only snapshot provider."""

    def __init__(
        self,
        market_rule_provider: Mapping[str, Any] | Callable[..., Any] | None,
        *,
        max_age_ms: int = DEFAULT_LOCAL_FACT_MAX_AGE_MS,
    ) -> None:
        self._market_rule_provider = market_rule_provider
        self._max_age_ms = max_age_ms

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        symbol: str,
        now_ms: int,
        **_kwargs: Any,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        if self._market_rule_provider is None:
            return _missing_source(
                key,
                source_id="configured_market_rule_source_unavailable",
                source_type="configured_market_rule_snapshot",
                now_ms=now_ms,
                metadata={"reason": "market_rule_provider_unavailable"},
            )
        snapshot = await _resolve_provider(self._market_rule_provider, symbol)
        if snapshot is None:
            return _missing_source(
                key,
                source_id=f"configured-market-rule:{symbol}:missing",
                source_type="configured_market_rule_snapshot",
                now_ms=now_ms,
                metadata={"reason": "market_rule_snapshot_missing"},
            )
        observed_at_ms = _int_or_none(_get(snapshot, "observed_at_ms"))
        freshness = (
            RuntimeExecutionTrustedFactFreshness.FRESH
            if observed_at_ms is not None
            else RuntimeExecutionTrustedFactFreshness.MISSING
        )
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=str(
                _get(snapshot, "source_id") or f"configured-market-rule:{symbol}"
            ),
            source_type=str(
                _get(snapshot, "source_type") or "configured_market_rule_snapshot"
            ),
            freshness=freshness,
            observed_at_ms=observed_at_ms,
            max_age_ms=(
                self._max_age_ms
                if freshness == RuntimeExecutionTrustedFactFreshness.FRESH
                else None
            ),
            metadata={
                "symbol": symbol,
                "has_min_qty": _get(snapshot, "min_qty") is not None,
                "has_tick_size": _get(snapshot, "tick_size") is not None,
                "has_price_precision": _get(snapshot, "price_precision") is not None,
                "has_quantity_precision": (
                    _get(snapshot, "quantity_precision") is not None
                ),
            },
        )


class StartupReconciliationTrustedSubmitFactReader:
    """Read reconciliation status from an injected startup/read-model summary."""

    def __init__(
        self,
        summary_provider: Mapping[str, Any] | Callable[[], Any] | Any,
        *,
        max_age_ms: int = DEFAULT_LOCAL_FACT_MAX_AGE_MS,
    ) -> None:
        self._summary_provider = summary_provider
        self._max_age_ms = max_age_ms

    async def read_trusted_submit_fact_source(
        self,
        *,
        key: str,
        symbol: str,
        now_ms: int,
        **_kwargs: Any,
    ) -> RuntimeExecutionTrustedSubmitFactSource:
        summary = await _resolve_zero_arg_provider(self._summary_provider)
        if summary is None:
            return _missing_source(
                key,
                source_id="startup_reconciliation_summary_unavailable",
                source_type="startup_reconciliation_summary",
                now_ms=now_ms,
                metadata={"reason": "reconciliation_summary_unavailable"},
            )
        observed_at_ms = (
            _int_or_none(_get(summary, "checked_at_ms"))
            or _int_or_none(_get(summary, "completed_at_ms"))
            or _int_or_none(_get(summary, "timestamp_ms"))
            or _int_or_none(_get(summary, "reconciliation_time"))
        )
        clean = _summary_is_clean(summary)
        freshness = RuntimeExecutionTrustedFactFreshness.FRESH
        if not clean:
            freshness = RuntimeExecutionTrustedFactFreshness.STALE
        if observed_at_ms is None:
            freshness = RuntimeExecutionTrustedFactFreshness.MISSING
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=str(_get(summary, "report_id") or f"startup-reconciliation:{symbol}"),
            source_type="startup_reconciliation_summary",
            freshness=freshness,
            observed_at_ms=observed_at_ms,
            max_age_ms=(
                self._max_age_ms
                if freshness == RuntimeExecutionTrustedFactFreshness.FRESH
                else None
            ),
            metadata={
                "symbol": symbol,
                "clean": clean,
                "status": _summary_status(summary),
                "failed_reconciliations_count": _int_or_none(
                    _get(summary, "failed_reconciliations_count")
                ),
                "total_discrepancies": _int_or_none(
                    _get(summary, "total_discrepancies")
                ),
            },
        )


def _fresh_source(
    key: str,
    *,
    source_id: str,
    source_type: str,
    now_ms: int,
    max_age_ms: int,
    metadata: dict[str, Any],
) -> RuntimeExecutionTrustedSubmitFactSource:
    return RuntimeExecutionTrustedSubmitFactSource(
        key=key,
        source_id=source_id,
        source_type=source_type,
        freshness=RuntimeExecutionTrustedFactFreshness.FRESH,
        observed_at_ms=now_ms,
        max_age_ms=max_age_ms,
        metadata=metadata,
    )


def _missing_source(
    key: str,
    *,
    source_id: str,
    source_type: str,
    now_ms: int,
    metadata: dict[str, Any],
) -> RuntimeExecutionTrustedSubmitFactSource:
    return RuntimeExecutionTrustedSubmitFactSource(
        key=key,
        source_id=source_id,
        source_type=source_type,
        freshness=RuntimeExecutionTrustedFactFreshness.MISSING,
        observed_at_ms=now_ms,
        max_age_ms=None,
        metadata=metadata,
    )


def _account_freshness_to_trusted(
    freshness: AccountFactsFreshnessStatus,
    *,
    timestamp_ms: int | None,
) -> RuntimeExecutionTrustedFactFreshness:
    if timestamp_ms is None:
        return RuntimeExecutionTrustedFactFreshness.MISSING
    if freshness == AccountFactsFreshnessStatus.FRESH:
        return RuntimeExecutionTrustedFactFreshness.FRESH
    if freshness == AccountFactsFreshnessStatus.STALE:
        return RuntimeExecutionTrustedFactFreshness.STALE
    return RuntimeExecutionTrustedFactFreshness.MISSING


def _object_refs(items: list[Any]) -> list[str]:
    refs: list[str] = []
    for item in items:
        ref = getattr(item, "id", None)
        if ref is None and isinstance(item, Mapping):
            ref = item.get("id")
        if ref is not None:
            refs.append(str(ref))
    return refs


async def _resolve_provider(
    provider: Mapping[str, Any] | Callable[..., Any],
    symbol: str,
) -> Any:
    if isinstance(provider, Mapping):
        return provider.get(symbol) or provider.get("default")
    try:
        result = provider(symbol)
    except TypeError:
        result = provider()
    if inspect.isawaitable(result):
        return await result
    return result


async def _resolve_zero_arg_provider(provider: Any) -> Any:
    if callable(provider):
        result = provider()
        if inspect.isawaitable(result):
            return await result
        return result
    return provider


def _get(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _summary_status(summary: Any) -> str:
    for key in ("status", "reconciliation_status", "state"):
        value = _get(summary, key)
        if value is not None:
            return str(value).lower()
    if _get(summary, "is_consistent") is True:
        return "consistent"
    if _get(summary, "is_consistent") is False:
        return "mismatch"
    return "unknown"


def _summary_is_clean(summary: Any) -> bool:
    status = _summary_status(summary)
    if status in {"clean", "consistent", "ok", "pass", "passed"}:
        return True
    if status in {"mismatch", "failed", "not_clean", "blocked"}:
        return False
    failed_count = _int_or_none(_get(summary, "failed_reconciliations_count"))
    if failed_count is not None:
        return failed_count == 0
    discrepancy_count = _int_or_none(_get(summary, "total_discrepancies"))
    if discrepancy_count is not None:
        return discrepancy_count == 0
    return False
