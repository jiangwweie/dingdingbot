from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedFactFreshness,
    RuntimeExecutionTrustedSubmitFactSource,
    RuntimeExecutionTrustedSubmitFactsStatus,
    build_runtime_execution_trusted_submit_facts_snapshot,
)


NOW_MS = 1781000000000


def _semantic_ids() -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        signal_evaluation_id="evaluation-1",
        order_candidate_id="candidate-1",
    )


def _source(key: str) -> RuntimeExecutionTrustedSubmitFactSource:
    return RuntimeExecutionTrustedSubmitFactSource(
        key=key,
        source_id=f"{key}-source-1",
        source_type=f"trusted_{key}_readmodel",
        freshness=RuntimeExecutionTrustedFactFreshness.FRESH,
        observed_at_ms=NOW_MS - 50,
        max_age_ms=1_000,
    )


class _AdapterService:
    def __init__(self) -> None:
        self.calls = []

    async def controlled_submit_plan_for_authorization(self, authorization_id):
        self.calls.append(authorization_id)
        return SimpleNamespace(
            plan_id="runtime-controlled-submit-plan-auth-1",
            execution_intent_id="intent-1",
            source_id="candidate-1",
            semantic_ids=_semantic_ids(),
            symbol="BNB/USDT:USDT",
            side="long",
        )


class _AssemblyService:
    def __init__(self) -> None:
        self.calls = []

    async def assemble_and_record_snapshot_for_controlled_submit_plan(
        self,
        **kwargs,
    ):
        self.calls.append(kwargs)
        return build_runtime_execution_trusted_submit_facts_snapshot(
            trusted_submit_fact_snapshot_id=kwargs[
                "trusted_submit_fact_snapshot_id"
            ],
            execution_intent_id=kwargs["plan"].execution_intent_id,
            runtime_instance_id=kwargs["plan"].semantic_ids.runtime_instance_id,
            order_candidate_id=kwargs["plan"].source_id,
            semantic_ids=kwargs["plan"].semantic_ids,
            symbol=kwargs["plan"].symbol,
            side=kwargs["plan"].side,
            account_fact_source=_source("account_fact"),
            active_position_source=_source("active_position"),
            open_order_source=_source("open_order"),
            protection_state_source=_source("protection_state"),
            market_rule_source=_source("market_rule"),
            reconciliation_source=_source("reconciliation"),
            now_ms=NOW_MS,
            metadata=kwargs["metadata"],
        )


@pytest.mark.asyncio
async def test_trading_console_records_trusted_submit_facts_from_authorization(
    monkeypatch,
):
    from src.interfaces import api_trading_console

    adapter = _AdapterService()
    assembly = _AssemblyService()

    async def _adapter_service():
        return adapter

    monkeypatch.setattr(
        api_trading_console,
        "_runtime_execution_intent_adapter_service",
        _adapter_service,
    )
    monkeypatch.setattr(
        api_trading_console,
        "_runtime_execution_trusted_submit_facts_assembly_service",
        lambda: assembly,
    )

    snapshot = (
        await api_trading_console
        .record_runtime_execution_trusted_submit_facts_for_authorization(
            "auth-1",
            trusted_submit_fact_snapshot_id="trusted-submit-facts-auth-1",
        )
    )

    assert adapter.calls == ["auth-1"]
    assert len(assembly.calls) == 1
    assert assembly.calls[0]["plan"].execution_intent_id == "intent-1"
    assert assembly.calls[0]["trusted_submit_fact_snapshot_id"] == (
        "trusted-submit-facts-auth-1"
    )
    assert assembly.calls[0]["metadata"]["authorization_id"] == "auth-1"
    assert (
        assembly.calls[0]["metadata"]["owner_supplied_allow_facts_accepted"]
        is False
    )
    assert snapshot.status == (
        RuntimeExecutionTrustedSubmitFactsStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert snapshot.exchange_called is False
    assert snapshot.order_lifecycle_called is False
