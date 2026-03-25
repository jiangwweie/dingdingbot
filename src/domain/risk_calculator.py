"""
Risk Calculator - Position sizing and stop-loss calculation.
All calculations use Decimal for precision, no float allowed.
"""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Tuple, List, Dict, Any
import json

from .models import (
    KlineData,
    SignalResult,
    Direction,
    AccountSnapshot,
    PositionInfo,
)


class RiskConfig:
    """Risk management configuration."""

    def __init__(
        self,
        max_loss_percent: Decimal,
        max_leverage: int,
    ):
        """
        Initialize risk configuration.

        Args:
            max_loss_percent: Maximum loss as fraction of account balance (e.g., 0.01 = 1%)
            max_leverage: Maximum allowed leverage
        """
        if not (Decimal(0) < max_loss_percent <= Decimal(1)):
            raise ValueError(
                f"max_loss_percent must be in (0, 1], got {max_loss_percent}"
            )
        if max_leverage < 1:
            raise ValueError(f"max_leverage must be >= 1, got {max_leverage}")

        self.max_loss_percent = Decimal(max_loss_percent)
        self.max_leverage = int(max_leverage)


class RiskCalculator:
    """
    Position sizing and risk calculation engine.

    Core formula:
    Position_Size = (Balance * Loss_Percent) / Stop_Loss_Distance

    Where:
    - Balance: Account equity available for trading
    - Loss_Percent: Maximum acceptable loss as fraction (e.g., 0.01 for 1%)
    - Stop_Loss_Distance: |Entry_Price - Stop_Loss| / Entry_Price (as percentage)
    """

    def __init__(self, config: RiskConfig):
        """
        Initialize risk calculator.

        Args:
            config: Risk configuration
        """
        self.config = config
        self._precision = Decimal("0.00000001")  # 8 decimal places for crypto

    def calculate_stop_loss(
        self,
        kline: KlineData,
        direction: Direction,
    ) -> Decimal:
        """
        Calculate suggested stop-loss level based on Pinbar.

        For LONG: Stop loss below the Pinbar low
        For SHORT: Stop loss above the Pinbar high

        Args:
            kline: K-line data where Pinbar was detected
            direction: Signal direction

        Returns:
            Suggested stop-loss price level
        """
        if direction == Direction.LONG:
            # Stop loss slightly below the Pinbar low
            # Use the low of the Pinbar candle
            stop_loss = kline.low
        else:  # SHORT
            # Stop loss slightly above the Pinbar high
            stop_loss = kline.high

        return self._quantize_price(stop_loss, kline.close)

    def calculate_position_size(
        self,
        account: AccountSnapshot,
        entry_price: Decimal,
        stop_loss: Decimal,
        direction: Direction,
    ) -> Tuple[Decimal, int]:
        """
        Calculate optimal position size based on risk parameters.

        Core formula:
        Position_Size = Risk_Amount / Stop_Distance
        where Risk_Amount = Balance * Max_Loss_Percent

        Args:
            account: Current account snapshot
            entry_price: Suggested entry price
            stop_loss: Calculated stop-loss level
            direction: Signal direction

        Returns:
            Tuple of (position_size, leverage_to_use)
        """
        # Use total balance as per requirements
        balance = account.total_balance
        if balance <= Decimal(0):
            return Decimal(0), 1

        # Calculate risk amount
        risk_amount = balance * self.config.max_loss_percent

        # Calculate stop-loss distance (absolute price difference)
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == Decimal(0):
            from .exceptions import DataQualityWarning
            raise DataQualityWarning("Stop loss distance is zero (doji candle)", "W-001")

        # Calculate position size: risk_amount / stop_distance
        position_size = risk_amount / stop_distance

        # Apply leverage cap
        max_position_value = balance * Decimal(self.config.max_leverage)
        max_position_size = max_position_value / entry_price
        position_size = min(position_size, max_position_size)

        # Calculate leverage to use
        position_value = position_size * entry_price
        leverage_required = position_value / balance if balance > 0 else Decimal(1)
        leverage_to_use = min(
            int(leverage_required.quantize(Decimal("1"), rounding=ROUND_DOWN)) + 1,
            self.config.max_leverage,
        )
        leverage_to_use = max(leverage_to_use, 1)

        # Quantize to reasonable precision
        position_size = position_size.quantize(self._precision, rounding=ROUND_DOWN)

        return position_size, leverage_to_use

    def _quantize_price(self, price: Decimal, reference: Decimal) -> Decimal:
        """
        Quantize price to appropriate precision.

        Uses reference price to determine appropriate decimal places.
        """
        # Determine precision based on price magnitude
        if reference >= Decimal(10000):
            precision = Decimal("0.01")
        elif reference >= Decimal(1000):
            precision = Decimal("0.01")
        elif reference >= Decimal(100):
            precision = Decimal("0.01")
        elif reference >= Decimal(10):
            precision = Decimal("0.001")
        elif reference >= Decimal(1):
            precision = Decimal("0.0001")
        elif reference >= Decimal("0.1"):
            precision = Decimal("0.00001")
        elif reference >= Decimal("0.01"):
            precision = Decimal("0.000001")
        else:
            precision = Decimal("0.00000001")

        return price.quantize(precision, rounding=ROUND_HALF_UP)

    def generate_risk_info(
        self,
        account: AccountSnapshot,
        position_size: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        direction: Direction,
    ) -> str:
        """
        Generate human-readable risk summary.

        Args:
            account: Current account snapshot
            position_size: Calculated position size
            entry_price: Entry price
            stop_loss: Stop-loss level
            direction: Signal direction

        Returns:
            Risk summary string
        """
        # Calculate actual risk amount
        stop_distance = abs(entry_price - stop_loss)
        actual_risk = stop_distance * position_size

        # Format as percentage
        loss_percent = self.config.max_loss_percent * Decimal(100)

        return f"Risk {loss_percent:.2f}% = {actual_risk:.2f} USDT"

    def calculate_signal_result(
        self,
        kline: KlineData,
        account: AccountSnapshot,
        direction: Direction,
        tags: List[Dict[str, str]] = None,
        kline_timestamp: int = 0,
        strategy_name: str = "unknown",
        score: float = 0.0,
    ) -> SignalResult:
        """
        Calculate complete signal result with risk parameters.

        Args:
            kline: K-line data where signal was detected
            account: Current account snapshot
            direction: Signal direction
            tags: Dynamic filter tags e.g., [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
            kline_timestamp: K-line close timestamp in milliseconds
            strategy_name: Strategy name that generated this signal
            score: Pattern quality score (0.0 ~ 1.0)

        Returns:
            Complete SignalResult with all fields populated
        """
        # Entry price is the current close price
        entry_price = kline.close

        # Calculate stop-loss
        stop_loss = self.calculate_stop_loss(kline, direction)

        # Calculate position size and leverage
        position_size, leverage = self.calculate_position_size(
            account, entry_price, stop_loss, direction
        )

        # Generate risk info
        risk_info = self.generate_risk_info(
            account, position_size, entry_price, stop_loss, direction
        )

        return SignalResult(
            symbol=kline.symbol,
            timeframe=kline.timeframe,
            direction=direction,
            entry_price=self._quantize_price(entry_price, entry_price),
            suggested_stop_loss=stop_loss,
            suggested_position_size=position_size,
            current_leverage=leverage,
            tags=tags or [],
            risk_reward_info=risk_info,
            kline_timestamp=kline_timestamp,
            strategy_name=strategy_name,
            score=score,
        )
