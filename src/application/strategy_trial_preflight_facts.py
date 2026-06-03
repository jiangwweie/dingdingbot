"""Read-only preflight fact collection for strategy trial rehearsal readiness.

The collector is intentionally dependency-injected. It can inspect already-bound
runtime/PG read paths, but it cannot create execution intents, place orders,
grant permissions, or start runtime.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from src.application.strategy_trial_readiness import (
    StrategyProfile,
    TrialReadinessPreflightInput,
)


FactStatus = Literal[
    "clear",
    "blocked",
    "stale",
    "unknown",
    "unavailable",
    "required_before_rehearsal",
    "not_checked",
]
PreflightFactId = Literal[
    "active_position",
    "open_order",
    "gks",
    "startup_guard",
    "reconciliation",
    "account_facts",
]

FactReader = Callable[[StrategyProfile], Awaitable[Any] | Any]


class TrialPreflightFact(BaseModel):
    fact_id: PreflightFactId
    status: FactStatus
    source: str
    blocking: bool
    blocker: Optional[str] = None
    blockers: list[str] = Field(default_factory=list)
    observed_at_ms: Optional[int] = None
    evidence: dict[str, str | int | bool | None] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class TrialPreflightFactsSnapshot(BaseModel):
    generated_at_ms: int
    candidate_id: str
    symbol: str
    side: str
    facts: list[TrialPreflightFact]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    live_ready: Literal[False] = False

    def fact_map(self) -> dict[str, TrialPreflightFact]:
        return {fact.fact_id: fact for fact in self.facts}

    def to_preflight_input(
        self,
        *,
        requested_mode: Literal["observe_only", "owner_confirm_each_entry", "auto_within_budget"],
        owner_authorized_testnet_rehearsal: bool = False,
    ) -> TrialReadinessPreflightInput:
        facts = self.fact_map()
        return TrialReadinessPreflightInput(
            requested_symbol=self.symbol,
            requested_side=self.side,
            requested_mode=requested_mode,
            owner_authorized_testnet_rehearsal=owner_authorized_testnet_rehearsal,
            active_conflicting_position_status=_position_preflight_status(
                facts["active_position"]
            ),
            open_conflicting_order_status=_order_preflight_status(facts["open_order"]),
            gks_status=_gks_preflight_status(facts["gks"]),
            startup_guard_status=_startup_guard_preflight_status(
                facts["startup_guard"]
            ),
            reconciliation_status=_reconciliation_preflight_status(
                facts["reconciliation"]
            ),
            account_facts_status=_account_facts_preflight_status(
                facts["account_facts"]
            ),
        )

    def to_response_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TrialPreflightFactCollector:
    """Collect rehearsal preflight facts through injected read-only readers."""

    def __init__(
        self,
        *,
        position_reader: Optional[FactReader] = None,
        open_order_reader: Optional[FactReader] = None,
        gks_reader: Optional[FactReader] = None,
        startup_guard_reader: Optional[FactReader] = None,
        reconciliation_reader: Optional[FactReader] = None,
        account_facts_reader: Optional[FactReader] = None,
    ) -> None:
        self._position_reader = position_reader
        self._open_order_reader = open_order_reader
        self._gks_reader = gks_reader
        self._startup_guard_reader = startup_guard_reader
        self._reconciliation_reader = reconciliation_reader
        self._account_facts_reader = account_facts_reader

    async def collect(self, profile: StrategyProfile) -> TrialPreflightFactsSnapshot:
        generated_at_ms = _now_ms()
        facts = [
            await self._collect_active_position(profile, generated_at_ms),
            await self._collect_open_order(profile, generated_at_ms),
            await self._collect_gks(profile, generated_at_ms),
            await self._collect_startup_guard(profile, generated_at_ms),
            await self._collect_reconciliation(profile, generated_at_ms),
            await self._collect_account_facts(profile, generated_at_ms),
        ]
        blockers: list[str] = []
        for fact in facts:
            blockers.extend(fact.blockers)
            if fact.blocker:
                blockers.append(fact.blocker)
        return TrialPreflightFactsSnapshot(
            generated_at_ms=generated_at_ms,
            candidate_id=profile.candidate_id,
            symbol=profile.symbol,
            side=profile.side,
            facts=facts,
            blockers=blockers,
            warnings=[],
        )

    async def _collect_active_position(
        self,
        profile: StrategyProfile,
        generated_at_ms: int,
    ) -> TrialPreflightFact:
        if self._position_reader is None:
            return _unavailable(
                "active_position",
                "active_position_check_required_before_rehearsal",
                generated_at_ms,
                "no active position read-only source was injected",
            )
        try:
            positions = await _maybe_await(self._position_reader(profile))
        except Exception as exc:
            return _unavailable(
                "active_position",
                "active_position_check_required_before_rehearsal",
                generated_at_ms,
                f"active position read failed: {type(exc).__name__}",
            )
        count = len(list(positions or []))
        if count:
            return TrialPreflightFact(
                fact_id="active_position",
                status="blocked",
                source="read_only_position_reader",
                blocking=True,
                blocker="conflicting_position_exists",
                observed_at_ms=generated_at_ms,
                evidence={"active_position_count": count},
                notes=["Existing active position blocks same-path rehearsal."],
            )
        return _clear(
            "active_position",
            generated_at_ms,
            "read_only_position_reader",
            {"active_position_count": 0},
        )

    async def _collect_open_order(
        self,
        profile: StrategyProfile,
        generated_at_ms: int,
    ) -> TrialPreflightFact:
        if self._open_order_reader is None:
            return _unavailable(
                "open_order",
                "open_order_check_required_before_rehearsal",
                generated_at_ms,
                "no open order read-only source was injected",
            )
        try:
            orders = await _maybe_await(self._open_order_reader(profile))
        except Exception as exc:
            return _unavailable(
                "open_order",
                "open_order_check_required_before_rehearsal",
                generated_at_ms,
                f"open order read failed: {type(exc).__name__}",
            )
        count = len(list(orders or []))
        if count:
            return TrialPreflightFact(
                fact_id="open_order",
                status="blocked",
                source="read_only_order_reader",
                blocking=True,
                blocker="conflicting_open_order_exists",
                observed_at_ms=generated_at_ms,
                evidence={"open_order_count": count},
                notes=["Existing open order blocks same-path rehearsal."],
            )
        return _clear(
            "open_order",
            generated_at_ms,
            "read_only_order_reader",
            {"open_order_count": 0},
        )

    async def _collect_gks(
        self,
        profile: StrategyProfile,
        generated_at_ms: int,
    ) -> TrialPreflightFact:
        if self._gks_reader is None:
            return _unavailable(
                "gks",
                "gks_status_required_before_rehearsal",
                generated_at_ms,
                "no GKS read-only source was injected",
            )
        try:
            state = await _maybe_await(self._gks_reader(profile))
        except Exception as exc:
            return _unavailable(
                "gks",
                "gks_status_required_before_rehearsal",
                generated_at_ms,
                f"GKS read failed: {type(exc).__name__}",
            )
        active = _get_bool(state, "active")
        state_name = str(
            _get_value(state, "state")
            or _get_value(state, "status")
            or ""
        ).lower()
        source = str(_get_value(state, "source") or "read_only_gks_reader")
        observed_at_ms = _get_int(state, "updated_at_ms") or generated_at_ms
        if state_name in {"unavailable", "not_started", "not_available"}:
            return TrialPreflightFact(
                fact_id="gks",
                status="unavailable",
                source=source,
                blocking=True,
                blocker="gks_unavailable",
                blockers=["gks_unavailable"],
                observed_at_ms=observed_at_ms,
                evidence={
                    "state": state_name or "unavailable",
                    "active": active,
                    "reason": _get_str(state, "reason"),
                },
                notes=["GKS state is unavailable and cannot be assumed clear."],
            )
        if active is True:
            return TrialPreflightFact(
                fact_id="gks",
                status="blocked",
                source=source,
                blocking=True,
                blocker="gks_blocked",
                observed_at_ms=observed_at_ms,
                evidence={"active": True},
                notes=["GKS active=True means new entries are blocked."],
            )
        if active is False:
            evidence: dict[str, str | int | bool | None] = {"active": False}
            for key in [
                "global_active",
                "scoped_clearance_valid",
                "authorization_id",
                "clearance_id",
                "expires_at_ms",
                "scope_match",
            ]:
                value = _get_value(state, key)
                if isinstance(value, (str, int, bool)) or value is None:
                    evidence[key] = value
            return _clear(
                "gks",
                observed_at_ms,
                source,
                evidence,
            )
        return _unavailable(
            "gks",
            "gks_status_required_before_rehearsal",
            generated_at_ms,
            "GKS state did not expose boolean active",
        )

    async def _collect_startup_guard(
        self,
        profile: StrategyProfile,
        generated_at_ms: int,
    ) -> TrialPreflightFact:
        if self._startup_guard_reader is None:
            return _unavailable(
                "startup_guard",
                "startup_guard_status_required_before_rehearsal",
                generated_at_ms,
                "no startup guard read-only source was injected",
            )
        try:
            state = await _maybe_await(self._startup_guard_reader(profile))
        except Exception as exc:
            return _unavailable(
                "startup_guard",
                "startup_guard_status_required_before_rehearsal",
                generated_at_ms,
                f"startup guard read failed: {type(exc).__name__}",
            )
        armed = _get_bool(state, "armed")
        state_name = str(
            _get_value(state, "state")
            or _get_value(state, "status")
            or ""
        ).lower()
        source = str(_get_value(state, "source") or "read_only_startup_guard_reader")
        observed_at_ms = _get_int(state, "updated_at_ms") or generated_at_ms
        runtime_started = _get_bool(state, "runtime_started")
        runtime_safety_context_bound = _get_bool(state, "runtime_safety_context_bound")
        runtime_state = _get_str(state, "runtime_state")
        reason = _get_str(state, "reason") or _get_str(state, "block_reason")
        if state_name in {"unavailable", "not_available"}:
            return TrialPreflightFact(
                fact_id="startup_guard",
                status="unavailable",
                source=source,
                blocking=True,
                blocker="startup_guard_unavailable",
                blockers=["startup_guard_unavailable"],
                observed_at_ms=observed_at_ms,
                evidence={
                    "armed": armed,
                    "runtime_started": runtime_started,
                    "runtime_safety_context_bound": runtime_safety_context_bound,
                    "runtime_state": runtime_state or state_name,
                    "reason": reason,
                },
                notes=["Startup guard state is unavailable and cannot be assumed clear."],
            )
        if (
            (runtime_started is False and runtime_safety_context_bound is not True)
            or runtime_state in {"not_started", "stopped"}
            or state_name in {"not_started", "stopped"}
        ):
            return TrialPreflightFact(
                fact_id="startup_guard",
                status="unavailable",
                source=source,
                blocking=True,
                blocker="startup_guard_runtime_not_started",
                blockers=["startup_guard_runtime_not_started"],
                observed_at_ms=observed_at_ms,
                evidence={
                    "armed": armed,
                    "runtime_started": runtime_started,
                    "runtime_safety_context_bound": runtime_safety_context_bound,
                    "runtime_state": runtime_state or state_name,
                    "reason": reason,
                },
                notes=["Startup guard runtime state is not started and cannot be assumed clear."],
            )
        if armed is True:
            evidence = {
                "armed": True,
                "runtime_started": runtime_started,
                "runtime_safety_context_bound": runtime_safety_context_bound,
                "runtime_state": runtime_state,
                "reason": reason,
            }
            for key in [
                "scoped_arm_valid",
                "authorization_id",
                "clearance_id",
                "expires_at_ms",
                "scope_match",
            ]:
                value = _get_value(state, key)
                if isinstance(value, (str, int, bool)) or value is None:
                    evidence[key] = value
            return _clear(
                "startup_guard",
                observed_at_ms,
                source,
                evidence,
            )
        if armed is False:
            return TrialPreflightFact(
                fact_id="startup_guard",
                status="blocked",
                source=source,
                blocking=True,
                blocker="startup_guard_blocked",
                observed_at_ms=observed_at_ms,
                evidence={
                    "armed": False,
                    "runtime_started": runtime_started,
                    "runtime_safety_context_bound": runtime_safety_context_bound,
                    "runtime_state": runtime_state,
                    "reason": reason,
                },
                notes=["Startup guard must be armed before rehearsal preflight can pass."],
            )
        return _unavailable(
            "startup_guard",
            "startup_guard_status_required_before_rehearsal",
            generated_at_ms,
            "startup guard state did not expose boolean armed",
        )

    async def _collect_reconciliation(
        self,
        profile: StrategyProfile,
        generated_at_ms: int,
    ) -> TrialPreflightFact:
        if self._reconciliation_reader is None:
            return _unavailable(
                "reconciliation",
                "reconciliation_status_required_before_rehearsal",
                generated_at_ms,
                "no reconciliation read-only source was injected",
            )
        try:
            summary = await _maybe_await(self._reconciliation_reader(profile))
        except Exception as exc:
            return _unavailable(
                "reconciliation",
                "reconciliation_status_required_before_rehearsal",
                generated_at_ms,
                f"reconciliation read failed: {type(exc).__name__}",
            )
        status = str(_get_value(summary, "status") or _get_value(summary, "reconciliation_status") or "").lower()
        source = str(_get_value(summary, "source") or "read_only_reconciliation_summary")
        failed = _get_int(summary, "failed_reconciliations_count")
        if status in {"clean", "passed", "ok"} or failed == 0:
            return _clear(
                "reconciliation",
                generated_at_ms,
                source,
                _reconciliation_evidence(summary, status or "clean", failed),
            )
        if status in {"mismatch", "failed", "dirty"} or (failed is not None and failed > 0):
            return TrialPreflightFact(
                fact_id="reconciliation",
                status="blocked",
                source=source,
                blocking=True,
                blocker="reconciliation_not_clean",
                observed_at_ms=generated_at_ms,
                evidence=_reconciliation_evidence(summary, status or "unknown", failed),
                notes=["Reconciliation is not clean."],
            )
        if status in {"unavailable", "not_started", "not_available"}:
            return TrialPreflightFact(
                fact_id="reconciliation",
                status="unavailable",
                source=source,
                blocking=True,
                blocker="reconciliation_unavailable",
                blockers=["reconciliation_unavailable"],
                observed_at_ms=generated_at_ms,
                evidence={
                    "status": status or "unavailable",
                    "failed_reconciliations_count": failed,
                    "reason": _get_str(summary, "reason"),
                },
                notes=["Reconciliation state is unavailable and cannot be assumed clean."],
            )
        return _unavailable(
            "reconciliation",
            "reconciliation_status_required_before_rehearsal",
            generated_at_ms,
            "reconciliation summary did not expose clean/mismatch status",
        )

    async def _collect_account_facts(
        self,
        profile: StrategyProfile,
        generated_at_ms: int,
    ) -> TrialPreflightFact:
        if self._account_facts_reader is None:
            return _unavailable(
                "account_facts",
                "account_facts_required_before_rehearsal",
                generated_at_ms,
                "no account facts freshness source was injected",
            )
        try:
            facts = await _maybe_await(self._account_facts_reader(profile))
        except Exception as exc:
            return _unavailable(
                "account_facts",
                "account_facts_required_before_rehearsal",
                generated_at_ms,
                f"account facts read failed: {type(exc).__name__}",
            )
        freshness = str(
            _get_value(facts, "freshness_status")
            or _get_value(facts, "freshness")
            or _get_value(facts, "account_equity_freshness")
            or ""
        ).lower()
        ready = (
            bool(_get_value(facts, "is_ready"))
            if _get_value(facts, "is_ready") is not None
            else None
        )
        timestamp_ms = _get_int(facts, "timestamp_ms") or generated_at_ms
        source = str(
            _get_value(facts, "source_type")
            or _get_value(facts, "source")
            or _get_value(facts, "account_equity_source")
            or "read_only_account_facts"
        )
        equity_available = _availability(
            facts,
            "account_equity_available",
            "wallet_equity_available",
            value_keys=("account_equity", "wallet_equity"),
        )
        margin_available = _availability(
            facts,
            "available_margin_available",
            value_keys=("available_margin",),
        )
        age_seconds = (
            max(0, (generated_at_ms - timestamp_ms) // 1000)
            if timestamp_ms is not None
            else None
        )
        reconciliation_status = str(
            _get_value(facts, "reconciliation_status")
            or _get_value(facts, "reconciliation_status_value")
            or "unknown"
        ).lower()
        evidence = {
            "freshness": freshness or "unknown",
            "age_seconds": age_seconds,
            "equity_available": equity_available,
            "available_margin_available": margin_available,
            "timestamp_ms": timestamp_ms,
            "reconciliation_status": reconciliation_status,
            "external_call_performed": _get_bool(facts, "external_call_performed"),
            "read_only_guarantee": _get_bool(facts, "read_only_guarantee"),
        }
        if (freshness == "fresh" or ready is True) and equity_available and margin_available:
            return _clear(
                "account_facts",
                timestamp_ms,
                source,
                evidence,
            )
        blockers: list[str] = []
        status: FactStatus = "required_before_rehearsal"
        primary_blocker = "account_facts_required_before_rehearsal"
        if freshness == "stale":
            status = "stale"
            primary_blocker = "account_facts_stale"
            blockers.append(primary_blocker)
        elif source == "unavailable" or freshness in {"unavailable", "missing"}:
            status = "unavailable"
            primary_blocker = "account_facts_unavailable"
            blockers.append(primary_blocker)
        elif freshness in {"unknown", ""}:
            status = "unknown"
            blockers.append(primary_blocker)
        else:
            blockers.append(primary_blocker)
        if not equity_available:
            blockers.append("account_equity_unavailable")
        if not margin_available:
            blockers.append("available_margin_unavailable")
        return TrialPreflightFact(
            fact_id="account_facts",
            status=status,
            source=source,
            blocking=True,
            blocker=primary_blocker,
            blockers=_dedupe(blockers),
            observed_at_ms=timestamp_ms,
            evidence=evidence,
            notes=["Fresh read-only account facts are required before rehearsal."],
        )


def _clear(
    fact_id: PreflightFactId,
    observed_at_ms: int,
    source: str,
    evidence: dict[str, str | int | bool | None],
) -> TrialPreflightFact:
    return TrialPreflightFact(
        fact_id=fact_id,
        status="clear",
        source=source,
        blocking=False,
        observed_at_ms=observed_at_ms,
        evidence=evidence,
    )


def _unavailable(
    fact_id: PreflightFactId,
    blocker: str,
    observed_at_ms: int,
    note: str,
) -> TrialPreflightFact:
    return TrialPreflightFact(
        fact_id=fact_id,
        status="unavailable",
        source="unavailable",
        blocking=True,
        blocker=blocker,
        blockers=[blocker],
        observed_at_ms=observed_at_ms,
        notes=[note],
    )


def _position_preflight_status(
    fact: TrialPreflightFact,
) -> Literal["clear", "blocked", "unknown", "not_checked"]:
    if fact.status == "clear":
        return "clear"
    if fact.blocker == "conflicting_position_exists":
        return "blocked"
    return "unknown"


def _order_preflight_status(
    fact: TrialPreflightFact,
) -> Literal["clear", "blocked", "unknown", "not_checked"]:
    if fact.status == "clear":
        return "clear"
    if fact.blocker == "conflicting_open_order_exists":
        return "blocked"
    return "unknown"


def _gks_preflight_status(
    fact: TrialPreflightFact,
) -> Literal["clear", "blocking", "unknown", "not_checked"]:
    if fact.status == "clear":
        return "clear"
    if fact.blocker == "gks_blocked":
        return "blocking"
    return "unknown"


def _startup_guard_preflight_status(
    fact: TrialPreflightFact,
) -> Literal["clear", "blocking", "unknown", "not_checked"]:
    if fact.status == "clear":
        return "clear"
    if fact.blocker == "startup_guard_blocked":
        return "blocking"
    return "unknown"


def _reconciliation_preflight_status(
    fact: TrialPreflightFact,
) -> Literal["clean", "mismatch", "unknown", "not_checked"]:
    if fact.status == "clear":
        return "clean"
    if fact.blocker == "reconciliation_not_clean":
        return "mismatch"
    return "unknown"


def _account_facts_preflight_status(
    fact: TrialPreflightFact,
) -> Literal["clear", "stale", "unavailable", "unknown", "not_checked"]:
    if fact.status == "clear":
        return "clear"
    if fact.status == "stale":
        return "stale"
    if fact.status in {"unavailable", "required_before_rehearsal"}:
        return "unavailable"
    return "unknown"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _get_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_bool(obj: Any, key: str) -> Optional[bool]:
    value = _get_value(obj, key)
    if isinstance(value, bool):
        return value
    return None


def _get_int(obj: Any, key: str) -> Optional[int]:
    value = _get_value(obj, key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_str(obj: Any, key: str) -> Optional[str]:
    value = _get_value(obj, key)
    if value is None:
        return None
    return str(value)


def _reconciliation_evidence(
    summary: Any,
    status: str,
    failed: Optional[int],
) -> dict[str, str | int | bool | None]:
    evidence: dict[str, str | int | bool | None] = {
        "status": status,
        "failed_reconciliations_count": failed,
    }
    for key in [
        "pg_execution_intents_count",
        "pg_blocking_execution_intents_count",
        "pg_closed_execution_intents_count",
        "retryable_failed_execution_intents_count",
        "retry_classification",
        "pg_orders_count",
        "pg_historical_closed_orders_count",
        "pg_bnb_active_position_count",
        "pg_bnb_open_order_count",
        "exchange_bnb_active_position_count",
        "exchange_bnb_open_order_count",
        "read_only",
    ]:
        value = _get_value(summary, key)
        if isinstance(value, (str, int, bool)) or value is None:
            evidence[key] = value
    return evidence


def _availability(
    obj: Any,
    *flag_keys: str,
    value_keys: tuple[str, ...],
) -> bool:
    for key in flag_keys:
        value = _get_value(obj, key)
        if isinstance(value, bool):
            return value
    for key in value_keys:
        value = _get_value(obj, key)
        if value is not None and str(value).lower() not in {"not_available", "none", ""}:
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _now_ms() -> int:
    return int(time.time() * 1000)
