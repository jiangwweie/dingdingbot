"""Runtime account-risk and liquidation-distance gate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from src.domain.models import PositionInfo
from src.infrastructure.logger import logger


ACCOUNT_RISK_BLOCK_REASON = "ACCOUNT_RISK_NOT_HEALTHY"


class AccountRiskState(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AccountRiskAssessment:
    """Result of one account-risk gate evaluation."""

    state: AccountRiskState
    allowed_new_entry: bool
    reason: str
    reason_message: str
    checked_at_ms: int
    liquidation_distance: Optional[Decimal] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AccountRiskService:
    """Fail-closed runtime account-risk gate for new entries.

    The service is read-only. It does not change leverage, margin mode,
    positions, orders, account balances, or runtime profile settings.
    """

    def __init__(
        self,
        *,
        gateway: Any,
        account_service: Any,
        critical_distance: Decimal = Decimal("0.05"),
        degraded_distance: Decimal = Decimal("0.10"),
    ) -> None:
        self._gateway = gateway
        self._account_service = account_service
        self._critical_distance = critical_distance
        self._degraded_distance = degraded_distance

    async def evaluate_new_entry(self, symbol: str) -> AccountRiskAssessment:
        """Evaluate whether a new entry may proceed for a symbol."""
        checked_at_ms = self._now_ms()
        try:
            balance = await self._account_service.get_balance()
        except Exception as exc:
            logger.error("Account risk balance read failed: %s", exc, exc_info=True)
            return self._assessment(
                state=AccountRiskState.UNKNOWN,
                reason="ACCOUNT_BALANCE_UNAVAILABLE",
                message="Account balance is unavailable; new entries fail closed.",
                checked_at_ms=checked_at_ms,
            )

        if balance is None or Decimal(str(balance)) <= Decimal("0"):
            return self._assessment(
                state=AccountRiskState.UNKNOWN,
                reason="ACCOUNT_BALANCE_INVALID",
                message="Account balance is missing or non-positive; new entries fail closed.",
                checked_at_ms=checked_at_ms,
                metadata={"balance": str(balance) if balance is not None else None},
            )

        try:
            positions = await self._gateway.fetch_positions(symbol=symbol)
        except Exception as exc:
            logger.error("Account risk position read failed: %s", exc, exc_info=True)
            return self._assessment(
                state=AccountRiskState.UNKNOWN,
                reason="ACCOUNT_POSITIONS_UNAVAILABLE",
                message="Account positions are unavailable; new entries fail closed.",
                checked_at_ms=checked_at_ms,
            )

        active_positions = [pos for pos in positions if Decimal(str(pos.size)) > Decimal("0")]
        if not active_positions:
            return self._assessment(
                state=AccountRiskState.HEALTHY,
                reason="ACCOUNT_HEALTHY_FLAT",
                message="Account read succeeded and symbol has no active position.",
                checked_at_ms=checked_at_ms,
                allowed=True,
                metadata={"balance": str(balance), "active_positions": 0},
            )

        worst: Optional[AccountRiskAssessment] = None
        for position in active_positions:
            assessment = self._evaluate_position(position, checked_at_ms, Decimal(str(balance)))
            if worst is None or self._severity_rank(assessment.state) > self._severity_rank(worst.state):
                worst = assessment
        assert worst is not None
        return worst

    def _evaluate_position(
        self,
        position: PositionInfo,
        checked_at_ms: int,
        balance: Decimal,
    ) -> AccountRiskAssessment:
        mark_price = position.mark_price
        liquidation_price = getattr(position, "liquidation_price", None)
        metadata = {
            "balance": str(balance),
            "symbol": position.symbol,
            "side": position.side,
            "size": str(position.size),
            "mark_price": str(mark_price) if mark_price is not None else None,
            "liquidation_price": str(liquidation_price) if liquidation_price is not None else None,
            "leverage": position.leverage,
        }
        if mark_price is None or mark_price <= Decimal("0"):
            return self._assessment(
                state=AccountRiskState.DEGRADED,
                reason="MARK_PRICE_UNAVAILABLE",
                message="Mark price is unavailable; new entries are blocked.",
                checked_at_ms=checked_at_ms,
                metadata=metadata,
            )
        if liquidation_price is None or liquidation_price <= Decimal("0"):
            return self._assessment(
                state=AccountRiskState.DEGRADED,
                reason="LIQUIDATION_PRICE_UNAVAILABLE",
                message="Liquidation price is unavailable; new entries are blocked.",
                checked_at_ms=checked_at_ms,
                metadata=metadata,
            )

        side = str(position.side).lower()
        if side == "short":
            distance = (liquidation_price - mark_price) / mark_price
        else:
            distance = (mark_price - liquidation_price) / mark_price
        metadata["liquidation_distance"] = str(distance)

        if distance <= Decimal("0") or distance < self._critical_distance:
            return self._assessment(
                state=AccountRiskState.CRITICAL,
                reason="LIQUIDATION_DISTANCE_CRITICAL",
                message="Liquidation distance is critical; new entries are blocked.",
                checked_at_ms=checked_at_ms,
                liquidation_distance=distance,
                metadata=metadata,
            )
        if distance < self._degraded_distance:
            return self._assessment(
                state=AccountRiskState.DEGRADED,
                reason="LIQUIDATION_DISTANCE_DEGRADED",
                message="Liquidation distance is degraded; new entries are blocked.",
                checked_at_ms=checked_at_ms,
                liquidation_distance=distance,
                metadata=metadata,
            )
        return self._assessment(
            state=AccountRiskState.HEALTHY,
            reason="ACCOUNT_HEALTHY_POSITION",
            message="Account risk and liquidation distance are healthy.",
            checked_at_ms=checked_at_ms,
            allowed=True,
            liquidation_distance=distance,
            metadata=metadata,
        )

    @staticmethod
    def _assessment(
        *,
        state: AccountRiskState,
        reason: str,
        message: str,
        checked_at_ms: int,
        allowed: bool = False,
        liquidation_distance: Optional[Decimal] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AccountRiskAssessment:
        return AccountRiskAssessment(
            state=state,
            allowed_new_entry=allowed,
            reason=reason,
            reason_message=message,
            checked_at_ms=checked_at_ms,
            liquidation_distance=liquidation_distance,
            metadata=metadata or {},
        )

    @staticmethod
    def _severity_rank(state: AccountRiskState) -> int:
        return {
            AccountRiskState.HEALTHY: 0,
            AccountRiskState.DEGRADED: 1,
            AccountRiskState.UNKNOWN: 2,
            AccountRiskState.CRITICAL: 3,
        }[state]

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)
