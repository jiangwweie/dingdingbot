"""Assemble trusted submit-time fact snapshots from read-only sources.

The assembler is an application boundary for first-real-submit readiness. It
does not call exchange write APIs, create orders, mutate runtime state, or
grant execution authority. Missing readers intentionally produce BLOCKED
snapshots through the domain builder.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactSource,
    RuntimeExecutionTrustedSubmitFactsSnapshot,
    build_runtime_execution_trusted_submit_facts_snapshot,
)


class TrustedSubmitFactSourceReader(Protocol):
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
    ) -> RuntimeExecutionTrustedSubmitFactSource | Mapping[str, Any] | None:
        ...


class TrustedSubmitFactsSnapshotRepositoryPort(Protocol):
    async def create(
        self,
        snapshot: RuntimeExecutionTrustedSubmitFactsSnapshot,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        ...


class RuntimeExecutionTrustedSubmitFactsAssemblyService:
    """Build a submit facts snapshot without creating execution authority."""

    _SOURCE_FIELDS = {
        "account_fact": "account_fact_source",
        "active_position": "active_position_source",
        "open_order": "open_order_source",
        "protection_state": "protection_state_source",
        "market_rule": "market_rule_source",
        "reconciliation": "reconciliation_source",
    }

    def __init__(
        self,
        *,
        repository: TrustedSubmitFactsSnapshotRepositoryPort | None = None,
        account_fact_reader: TrustedSubmitFactSourceReader | None = None,
        active_position_reader: TrustedSubmitFactSourceReader | None = None,
        open_order_reader: TrustedSubmitFactSourceReader | None = None,
        protection_state_reader: TrustedSubmitFactSourceReader | None = None,
        market_rule_reader: TrustedSubmitFactSourceReader | None = None,
        reconciliation_reader: TrustedSubmitFactSourceReader | None = None,
    ) -> None:
        self._repository = repository
        self._readers = {
            "account_fact": account_fact_reader,
            "active_position": active_position_reader,
            "open_order": open_order_reader,
            "protection_state": protection_state_reader,
            "market_rule": market_rule_reader,
            "reconciliation": reconciliation_reader,
        }

    async def assemble_snapshot(
        self,
        *,
        execution_intent_id: str,
        semantic_ids: BrcSemanticIds,
        symbol: str,
        now_ms: int,
        trusted_submit_fact_snapshot_id: str | None = None,
        runtime_instance_id: str | None = None,
        order_candidate_id: str | None = None,
        side: str | None = None,
        owner_supplied_allow_facts_rejected: bool = True,
        missing_or_stale_facts_block: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        sources: dict[str, RuntimeExecutionTrustedSubmitFactSource | None] = {}
        missing_readers: list[str] = []
        read_errors: dict[str, str] = {}

        for key, field_name in self._SOURCE_FIELDS.items():
            reader = self._readers.get(key)
            if reader is None:
                sources[field_name] = None
                missing_readers.append(key)
                continue
            try:
                raw_source = await reader.read_trusted_submit_fact_source(
                    key=key,
                    execution_intent_id=execution_intent_id,
                    runtime_instance_id=runtime_instance_id,
                    order_candidate_id=order_candidate_id,
                    symbol=symbol,
                    side=side,
                    now_ms=now_ms,
                )
            except Exception as exc:  # pragma: no cover - exact exception is reader-owned.
                sources[field_name] = None
                read_errors[key] = type(exc).__name__
                continue
            sources[field_name] = _coerce_fact_source(raw_source)

        assembly_metadata = {
            "assembled_from_read_only_source_ports": True,
            "missing_readers": missing_readers,
            "read_errors": read_errors,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange_write": True,
        }
        if metadata:
            assembly_metadata.update(metadata)

        return build_runtime_execution_trusted_submit_facts_snapshot(
            trusted_submit_fact_snapshot_id=(
                trusted_submit_fact_snapshot_id
                or f"trusted-submit-facts-{execution_intent_id}"
            ),
            execution_intent_id=execution_intent_id,
            runtime_instance_id=runtime_instance_id,
            order_candidate_id=order_candidate_id,
            semantic_ids=semantic_ids,
            symbol=symbol,
            side=side,
            now_ms=now_ms,
            owner_supplied_allow_facts_rejected=owner_supplied_allow_facts_rejected,
            missing_or_stale_facts_block=missing_or_stale_facts_block,
            metadata=assembly_metadata,
            **sources,
        )

    async def assemble_snapshot_for_controlled_submit_plan(
        self,
        *,
        plan: Any,
        now_ms: int,
        trusted_submit_fact_snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        """Assemble trusted facts from a non-submitting controlled-submit plan."""

        assembly_metadata = {
            "controlled_submit_plan_id": getattr(plan, "plan_id", None),
            "controlled_submit_plan_status": (
                getattr(getattr(plan, "status", None), "value", None)
                or str(getattr(plan, "status", "unknown"))
            ),
        }
        if metadata:
            assembly_metadata.update(metadata)
        return await self.assemble_snapshot(
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            execution_intent_id=getattr(plan, "execution_intent_id"),
            runtime_instance_id=getattr(
                getattr(plan, "semantic_ids"),
                "runtime_instance_id",
                None,
            ),
            order_candidate_id=getattr(plan, "source_id", None),
            semantic_ids=getattr(plan, "semantic_ids"),
            symbol=getattr(plan, "symbol"),
            side=getattr(plan, "side", None),
            now_ms=now_ms,
            metadata=assembly_metadata,
        )

    async def assemble_and_record_snapshot(
        self,
        **kwargs: Any,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        if self._repository is None:
            raise RuntimeError(
                "runtime_execution_trusted_submit_facts_repository_unavailable"
            )
        snapshot = await self.assemble_snapshot(**kwargs)
        return await self._repository.create(snapshot)

    async def assemble_and_record_snapshot_for_controlled_submit_plan(
        self,
        *,
        plan: Any,
        now_ms: int,
        trusted_submit_fact_snapshot_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        if self._repository is None:
            raise RuntimeError(
                "runtime_execution_trusted_submit_facts_repository_unavailable"
            )
        snapshot = await self.assemble_snapshot_for_controlled_submit_plan(
            plan=plan,
            now_ms=now_ms,
            trusted_submit_fact_snapshot_id=trusted_submit_fact_snapshot_id,
            metadata=metadata,
        )
        return await self._repository.create(snapshot)


def _coerce_fact_source(
    source: RuntimeExecutionTrustedSubmitFactSource | Mapping[str, Any] | None,
) -> RuntimeExecutionTrustedSubmitFactSource | None:
    if source is None:
        return None
    if isinstance(source, RuntimeExecutionTrustedSubmitFactSource):
        return source
    return RuntimeExecutionTrustedSubmitFactSource.model_validate(dict(source))
