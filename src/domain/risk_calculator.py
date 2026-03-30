"""
Risk Calculator - Position sizing and stop-loss calculation.
All calculations use Decimal for precision, no float allowed.
"""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Tuple, List, Dict, Any, Optional
import json

from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)

from .models import (
    KlineData,
    SignalResult,
    Direction,
    AccountSnapshot,
    PositionInfo,
    RiskConfig,
    TakeProfitConfig,
    TakeProfitLevel,
)


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

    # S6-4: 最小止损距离（防止止损距离过小导致仓位为 0）
    MIN_STOP_LOSS_RATIO = Decimal("0.001")  # 0.1%

    def __init__(self, config: RiskConfig, take_profit_config: Optional[TakeProfitConfig] = None):
        """
        Initialize risk calculator.

        Args:
            config: Risk configuration
            take_profit_config: Optional take profit configuration (uses default if not provided)
        """
        self.config = config
        self.take_profit_config = take_profit_config or self._get_default_take_profit_config()
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
        logger.debug(f"止损计算：direction={direction.value}, entry={kline.close}")

        if direction == Direction.LONG:
            # Stop loss slightly below the Pinbar low
            # Use the low of the Pinbar candle
            stop_loss = kline.low
        else:  # SHORT
            # Stop loss slightly above the Pinbar high
            stop_loss = kline.high

        stop_loss = self._quantize_price(stop_loss, kline.close)

        # S6-4: 添加最小止损距离检查（≥ 0.1%），防止止损距离过小导致仓位为 0
        entry_price = kline.close
        min_stop_distance = entry_price * self.MIN_STOP_LOSS_RATIO

        if direction == Direction.LONG:
            # 对于 LONG，止损必须低于入场价至少 0.1%
            min_stop_loss = entry_price - min_stop_distance
            if stop_loss > min_stop_loss:
                # 止损距离太小，调整到最小允许值
                stop_loss = min_stop_loss
                logger.warning(f"止损距离过小，已调整到最小允许值：entry={entry_price}, stop_loss={stop_loss}")
        else:  # SHORT
            # 对于 SHORT，止损必须高于入场价至少 0.1%
            min_stop_loss = entry_price + min_stop_distance
            if stop_loss < min_stop_loss:
                # 止损距离太小，调整到最小允许值
                stop_loss = min_stop_loss
                logger.warning(f"止损距离过小，已调整到最小允许值：entry={entry_price}, stop_loss={stop_loss}")

        return stop_loss

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
        where Risk_Amount = Available_Balance * Max_Loss_Percent

        Dynamic risk adjustment (Scheme B):
        - Considers current position exposure
        - Reduces risk when approaching max_total_exposure limit

        Args:
            account: Current account snapshot
            entry_price: Suggested entry price
            stop_loss: Calculated stop-loss level
            direction: Signal direction

        Returns:
            Tuple of (position_size, leverage_to_use)
        """
        logger.debug(f"仓位计算：balance={account.total_balance}, risk={self.config.max_loss_percent}")

        # Handle zero/negative balance
        if account.total_balance <= Decimal(0):
            return Decimal(0), 1

        if account.available_balance <= Decimal(0):
            return Decimal(0), 1

        # Step 1: Calculate current total exposure from all positions
        total_position_value = sum(
            pos.size * pos.entry_price for pos in account.positions
        )

        # Step 2: Calculate current exposure ratio
        current_exposure_ratio = (
            total_position_value / account.total_balance
            if account.total_balance > 0
            else Decimal(0)
        )

        # Step 3: Calculate available exposure room
        available_exposure = max(
            Decimal(0),
            self.config.max_total_exposure - current_exposure_ratio
        )

        # Step 4: Calculate base risk amount using available balance
        base_risk_amount = account.available_balance * self.config.max_loss_percent

        # Step 5: Apply exposure limit - reduce risk if approaching limit
        exposure_limited_risk = account.available_balance * available_exposure
        risk_amount = min(base_risk_amount, exposure_limited_risk)

        # If no risk budget available, return zero position
        if risk_amount <= Decimal(0):
            return Decimal(0), 1

        # Step 6: Calculate stop-loss distance (absolute price difference)
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == Decimal(0):
            from .exceptions import DataQualityWarning
            raise DataQualityWarning("Stop loss distance is zero (doji candle)", "W-001")

        # Step 7: Calculate position size: risk_amount / stop_distance
        position_size = risk_amount / stop_distance

        # Step 8: Apply leverage cap
        max_position_value = account.available_balance * Decimal(self.config.max_leverage)
        max_position_size = max_position_value / entry_price
        position_size = min(position_size, max_position_size)

        # Step 9: Calculate leverage to use
        position_value = position_size * entry_price
        leverage_required = position_value / account.available_balance if account.available_balance > 0 else Decimal(1)
        leverage_to_use = min(
            int(leverage_required.quantize(Decimal("1"), rounding=ROUND_DOWN)) + 1,
            self.config.max_leverage,
        )
        leverage_to_use = max(leverage_to_use, 1)

        # Step 10: Quantize to reasonable precision
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

    def _get_default_take_profit_config(self) -> TakeProfitConfig:
        """获取默认止盈配置"""
        return TakeProfitConfig(
            enabled=True,
            levels=[
                TakeProfitLevel(id="TP1", position_ratio=Decimal("0.5"), risk_reward=Decimal("1.5")),
                TakeProfitLevel(id="TP2", position_ratio=Decimal("0.5"), risk_reward=Decimal("3.0")),
            ]
        )

    def calculate_take_profit_levels(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        direction: Direction,
        config: Optional[TakeProfitConfig] = None,
    ) -> List[Dict[str, str]]:
        """
        计算多级别止盈价格

        核心公式:
        - LONG: TP = Entry + (|Entry - Stop| × RiskReward)
        - SHORT: TP = Entry - (|Entry - Stop| × RiskReward)

        Args:
            entry_price: 入场价格
            stop_loss: 止损价格
            direction: 方向 (LONG/SHORT)
            config: 止盈配置（可选，使用默认配置如果为空）

        Returns:
            止盈级别列表，结构：[{id, position_ratio, risk_reward, price}, ...]
        """
        # 如果未提供配置，使用默认配置
        if config is None:
            config = self._get_default_take_profit_config()

        # 如果配置禁用，返回空列表
        if not config.enabled:
            return []

        stop_distance = abs(entry_price - stop_loss)
        levels = []

        for level in config.levels:
            if direction == Direction.LONG:
                tp_price = entry_price + (stop_distance * level.risk_reward)
            else:  # SHORT
                tp_price = entry_price - (stop_distance * level.risk_reward)

            quantized_price = self._quantize_price(tp_price, entry_price)

            levels.append({
                "id": level.id,
                "position_ratio": str(level.position_ratio),
                "risk_reward": str(level.risk_reward),
                "price": str(quantized_price),
            })

        return levels

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

        # Calculate take profit levels (S6-3)
        take_profit_levels = self.calculate_take_profit_levels(
            entry_price, stop_loss, direction, self.take_profit_config
        )

        logger.info(f"风险计算完成：stop_loss={stop_loss}, position_size={position_size}, leverage={leverage}, take_profit_levels={len(take_profit_levels)}")

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
            take_profit_levels=take_profit_levels,
        )
