from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from src.application.readmodels.console_models import PortfolioPositionItem, RuntimePortfolioResponse


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _direction_from_side(side: str) -> str:
    normalized = (side or "").lower()
    if normalized in {"sell", "short"}:
        return "SHORT"
    return "LONG"


class RuntimePortfolioReadModel:
    async def build(
        self,
        *,
        runtime_config_provider: Optional[Any],
        capital_protection: Optional[Any],
        account_snapshot: Optional[Any],
    ) -> RuntimePortfolioResponse:
        if account_snapshot is None:
            return RuntimePortfolioResponse(
                total_equity=0.0,
                available_balance=0.0,
                unrealized_pnl=0.0,
                total_exposure=0.0,
                daily_loss_used=0.0,
                daily_loss_limit=0.0,
                max_total_exposure=0.0,
                leverage_usage=0.0,
                positions=[],
            )

        total_balance = getattr(account_snapshot, "total_balance", Decimal("0"))
        available_balance = getattr(account_snapshot, "available_balance", Decimal("0"))
        unrealized_pnl = getattr(account_snapshot, "unrealized_pnl", Decimal("0"))
        total_equity = total_balance + unrealized_pnl

        positions: list[PortfolioPositionItem] = []
        total_exposure = Decimal("0")

        for position in getattr(account_snapshot, "positions", []):
            size = getattr(position, "size", Decimal("0"))
            entry_price = getattr(position, "entry_price", Decimal("0"))
            current_price = getattr(position, "current_price", entry_price)
            position_unrealized_pnl = getattr(position, "unrealized_pnl", Decimal("0"))
            leverage = int(getattr(position, "leverage", 1) or 1)
            notional = abs(size * entry_price)
            total_exposure += notional
            pnl_percent = float(position_unrealized_pnl / notional * 100) if notional else 0.0

            positions.append(
                PortfolioPositionItem(
                    symbol=getattr(position, "symbol", "unknown"),
                    direction=_direction_from_side(getattr(position, "side", "long")),
                    quantity=_to_float(size),
                    entry_price=_to_float(entry_price),
                    current_price=_to_float(current_price),
                    unrealized_pnl=_to_float(position_unrealized_pnl),
                    pnl_percent=pnl_percent,
                    leverage=leverage,
                )
            )

        risk_limit_multiplier = Decimal("1.0")
        if runtime_config_provider is not None:
            risk_limit_multiplier = runtime_config_provider.resolved_config.risk.max_total_exposure
        max_total_exposure = total_equity * risk_limit_multiplier

        daily_loss_limit = Decimal("0")
        daily_loss_used = Decimal("0")
        if capital_protection is not None:
            config = getattr(capital_protection, "_config", None)
            daily_stats = getattr(capital_protection, "_daily_stats", None)
            if config is not None:
                max_loss_amount = config.daily.get("max_loss_amount")
                if max_loss_amount is not None:
                    daily_loss_limit = Decimal(str(max_loss_amount))
                else:
                    max_loss_percent = Decimal(str(config.daily.get("max_loss_percent", "0")))
                    daily_loss_limit = total_equity * (max_loss_percent / Decimal("100"))
            if daily_stats is not None:
                realized_pnl = getattr(daily_stats, "realized_pnl", Decimal("0"))
                if realized_pnl < 0:
                    daily_loss_used = abs(realized_pnl)
        elif runtime_config_provider is not None:
            # Fallback to runtime risk config if capital_protection unavailable
            daily_max_loss_percent = runtime_config_provider.resolved_config.risk.daily_max_loss_percent
            daily_loss_limit = total_equity * daily_max_loss_percent

        leverage_usage = float(total_exposure / total_equity) if total_equity else 0.0

        return RuntimePortfolioResponse(
            total_equity=_to_float(total_equity),
            available_balance=_to_float(available_balance),
            unrealized_pnl=_to_float(unrealized_pnl),
            total_exposure=_to_float(total_exposure),
            daily_loss_used=_to_float(daily_loss_used),
            daily_loss_limit=_to_float(daily_loss_limit),
            max_total_exposure=_to_float(max_total_exposure),
            leverage_usage=leverage_usage,
            positions=positions,
        )

