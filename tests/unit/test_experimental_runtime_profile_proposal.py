from __future__ import annotations

from decimal import Decimal

from src.domain.experimental_runtime_profile_proposal import (
    ExperimentalRuntimeProfileKind,
    ExperimentalRuntimeProfileProposalStatus,
    build_experimental_runtime_profile_proposal,
)
from src.interfaces.api_trading_console import (
    experimental_runtime_profile_proposal_preview,
)


def test_cpm_long_small_capital_profile_proposal_is_ready_for_confirmation():
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="BNB/USDT:USDT",
        side="long",
        capital_base=Decimal("30"),
    )

    assert proposal.status == (
        ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    )
    assert proposal.profile_kind == (
        ExperimentalRuntimeProfileKind.SMALL_CAPITAL_RIGHT_TAIL_LONG
    )
    assert proposal.total_loss_budget == Decimal("9.00")
    assert proposal.max_loss_per_attempt == Decimal("3.00")
    assert proposal.max_notional_per_attempt == Decimal("10.00")
    assert proposal.max_attempts == 3
    assert proposal.max_active_positions == 1
    assert proposal.max_leverage == Decimal("1")
    assert proposal.boundary.total_budget == Decimal("9.00")
    assert proposal.boundary.max_notional_per_attempt == Decimal("10.00")
    assert proposal.boundary.allowed_symbols == ["BNB/USDT:USDT"]
    assert proposal.boundary.allowed_sides == ["long"]
    assert "reference_implementation_not_proven_production_strategy" in (
        proposal.warnings
    )
    assert "strategy_not_proven_alpha_limits_budget_and_autonomy" in proposal.warnings
    assert proposal.not_execution_authority is True
    assert proposal.creates_runtime is False
    assert proposal.creates_execution_intent is False
    assert proposal.order_created is False
    assert proposal.exchange_called is False


def test_brf_short_profile_proposal_uses_conservative_short_budget():
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        symbol="BNB/USDT:USDT",
        side="short",
        capital_base=Decimal("30"),
    )

    assert proposal.status == (
        ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    )
    assert proposal.profile_kind == (
        ExperimentalRuntimeProfileKind.SMALL_CAPITAL_CONSERVATIVE_SHORT
    )
    assert proposal.total_loss_budget == Decimal("6.00")
    assert proposal.max_loss_per_attempt == Decimal("2.00")
    assert proposal.max_notional_per_attempt == Decimal("8.00")
    assert proposal.boundary.allowed_sides == ["short"]
    assert "short_side_conservative_profile_required" in proposal.warnings
    assert "short_side_conservative_profile_confirmed" in (
        proposal.owner_confirmation_keys
    )
    assert proposal.not_execution_authority is True
    assert proposal.order_created is False
    assert proposal.exchange_called is False


def test_mean_reversion_profile_proposal_uses_tighter_budget():
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="LSR-001",
        strategy_family_version_id="LSR-001-v0",
        symbol="BNB/USDT:USDT",
        side="long",
        capital_base=Decimal("30"),
    )

    assert proposal.status == (
        ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    )
    assert proposal.profile_kind == (
        ExperimentalRuntimeProfileKind.SMALL_CAPITAL_MEAN_REVERSION
    )
    assert proposal.total_loss_budget == Decimal("6.00")
    assert proposal.max_notional_per_attempt == Decimal("8.00")
    assert "mean_reversion_profile_needs_tighter_attempt_review" in proposal.warnings
    assert proposal.not_execution_authority is True
    assert proposal.order_created is False


def test_profile_proposal_blocks_side_mismatch_without_granting_authority():
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="BNB/USDT:USDT",
        side="short",
        capital_base=Decimal("30"),
    )

    assert proposal.status == ExperimentalRuntimeProfileProposalStatus.BLOCKED
    assert "strategy_side_not_supported" in proposal.blockers
    assert proposal.not_execution_authority is True
    assert proposal.creates_runtime is False
    assert proposal.order_created is False


def test_profile_proposal_blocks_regime_classifier_as_trade_runtime():
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="RMR-001",
        strategy_family_version_id="RMR-001-v0",
        symbol="BNB/USDT:USDT",
        side="long",
        capital_base=Decimal("30"),
    )

    assert proposal.status == ExperimentalRuntimeProfileProposalStatus.BLOCKED
    assert "strategy_binding_not_trade_candidate" in proposal.blockers
    assert "regime_classifier_not_runtime_trade_strategy" in proposal.blockers
    assert proposal.not_execution_authority is True
    assert proposal.exchange_called is False


async def test_trading_console_profile_proposal_endpoint_is_non_executing():
    proposal = await experimental_runtime_profile_proposal_preview(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        symbol="BNB/USDT:USDT",
        side="short",
        capital_base=Decimal("30"),
    )

    assert proposal.status == (
        ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    )
    assert proposal.not_runtime_record is True
    assert proposal.not_execution_authority is True
    assert proposal.creates_runtime is False
    assert proposal.creates_execution_intent is False
    assert proposal.order_created is False
    assert proposal.exchange_called is False
