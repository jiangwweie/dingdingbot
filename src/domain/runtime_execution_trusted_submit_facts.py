"""Trusted submit-time fact snapshot for runtime execution gates.

This module is pure domain logic. It records whether submit-time facts came
from trusted read-only/local sources before a future real runtime submit. It
does not read exchange data, create orders, mutate runtime state, or authorize
execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_audit_ids import BrcSemanticIds


class RuntimeExecutionTrustedSubmitFactsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionTrustedFactFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


class RuntimeExecutionTrustedSubmitFactsStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION = (
        "ready_for_first_real_submit_confirmation"
    )


class RuntimeExecutionTrustedSubmitFactSource(
    RuntimeExecutionTrustedSubmitFactsModel
):
    """A single submit-time fact source.

    `trusted=True` means the fact is sourced from a local projection,
    reconciliation readmodel, market-rule readmodel, or exchange read-only
    fact source. It must not mean an Owner/UI-supplied allow signal.
    """

    key: str = Field(min_length=1, max_length=96)
    source_id: str = Field(min_length=1, max_length=180)
    source_type: str = Field(min_length=1, max_length=128)
    trusted: bool = True
    freshness: RuntimeExecutionTrustedFactFreshness = (
        RuntimeExecutionTrustedFactFreshness.FRESH
    )
    observed_at_ms: Optional[int] = Field(default=None, ge=0)
    max_age_ms: Optional[int] = Field(default=None, ge=0)
    missing_behavior: Literal["block"] = "block"
    stale_behavior: Literal["block"] = "block"
    owner_supplied_allow_signal: bool = False
    read_only: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    not_execution_authority: Literal[True] = True
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False

    @model_validator(mode="after")
    def _reject_execution_metadata(
        self,
    ) -> "RuntimeExecutionTrustedSubmitFactSource":
        _reject_forbidden_execution_fields(
            {"metadata": self.metadata},
            artifact="trusted submit fact source",
        )
        return self


class RuntimeExecutionTrustedSubmitFactsSnapshot(
    RuntimeExecutionTrustedSubmitFactsModel
):
    trusted_submit_fact_snapshot_id: str = Field(min_length=1, max_length=240)
    execution_intent_id: str = Field(min_length=1, max_length=64)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    order_candidate_id: Optional[str] = Field(default=None, max_length=128)
    semantic_ids: BrcSemanticIds
    symbol: str = Field(min_length=1, max_length=128)
    side: Optional[str] = Field(default=None, max_length=32)
    status: RuntimeExecutionTrustedSubmitFactsStatus
    account_fact_source: Optional[RuntimeExecutionTrustedSubmitFactSource] = None
    active_position_source: Optional[RuntimeExecutionTrustedSubmitFactSource] = None
    open_order_source: Optional[RuntimeExecutionTrustedSubmitFactSource] = None
    protection_state_source: Optional[RuntimeExecutionTrustedSubmitFactSource] = None
    market_rule_source: Optional[RuntimeExecutionTrustedSubmitFactSource] = None
    reconciliation_source: Optional[RuntimeExecutionTrustedSubmitFactSource] = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_or_stale_facts_block: bool = True
    owner_supplied_allow_facts_rejected: bool = True
    facts_fresh_enough: bool
    read_only_sources_only: bool = True
    not_execution_authority: Literal[True] = True
    execution_intent_status_changed: Literal[False] = False
    runtime_state_mutated: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    order_lifecycle_called: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_metadata(
        self,
    ) -> "RuntimeExecutionTrustedSubmitFactsSnapshot":
        _reject_forbidden_execution_fields(
            {"metadata": self.metadata},
            artifact="trusted submit facts snapshot",
        )
        return self


def build_runtime_execution_trusted_submit_facts_snapshot(
    *,
    trusted_submit_fact_snapshot_id: str,
    execution_intent_id: str,
    semantic_ids: BrcSemanticIds,
    symbol: str,
    now_ms: int,
    runtime_instance_id: str | None = None,
    order_candidate_id: str | None = None,
    side: str | None = None,
    account_fact_source: RuntimeExecutionTrustedSubmitFactSource | None = None,
    active_position_source: RuntimeExecutionTrustedSubmitFactSource | None = None,
    open_order_source: RuntimeExecutionTrustedSubmitFactSource | None = None,
    protection_state_source: RuntimeExecutionTrustedSubmitFactSource | None = None,
    market_rule_source: RuntimeExecutionTrustedSubmitFactSource | None = None,
    reconciliation_source: RuntimeExecutionTrustedSubmitFactSource | None = None,
    owner_supplied_allow_facts_rejected: bool = True,
    missing_or_stale_facts_block: bool = True,
    metadata: dict[str, Any] | None = None,
) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
    blockers: list[str] = []
    warnings: list[str] = []
    sources = {
        "account_fact": account_fact_source,
        "active_position": active_position_source,
        "open_order": open_order_source,
        "protection_state": protection_state_source,
        "market_rule": market_rule_source,
        "reconciliation": reconciliation_source,
    }
    for key, source in sources.items():
        _check_source(
            key,
            source,
            now_ms=now_ms,
            blockers=blockers,
            warnings=warnings,
        )
    if not owner_supplied_allow_facts_rejected:
        blockers.append("owner_supplied_allow_facts_not_rejected")
    if not missing_or_stale_facts_block:
        blockers.append("missing_or_stale_facts_do_not_block")

    facts_fresh_enough = not any(
        source is None
        or source.freshness != RuntimeExecutionTrustedFactFreshness.FRESH
        or _source_is_age_stale(source, now_ms)
        for source in sources.values()
    )
    if not facts_fresh_enough:
        blockers.append("trusted_submit_facts_not_fresh_enough")

    status = (
        RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
        if blockers
        else RuntimeExecutionTrustedSubmitFactsStatus.READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    return RuntimeExecutionTrustedSubmitFactsSnapshot(
        trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
        execution_intent_id=execution_intent_id,
        runtime_instance_id=runtime_instance_id,
        order_candidate_id=order_candidate_id,
        semantic_ids=semantic_ids,
        symbol=symbol,
        side=side,
        status=status,
        account_fact_source=account_fact_source,
        active_position_source=active_position_source,
        open_order_source=open_order_source,
        protection_state_source=protection_state_source,
        market_rule_source=market_rule_source,
        reconciliation_source=reconciliation_source,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        missing_or_stale_facts_block=missing_or_stale_facts_block,
        owner_supplied_allow_facts_rejected=owner_supplied_allow_facts_rejected,
        facts_fresh_enough=facts_fresh_enough,
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_trusted_submit_facts",
            "non_executing_fact_gate": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange_write": True,
            **(metadata or {}),
        },
    )


def _check_source(
    key: str,
    source: RuntimeExecutionTrustedSubmitFactSource | None,
    *,
    now_ms: int,
    blockers: list[str],
    warnings: list[str],
) -> None:
    if source is None:
        blockers.append(f"trusted_{key}_source_missing")
        return
    if not source.trusted:
        blockers.append(f"trusted_{key}_source_untrusted")
    if not source.read_only:
        blockers.append(f"trusted_{key}_source_not_read_only")
    if source.owner_supplied_allow_signal:
        blockers.append(f"trusted_{key}_owner_supplied_allow_signal_rejected")
    if source.freshness == RuntimeExecutionTrustedFactFreshness.MISSING:
        blockers.append(f"trusted_{key}_fact_missing")
    if source.freshness == RuntimeExecutionTrustedFactFreshness.STALE:
        blockers.append(f"trusted_{key}_fact_stale")
    if _source_is_age_stale(source, now_ms):
        blockers.append(f"trusted_{key}_fact_age_exceeded")
    if source.observed_at_ms is None:
        warnings.append(f"trusted_{key}_observed_at_missing")


def _source_is_age_stale(
    source: RuntimeExecutionTrustedSubmitFactSource,
    now_ms: int,
) -> bool:
    if source.observed_at_ms is None or source.max_age_ms is None:
        return False
    return now_ms - source.observed_at_ms > source.max_age_ms


def _reject_forbidden_execution_fields(
    value: Any,
    *,
    artifact: str,
) -> None:
    forbidden = {
        "client_order_id",
        "exchange_order_id",
        "exchange_payload",
        "execution_intent_status",
        "order_id",
        "place_order",
        "submit_order",
        "transfer_payload",
        "withdrawal_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{artifact} contains forbidden execution field: {key}")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
