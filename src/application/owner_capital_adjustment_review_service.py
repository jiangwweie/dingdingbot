"""Application service for Owner capital adjustment review classification."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from src.application.trial_readiness_account_facts import TrialReadinessAccountFacts
from src.domain.owner_capital_adjustment import (
    OwnerCapitalAdjustmentRecord,
    OwnerCapitalBaseReviewInput,
    OwnerCapitalBaseReviewResult,
    review_owner_capital_base_movement,
)


class OwnerCapitalAdjustmentReviewServiceError(ValueError):
    """Raised when account facts are insufficient for capital review."""


class OwnerCapitalAdjustmentReviewService:
    """Classify account equity movement without exchange or withdrawal authority."""

    def review_account_facts(
        self,
        *,
        previous_facts: TrialReadinessAccountFacts,
        current_facts: TrialReadinessAccountFacts,
        starting_capital_base: Decimal,
        realized_trading_pnl: Decimal = Decimal("0"),
        owner_capital_adjustments: Sequence[OwnerCapitalAdjustmentRecord] = (),
        tolerance: Decimal = Decimal("0"),
    ) -> OwnerCapitalBaseReviewResult:
        previous_equity = self._require_account_equity(previous_facts, "previous")
        current_equity = self._require_account_equity(current_facts, "current")
        return review_owner_capital_base_movement(
            OwnerCapitalBaseReviewInput(
                previous_account_equity=previous_equity,
                current_account_equity=current_equity,
                starting_capital_base=starting_capital_base,
                realized_trading_pnl=realized_trading_pnl,
                owner_capital_adjustments=list(owner_capital_adjustments),
                tolerance=tolerance,
            )
        )

    @staticmethod
    def _require_account_equity(
        facts: TrialReadinessAccountFacts,
        label: str,
    ) -> Decimal:
        if facts.account_equity is None:
            raise OwnerCapitalAdjustmentReviewServiceError(
                f"{label} account equity missing"
            )
        if not facts.read_only_guarantee:
            raise OwnerCapitalAdjustmentReviewServiceError(
                f"{label} account facts read-only guarantee missing"
            )
        return facts.account_equity
