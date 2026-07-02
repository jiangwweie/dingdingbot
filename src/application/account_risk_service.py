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
        max_total_exposure_to_balance: Optional[Decimal] = Decimal("3"),
        account_scope_positions: bool = True,
    ) -> None:
        self._gateway = gateway
        self._account_service = account_service
        self._critical_distance = critical_distance
        self._degraded_distance = degraded_distance
        self._max_total_exposure_to_balance = max_total_exposure_to_balance
        self._account_scope_positions = account_scope_positions

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
            positions = await self._fetch_positions_for_account_scope(symbol)
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
                metadata={
                    "balance": str(balance),
                    "active_positions": 0,
                    "account_scope_positions": self._account_scope_positions,
                },
            )

        worst: Optional[AccountRiskAssessment] = None
        for position in active_positions:
            assessment = self._evaluate_position(position, checked_at_ms, Decimal(str(balance)))
            if worst is None or self._severity_rank(assessment.state) > self._severity_rank(worst.state):
                worst = assessment
        assert worst is not None
        exposure_assessment = self._evaluate_total_exposure(
            active_positions,
            checked_at_ms,
            Decimal(str(balance)),
        )
        if (
            exposure_assessment is not None
            and self._severity_rank(exposure_assessment.state) > self._severity_rank(worst.state)
        ):
            return exposure_assessment
        return worst

    async def _fetch_positions_for_account_scope(self, symbol: str) -> list[PositionInfo]:
        if not self._account_scope_positions:
            return await self._gateway.fetch_positions(symbol=symbol)
        try:
            return await self._gateway.fetch_positions(symbol=None)
        except TypeError:
            logger.warning(
                "Gateway does not support account-scope position fetch; "
                "falling back to symbol scope for account risk."
            )
            return await self._gateway.fetch_positions(symbol=symbol)

    def _evaluate_total_exposure(
        self,
        positions: list[PositionInfo],
        checked_at_ms: int,
        balance: Decimal,
    ) -> Optional[AccountRiskAssessment]:
        if self._max_total_exposure_to_balance is None:
            return None
        exposures: list[Decimal] = []
        metadata_positions: list[dict[str, str | None]] = []
        for position in positions:
            mark_price = position.mark_price
            if mark_price is None or mark_price <= Decimal("0"):
                return self._assessment(
                    state=AccountRiskState.DEGRADED,
                    reason="ACCOUNT_EXPOSURE_MARK_PRICE_UNAVAILABLE",
                    message="Cannot compute account exposure without mark prices; new entries are blocked.",
                    checked_at_ms=checked_at_ms,
                    metadata={
                        "balance": str(balance),
                        "symbol": position.symbol,
                        "account_scope_positions": self._account_scope_positions,
                    },
                )
            exposure = Decimal(str(position.size)) * mark_price
            exposures.append(exposure)
            metadata_positions.append(
                {
                    "symbol": position.symbol,
                    "side": position.side,
                    "size": str(position.size),
                    "mark_price": str(mark_price),
                    "exposure": str(exposure),
                }
            )

        total_exposure = sum(exposures, Decimal("0"))
        exposure_limit = balance * self._max_total_exposure_to_balance
        if total_exposure > exposure_limit:
            return self._assessment(
                state=AccountRiskState.DEGRADED,
                reason="ACCOUNT_TOTAL_EXPOSURE_LIMIT_EXCEEDED",
                message="Total account exposure exceeds the configured balance multiple; new entries are blocked.",
                checked_at_ms=checked_at_ms,
                metadata={
                    "balance": str(balance),
                    "total_exposure": str(total_exposure),
                    "exposure_limit": str(exposure_limit),
                    "max_total_exposure_to_balance": str(self._max_total_exposure_to_balance),
                    "positions": metadata_positions,
                    "account_scope_positions": self._account_scope_positions,
                },
            )
        return None

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
