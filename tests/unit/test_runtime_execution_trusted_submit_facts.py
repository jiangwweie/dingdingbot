from __future__ import annotations

import pytest

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedFactFreshness,
    RuntimeExecutionTrustedSubmitFactsStatus,
    RuntimeExecutionTrustedSubmitFactSource,
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
        observed_at_ms=NOW_MS - 100,
        max_age_ms=1_000,
    )


def _ready_snapshot(**overrides):
    sources = {
        "account_fact_source": _source("account_fact"),
        "active_position_source": _source("active_position"),
        "open_order_source": _source("open_order"),
        "protection_state_source": _source("protection_state"),
        "market_rule_source": _source("market_rule"),
        "reconciliation_source": _source("reconciliation"),
    }
    sources.update(overrides)
    return build_runtime_execution_trusted_submit_facts_snapshot(
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
        **sources,
    )


def test_trusted_submit_facts_snapshot_can_be_ready_without_execution_authority():
    snapshot = _ready_snapshot()

    assert (
        snapshot.status
        == RuntimeExecutionTrustedSubmitFactsStatus.READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert snapshot.blockers == []
    assert snapshot.facts_fresh_enough is True
    assert snapshot.owner_supplied_allow_facts_rejected is True
    assert snapshot.missing_or_stale_facts_block is True
    assert snapshot.not_execution_authority is True
    assert snapshot.execution_intent_status_changed is False
    assert snapshot.runtime_state_mutated is False
    assert snapshot.order_created is False
    assert snapshot.exchange_called is False
    assert snapshot.owner_bounded_execution_called is False
    assert snapshot.order_lifecycle_called is False
    assert snapshot.withdrawal_instruction_created is False
    assert snapshot.transfer_instruction_created is False


def test_trusted_submit_facts_snapshot_blocks_missing_fact_source():
    snapshot = _ready_snapshot(open_order_source=None)

    assert snapshot.status == RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
    assert "trusted_open_order_source_missing" in snapshot.blockers
    assert "trusted_submit_facts_not_fresh_enough" in snapshot.blockers
    assert snapshot.order_created is False
    assert snapshot.exchange_called is False


def test_trusted_submit_facts_snapshot_rejects_owner_supplied_allow_signal():
    snapshot = _ready_snapshot(
        active_position_source=RuntimeExecutionTrustedSubmitFactSource(
            key="active_position",
            source_id="owner-ui-active-position-count",
            source_type="owner_supplied_preview_fact",
            observed_at_ms=NOW_MS,
            max_age_ms=1_000,
            owner_supplied_allow_signal=True,
        )
    )

    assert snapshot.status == RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
    assert "trusted_active_position_owner_supplied_allow_signal_rejected" in (
        snapshot.blockers
    )
    assert snapshot.owner_supplied_allow_facts_rejected is True


def test_trusted_submit_facts_snapshot_blocks_stale_facts():
    snapshot = _ready_snapshot(
        account_fact_source=RuntimeExecutionTrustedSubmitFactSource(
            key="account_fact",
            source_id="account-facts-source-1",
            source_type="trusted_account_fact_readmodel",
            freshness=RuntimeExecutionTrustedFactFreshness.STALE,
            observed_at_ms=NOW_MS - 10_000,
            max_age_ms=1_000,
        )
    )

    assert snapshot.status == RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
    assert "trusted_account_fact_fact_stale" in snapshot.blockers
    assert "trusted_account_fact_fact_age_exceeded" in snapshot.blockers
    assert "trusted_submit_facts_not_fresh_enough" in snapshot.blockers


def test_trusted_submit_facts_snapshot_rejects_execution_metadata():
    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionTrustedSubmitFactSource(
            key="account_fact",
            source_id="bad-source",
            source_type="trusted_account_fact_readmodel",
            metadata={"exchange_payload": {"symbol": "BNB/USDT:USDT"}},
        )
