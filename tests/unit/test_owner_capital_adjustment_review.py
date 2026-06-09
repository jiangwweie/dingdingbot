from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.application.owner_capital_adjustment_review_service import (
    OwnerCapitalAdjustmentReviewService,
    OwnerCapitalAdjustmentReviewServiceError,
)
from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    TrialReadinessAccountFacts,
)
from src.domain.owner_capital_adjustment import (
    OwnerCapitalAdjustmentRecord,
    OwnerCapitalAdjustmentType,
    OwnerCapitalBaseReviewInput,
    OwnerCapitalMovementClassification,
    review_owner_capital_base_movement,
)


NOW_MS = 1781000000000


def _withdrawal(
    amount: str = "30",
    *,
    adjustment_id: str = "owner-withdrawal-1",
    capital_base_delta: Decimal | None = None,
) -> OwnerCapitalAdjustmentRecord:
    return OwnerCapitalAdjustmentRecord(
        adjustment_id=adjustment_id,
        adjustment_type=OwnerCapitalAdjustmentType.OWNER_MANUAL_WITHDRAWAL,
        amount=Decimal(amount),
        capital_base_delta=capital_base_delta,
        reason="Owner manually withdrew profit outside the system.",
        occurred_at_ms=NOW_MS,
        evidence_refs=["owner-note://withdrawal-1"],
    )


def _injection(amount: str = "20") -> OwnerCapitalAdjustmentRecord:
    return OwnerCapitalAdjustmentRecord(
        adjustment_id="owner-injection-1",
        adjustment_type=OwnerCapitalAdjustmentType.OWNER_CAPITAL_INJECTION,
        amount=Decimal(amount),
        reason="Owner manually added experimental capital outside the system.",
        occurred_at_ms=NOW_MS,
        evidence_refs=["owner-note://injection-1"],
    )


def _capital_base_reset(target: str = "30") -> OwnerCapitalAdjustmentRecord:
    return OwnerCapitalAdjustmentRecord(
        adjustment_id="capital-base-reset-1",
        adjustment_type=OwnerCapitalAdjustmentType.CAPITAL_BASE_RESET,
        target_capital_base=Decimal(target),
        reason="Owner reset the review capital base after manual bookkeeping.",
        occurred_at_ms=NOW_MS,
        evidence_refs=["owner-note://capital-base-reset-1"],
    )


def _facts(equity: Decimal | None, *, read_only: bool = True) -> TrialReadinessAccountFacts:
    return TrialReadinessAccountFacts(
        account_id="acct-test",
        account_type="binance_usdt_futures",
        source_id="unit-test",
        source_type=AccountFactsSourceType.CACHED_SNAPSHOT,
        account_equity=equity,
        available_margin=equity,
        timestamp_ms=NOW_MS,
        freshness_status=AccountFactsFreshnessStatus.FRESH,
        reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
        read_only_guarantee=read_only,
        external_call_performed=False,
        external_call_type="none",
    )


def test_manual_withdrawal_explains_equity_drop_without_strategy_loss_attribution():
    result = review_owner_capital_base_movement(
        OwnerCapitalBaseReviewInput(
            previous_account_equity=Decimal("130"),
            current_account_equity=Decimal("100"),
            starting_capital_base=Decimal("130"),
            owner_capital_adjustments=[_withdrawal("30")],
        )
    )

    assert (
        result.classification
        == OwnerCapitalMovementClassification.EXPLAINED_BY_OWNER_CAPITAL_EVENTS
    )
    assert result.owner_equity_flow_delta == Decimal("-30")
    assert result.expected_account_equity_delta == Decimal("-30")
    assert result.unexplained_account_equity_delta == Decimal("0")
    assert result.ending_capital_base == Decimal("100")
    assert result.owner_capital_events_are_strategy_pnl is False
    assert result.owner_capital_events_are_risk_events is False
    assert result.withdrawal_instruction_created is False
    assert result.transfer_instruction_created is False
    assert result.order_instruction_created is False
    assert result.exchange_called is False
    assert result.effects[0].trading_pnl_delta == Decimal("0")
    assert result.effects[0].strategy_loss_attribution is False
    assert result.effects[0].risk_event_created is False


def test_manual_profit_extraction_can_explain_equity_drop_without_reducing_active_base():
    profit_extraction = OwnerCapitalAdjustmentRecord(
        adjustment_id="profit-extraction-1",
        adjustment_type=OwnerCapitalAdjustmentType.MANUAL_PROFIT_EXTRACTION,
        amount=Decimal("30"),
        capital_base_delta=Decimal("0"),
        reason="Owner manually extracted profit while keeping trial capital base.",
        occurred_at_ms=NOW_MS,
    )

    result = review_owner_capital_base_movement(
        OwnerCapitalBaseReviewInput(
            previous_account_equity=Decimal("130"),
            current_account_equity=Decimal("100"),
            starting_capital_base=Decimal("100"),
            owner_capital_adjustments=[profit_extraction],
        )
    )

    assert (
        result.classification
        == OwnerCapitalMovementClassification.EXPLAINED_BY_OWNER_CAPITAL_EVENTS
    )
    assert result.owner_equity_flow_delta == Decimal("-30")
    assert result.ending_capital_base == Decimal("100")
    assert result.unexplained_account_equity_delta == Decimal("0")


def test_capital_injection_explains_equity_increase_without_trading_pnl():
    result = review_owner_capital_base_movement(
        OwnerCapitalBaseReviewInput(
            previous_account_equity=Decimal("100"),
            current_account_equity=Decimal("120"),
            starting_capital_base=Decimal("100"),
            owner_capital_adjustments=[_injection("20")],
        )
    )

    assert (
        result.classification
        == OwnerCapitalMovementClassification.EXPLAINED_BY_OWNER_CAPITAL_EVENTS
    )
    assert result.owner_equity_flow_delta == Decimal("20")
    assert result.ending_capital_base == Decimal("120")
    assert result.unexplained_account_equity_delta == Decimal("0")


def test_capital_base_reset_changes_review_base_without_explaining_equity_flow():
    result = review_owner_capital_base_movement(
        OwnerCapitalBaseReviewInput(
            previous_account_equity=Decimal("100"),
            current_account_equity=Decimal("100"),
            starting_capital_base=Decimal("100"),
            owner_capital_adjustments=[_capital_base_reset("30")],
        )
    )

    assert (
        result.classification
        == OwnerCapitalMovementClassification.EXPLAINED_BY_OWNER_CAPITAL_EVENTS
    )
    assert result.owner_equity_flow_delta == Decimal("0")
    assert result.ending_capital_base == Decimal("30")
    assert result.unexplained_account_equity_delta == Decimal("0")


def test_equity_drop_without_trading_or_owner_record_remains_unresolved():
    result = review_owner_capital_base_movement(
        OwnerCapitalBaseReviewInput(
            previous_account_equity=Decimal("100"),
            current_account_equity=Decimal("70"),
            starting_capital_base=Decimal("100"),
        )
    )

    assert result.classification == OwnerCapitalMovementClassification.UNRESOLVED_EQUITY_DELTA
    assert "unresolved_account_equity_delta" in result.blockers
    assert (
        "equity_delta_requires_trade_reconciliation_or_owner_capital_record"
        in result.warnings
    )
    assert result.owner_capital_events_are_strategy_pnl is False
    assert result.exchange_called is False


def test_trading_loss_can_be_explained_without_owner_capital_event():
    result = review_owner_capital_base_movement(
        OwnerCapitalBaseReviewInput(
            previous_account_equity=Decimal("100"),
            current_account_equity=Decimal("95"),
            starting_capital_base=Decimal("100"),
            realized_trading_pnl=Decimal("-5"),
        )
    )

    assert result.classification == OwnerCapitalMovementClassification.EXPLAINED_BY_TRADING_ONLY
    assert result.realized_trading_pnl == Decimal("-5")
    assert result.owner_equity_flow_delta == Decimal("0")
    assert result.unexplained_account_equity_delta == Decimal("0")


def test_owner_capital_record_rejects_instruction_or_exchange_authority():
    payload = _withdrawal("30").model_dump()
    payload["withdrawal_instruction_created"] = True

    with pytest.raises(ValidationError):
        OwnerCapitalAdjustmentRecord(**payload)


def test_application_service_reviews_read_only_account_facts():
    result = OwnerCapitalAdjustmentReviewService().review_account_facts(
        previous_facts=_facts(Decimal("130")),
        current_facts=_facts(Decimal("100")),
        starting_capital_base=Decimal("130"),
        owner_capital_adjustments=[_withdrawal("30")],
    )

    assert (
        result.classification
        == OwnerCapitalMovementClassification.EXPLAINED_BY_OWNER_CAPITAL_EVENTS
    )
    assert result.withdrawal_instruction_created is False
    assert result.exchange_called is False


def test_application_service_fails_closed_when_account_equity_missing():
    with pytest.raises(
        OwnerCapitalAdjustmentReviewServiceError,
        match="current account equity missing",
    ):
        OwnerCapitalAdjustmentReviewService().review_account_facts(
            previous_facts=_facts(Decimal("100")),
            current_facts=_facts(None),
            starting_capital_base=Decimal("100"),
        )


def test_application_service_fails_closed_without_read_only_guarantee():
    with pytest.raises(
        OwnerCapitalAdjustmentReviewServiceError,
        match="current account facts read-only guarantee missing",
    ):
        OwnerCapitalAdjustmentReviewService().review_account_facts(
            previous_facts=_facts(Decimal("100")),
            current_facts=_facts(Decimal("100"), read_only=False),
            starting_capital_base=Decimal("100"),
        )
