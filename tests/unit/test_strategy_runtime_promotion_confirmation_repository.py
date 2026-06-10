from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.strategy_runtime_promotion_gate_service import (
    StrategyRuntimePromotionGateService,
)
from src.domain.experimental_runtime_profile_proposal import (
    build_experimental_runtime_profile_proposal,
)
from src.domain.strategy_runtime_promotion_gate import (
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateConfirmationRecord,
    StrategyRuntimePromotionGateStatus,
    StrategySemanticsConfirmationFacts,
)
from src.infrastructure.pg_models import PGStrategyRuntimePromotionConfirmationORM
from src.infrastructure.pg_strategy_runtime_promotion_confirmation_repository import (
    PgStrategyRuntimePromotionConfirmationRepository,
)


NOW_MS = 1781000000000


def _semantic_confirmed() -> StrategySemanticsConfirmationFacts:
    return StrategySemanticsConfirmationFacts(
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
    )


def _runtime_confirmed() -> RuntimeExecutionConfirmationFacts:
    return RuntimeExecutionConfirmationFacts(
        runtime_profile_confirmed=True,
        owner_confirmation_mode_confirmed=True,
        symbol_side_boundary_confirmed=True,
        max_loss_budget_confirmed=True,
        max_notional_boundary_confirmed=True,
        max_active_positions_boundary_confirmed=True,
        max_leverage_boundary_confirmed=True,
        margin_usage_boundary_confirmed=True,
        liquidation_buffer_boundary_confirmed=True,
        protection_readiness_source_confirmed=True,
        stale_fact_behavior_confirmed=True,
        attempt_consumption_rule_confirmed=True,
        budget_reservation_rule_confirmed=True,
        trusted_active_position_source_confirmed=True,
        trusted_account_fact_source_confirmed=True,
    )


@pytest_asyncio.fixture()
async def promotion_confirmation_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGStrategyRuntimePromotionConfirmationORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgStrategyRuntimePromotionConfirmationRepository(
            session_maker=session_maker
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_promotion_confirmation_repository_roundtrip(
    promotion_confirmation_repo,
):
    record = StrategyRuntimePromotionGateConfirmationRecord(
        confirmation_id="promotion-confirmation-repo-1",
        runtime_instance_id="runtime-cpm-repo-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        runtime_profile_proposal_snapshot=build_experimental_runtime_profile_proposal(
            strategy_family_id="CPM-RO-001",
            strategy_family_version_id="CPM-RO-001-v0",
            symbol="BNB/USDT:USDT",
            side="long",
        ),
        reason="Owner accepts bounded trial semantics for small risk capital.",
        evidence_refs=["owner-note://promotion-confirmation-repo-1"],
        created_at_ms=NOW_MS,
        metadata={"source": "unit-test"},
    )
    record = StrategyRuntimePromotionGateService().with_result_snapshot(record)

    saved = await promotion_confirmation_repo.append(record)
    loaded = await promotion_confirmation_repo.get("promotion-confirmation-repo-1")
    listed = await promotion_confirmation_repo.list(
        runtime_instance_id="runtime-cpm-repo-1"
    )

    assert saved.confirmation_id == record.confirmation_id
    assert loaded is not None
    assert loaded.runtime_instance_id == "runtime-cpm-repo-1"
    assert loaded.strategy_family_id == "CPM-RO-001"
    assert loaded.semantic_confirmations.entry_policy_confirmed is True
    assert loaded.runtime_confirmations.max_loss_budget_confirmed is True
    assert loaded.runtime_profile_proposal_snapshot is not None
    assert loaded.runtime_profile_proposal_snapshot.total_loss_budget == Decimal("9.00")
    assert loaded.runtime_profile_proposal_snapshot.not_execution_authority is True
    assert loaded.runtime_profile_proposal_snapshot.order_created is False
    assert loaded.promotion_gate_result_snapshot is not None
    assert (
        loaded.promotion_gate_result_snapshot.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    assert listed[0].confirmation_id == "promotion-confirmation-repo-1"
    assert loaded.not_execution_authority is True
    assert loaded.execution_intent_created is False
    assert loaded.order_created is False
    assert loaded.exchange_called is False
    assert loaded.owner_bounded_execution_called is False
    assert loaded.order_lifecycle_called is False
    assert loaded.runtime_mutation_created is False
    assert loaded.withdrawal_instruction_created is False
    assert loaded.transfer_instruction_created is False


def test_promotion_confirmation_rejects_mismatched_profile_proposal_snapshot():
    with pytest.raises(ValueError, match="strategy_family_id mismatch"):
        StrategyRuntimePromotionGateConfirmationRecord(
            confirmation_id="promotion-confirmation-profile-mismatch",
            strategy_family_id="BRF-001",
            strategy_family_version_id="BRF-001-v0",
            semantic_confirmations=_semantic_confirmed(),
            runtime_confirmations=_runtime_confirmed(),
            runtime_profile_proposal_snapshot=(
                build_experimental_runtime_profile_proposal(
                    strategy_family_id="CPM-RO-001",
                    strategy_family_version_id="CPM-RO-001-v0",
                    symbol="BNB/USDT:USDT",
                    side="long",
                )
            ),
            reason="Mismatched proposal snapshot must not confirm runtime profile.",
            created_at_ms=NOW_MS,
        )
