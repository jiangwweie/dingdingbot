"""
Backtester - Stateless backtesting sandbox for strategy validation.

Key Design Principles:
1. **Sandbox Isolation**: Never calls global ConfigManager. Uses isolated config.
2. **Stateless Execution**: Each backtest run is independent.
3. **Diagnostic Output**: Returns detailed statistics, not just PnL.
4. **Dynamic Rule Engine Support**: Supports both legacy and new dynamic strategy definitions.
"""
import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from src.domain.models import (
    KlineData,
    Direction,
    TrendDirection,
    MtfStatus,
    PatternResult,
    FilterResult,
    SignalAttempt,
    BacktestRequest,
    BacktestReport,
    SignalStats,
    StrategyDefinition,
)
from src.domain.strategy_engine import (
    StrategyEngine,
    StrategyConfig,
    PinbarConfig,
    StrategyRunner,
    PinbarStrategy,
    EmaTrendFilter,
    MtfFilter,
    DynamicStrategyRunner,
    StrategyWithFilters,
    create_dynamic_runner,
)
from src.domain.filter_factory import FilterFactory
from src.domain.risk_calculator import RiskCalculator, RiskConfig
from src.domain.models import AccountSnapshot
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.logger import logger


# ============================================================
# Isolated Strategy Runner for Backtesting (Legacy Support)
# ============================================================
@dataclass
class IsolatedStrategyConfig:
    """Isolated configuration for backtest strategy runner (legacy)."""
    pinbar_config: PinbarConfig
    trend_filter_enabled: bool
    mtf_validation_enabled: bool
    ema_period: int
    risk_config: RiskConfig


class IsolatedStrategyRunner:
    """
    Private strategy runner for backtesting (legacy implementation).
    Uses isolated config, never references global ConfigManager.

    Note: For new dynamic rule engine, use DynamicStrategyRunner directly.
    """

    def __init__(self, config: IsolatedStrategyConfig):
        self._config = config

        # Build strategy and filters
        self._pinbar_strategy = PinbarStrategy(config.pinbar_config)
        self._ema_filter = EmaTrendFilter(period=config.ema_period, enabled=config.trend_filter_enabled)
        self._mtf_filter = MtfFilter(enabled=config.mtf_validation_enabled)

        self._runner = StrategyRunner(
            strategies=[self._pinbar_strategy],
            filters=[self._ema_filter],
            mtf_filter=self._mtf_filter,
        )

    def update_state(self, kline: KlineData) -> None:
        """Update internal state (EMA) for each kline."""
        self._ema_filter.update(kline, kline.symbol, kline.timeframe)

    def run(
        self,
        kline: KlineData,
        higher_tf_trends: Dict[str, TrendDirection],
    ) -> SignalAttempt:
        """Run strategy on a single kline."""
        # Get current trend
        current_trend = self._ema_filter.get_trend(kline, kline.symbol, kline.timeframe)

        # Run strategy
        return self._runner.run(kline, higher_tf_trends, current_trend)


# ============================================================
# Backtest Engine with Dynamic Rule Engine Support
# ============================================================
class Backtester:
    """
    Stateless backtesting engine.

    Usage:
        backtester = Backtester(exchange_gateway)
        report = await backtester.run_backtest(request)
    """

    # MTF mapping (same as StrategyEngine)
    MTF_MAPPING = {
        "15m": "1h",
        "1h": "4h",
        "4h": "1d",
        "1d": "1w",
    }

    def __init__(self, exchange_gateway: ExchangeGateway):
        """
        Initialize backtester.

        Args:
            exchange_gateway: Exchange gateway for fetching historical data
        """
        self._gateway = exchange_gateway

    async def run_backtest(
        self,
        request: BacktestRequest,
        account_snapshot: Optional[AccountSnapshot] = None,
        repository = None,  # SignalRepository for saving signals (always saved if provided)
    ) -> BacktestReport:
        """
        Run backtest with isolated config sandbox.

        Supports both:
        1. Legacy mode: Simple pinbar + EMA + MTF config
        2. Dynamic rule engine mode: Multiple strategies with custom filter chains

        Backtest signals are automatically saved to database with source='backtest'.
        Signals can be viewed in the Signals page with K-line chart visualization.

        Args:
            request: Backtest request parameters
            account_snapshot: Optional account snapshot for position sizing.
                              If not provided, uses a default snapshot.
            repository: SignalRepository instance for saving signals

        Returns:
            BacktestReport with detailed statistics
        """
        # Determine mode: Dynamic rule engine or legacy
        use_dynamic = request.strategies is not None and len(request.strategies) > 0

        if use_dynamic:
            # Step 1: Build dynamic strategy runner from strategy definitions
            runner = self._build_dynamic_runner(request.strategies)
        else:
            # Step 1: Build isolated strategy config (legacy mode)
            strategy_config = self._build_strategy_config(request)
            runner = IsolatedStrategyRunner(strategy_config)

        # Step 2: Fetch historical K-line data
        klines = await self._fetch_klines(request)

        if not klines:
            raise ValueError("No K-line data fetched for backtest")

        # Step 3: Create mock account if not provided
        if account_snapshot is None:
            account_snapshot = AccountSnapshot(
                total_balance=Decimal("10000"),  # Default $10,000
                available_balance=Decimal("10000"),
                unrealized_pnl=Decimal("0"),
                positions=[],
                timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            )

        # Step 4: Run backtest
        if use_dynamic:
            attempts, higher_tf_data = await self._run_dynamic_strategy_loop(
                runner, klines, request
            )
        else:
            attempts, higher_tf_data = await self._run_strategy_loop(
                runner, klines, request
            )

        # Step 5: Calculate statistics
        signal_stats = self._calculate_signal_stats(attempts)
        reject_reasons = self._calculate_reject_reasons(attempts)

        # Step 5.5: Save signals to database (if repository is provided)
        saved_count = 0
        if repository is not None:
            saved_count = await self._save_backtest_signals(
                attempts, klines, request, repository
            )
            logger.info(f"Saved {saved_count} backtest signals to database")

        # Step 6: Simulate win rate (simplified - based on stop-loss distance)
        simulated_win_rate, avg_gain, avg_loss = await self._simulate_win_rate(
            attempts, klines, request, RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)
        )

        # Step 7: Build report
        report = BacktestReport(
            symbol=request.symbol,
            timeframe=request.timeframe,
            candles_analyzed=len(klines),
            start_timestamp=klines[0].timestamp if klines else 0,
            end_timestamp=klines[-1].timestamp if klines else 0,
            signal_stats=signal_stats,
            reject_reasons=reject_reasons,
            simulated_win_rate=simulated_win_rate,
            simulated_avg_gain=avg_gain,
            simulated_avg_loss=avg_loss,
            attempts=[self._attempt_to_dict(a) for a in attempts],
        )

        logger.info(
            f"Backtest completed: {request.symbol} {request.timeframe}, "
            f"{len(klines)} candles, {signal_stats.signals_fired} signals"
        )

        return report

    def _build_dynamic_runner(self, strategy_definitions: List[StrategyDefinition]) -> DynamicStrategyRunner:
        """Build DynamicStrategyRunner from strategy definitions."""
        from src.domain.models import StrategyDefinition

        # 手动反序列化为 StrategyDefinition 对象
        # 因为 BacktestRequest.strategies 使用 List[Dict] 而非 List[StrategyDefinition]
        strategies = []
        for strat_def in strategy_definitions:
            if isinstance(strat_def, StrategyDefinition):
                strategies.append(strat_def)
            else:
                # 从 dict 反序列化
                try:
                    strategies.append(StrategyDefinition(**strat_def))
                except Exception as e:
                    logger.warning(f"Failed to deserialize strategy: {e}")
                    continue

        return create_dynamic_runner(strategies)

    def _build_strategy_config(self, request: BacktestRequest) -> IsolatedStrategyConfig:
        """Build isolated strategy config from request."""
        # Default pinbar config
        pinbar_config = PinbarConfig(
            min_wick_ratio=request.min_wick_ratio or Decimal("0.6"),
            max_body_ratio=request.max_body_ratio or Decimal("0.3"),
            body_position_tolerance=request.body_position_tolerance or Decimal("0.1"),
        )

        # Default strategy flags
        trend_filter = request.trend_filter_enabled if request.trend_filter_enabled is not None else True
        mtf_validation = request.mtf_validation_enabled if request.mtf_validation_enabled is not None else True

        # Risk config for position sizing
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),  # Default 1% risk per trade
            max_leverage=20,  # Default max leverage
        )

        return IsolatedStrategyConfig(
            pinbar_config=pinbar_config,
            trend_filter_enabled=trend_filter,
            mtf_validation_enabled=mtf_validation,
            ema_period=60,  # EMA60
            risk_config=risk_config,
        )

    async def _fetch_klines(self, request: BacktestRequest) -> List[KlineData]:
        """Fetch historical K-line data."""
        try:
            # 检查是否有时间范围参数
            if request.start_time and request.end_time:
                # 计算需要的 K 线数量
                duration_ms = int(request.end_time) - int(request.start_time)
                timeframe_minutes = self._parse_timeframe(request.timeframe)
                expected_bars = duration_ms // (timeframe_minutes * 60 * 1000)
                # 添加 20% 缓冲，并确保至少满足 limit 要求
                limit = max(int(expected_bars * 1.2), request.limit, 1000)
                logger.info(f"Time range specified: fetching ~{expected_bars} bars (limit: {limit})")
            else:
                limit = request.limit

            klines = await self._gateway.fetch_historical_ohlcv(
                symbol=request.symbol,
                timeframe=request.timeframe,
                limit=limit,
            )

            # 按时间范围过滤
            if request.start_time and request.end_time:
                start_ts = int(request.start_time)
                end_ts = int(request.end_time)
                filtered_klines = [k for k in klines if start_ts <= k.timestamp <= end_ts]
                logger.info(f"Filtered from {len(klines)} to {len(filtered_klines)} candles within time range")
                klines = filtered_klines

            logger.info(f"Fetched {len(klines)} candles for {request.symbol} {request.timeframe}")
            return klines
        except Exception as e:
            logger.error(f"Failed to fetch K-lines: {e}")
            raise

    def _parse_timeframe(self, timeframe: str) -> int:
        """解析时间框架为分钟数"""
        mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
        return mapping.get(timeframe, 15)

    async def _run_strategy_loop(
        self,
        runner: IsolatedStrategyRunner,
        klines: List[KlineData],
        request: BacktestRequest,
    ) -> Tuple[List[SignalAttempt], Dict[str, Dict[str, TrendDirection]]]:
        """
        Run strategy on all K-lines.

        Returns:
            Tuple of (attempts, higher_tf_data)
        """
        attempts = []
        higher_tf_data = {}  # {timestamp: {timeframe: TrendDirection}}

        # We need to simulate higher timeframe data
        # For simplicity, we'll fetch it separately
        higher_tf = self.MTF_MAPPING.get(request.timeframe)
        higher_tf_klines = {}

        if higher_tf:
            try:
                # Calculate limit for higher timeframe data
                # Must ensure coverage of the klines time range
                if klines:
                    min_kline_ts = min(k.timestamp for k in klines)
                    max_kline_ts = max(k.timestamp for k in klines)

                    # Calculate how many higher TF candles are needed to cover from max_kline_ts back to min_kline_ts
                    # But we also need to ensure the OLDEST 4h candle <= min_kline_ts
                    # Since exchange returns from "now" backwards, we need to calculate:
                    # limit = (max_kline_ts - min_kline_ts) / (higher_tf_interval) + buffer
                    higher_tf_minutes = self._parse_timeframe(higher_tf)
                    duration_ms = max_kline_ts - min_kline_ts
                    expected_higher_tf_bars = max(
                        int(duration_ms / (higher_tf_minutes * 60 * 1000)) + 5,  # +5 for edge cases
                        100  # minimum to ensure coverage
                    )

                    # Also consider request.start_time and request.end_time if provided
                    # This is the ACTUAL time range we need to cover
                    if request.start_time and request.end_time:
                        start_ts = int(request.start_time)
                        end_ts = int(request.end_time)
                        full_duration_ms = end_ts - start_ts
                        full_expected_bars = int(full_duration_ms / (higher_tf_minutes * 60 * 1000)) + 5
                        expected_higher_tf_bars = max(expected_higher_tf_bars, full_expected_bars, 1000)

                    # IMPORTANT: The exchange returns candles from "latest available" backwards.
                    # We need to ensure that the oldest returned candle has timestamp <= min_kline_ts
                    # Conservative approach: always fetch at least 1000 candles for higher TF
                    limit = max(expected_higher_tf_bars, 1000)

                    logger.info(f"Fetching {limit} {higher_tf} candles for MTF (klines range: {min_kline_ts}-{max_kline_ts}, duration: {duration_ms}ms)")
                else:
                    limit = max(request.limit, 1000)

                higher_tf_klines_list = await self._gateway.fetch_historical_ohlcv(
                    symbol=request.symbol,
                    timeframe=higher_tf,
                    limit=limit,
                )

                # Build a map of timestamp -> trend
                for kline in higher_tf_klines_list:
                    ts = kline.timestamp
                    higher_tf_data[ts] = {
                        higher_tf: TrendDirection.BULLISH if kline.close > kline.open else TrendDirection.BEARISH
                    }

                logger.info(f"Loaded {len(higher_tf_data)} {higher_tf} candles for MTF validation")
            except Exception as e:
                logger.warning(f"Failed to fetch higher TF data for MTF: {e}")

        # Process each K-line
        for kline in klines:
            # Update internal state
            runner.update_state(kline)

            # Get higher TF trends for this timestamp
            # Use the closest available higher TF data
            higher_tf_trends = self._get_closest_higher_tf_trends(
                kline.timestamp, higher_tf_data
            )

            # Run strategy
            attempt = runner.run(kline, higher_tf_trends)
            attempts.append(attempt)

        return attempts, higher_tf_data

    async def _run_dynamic_strategy_loop(
        self,
        runner: DynamicStrategyRunner,
        klines: List[KlineData],
        request: BacktestRequest,
    ) -> Tuple[List[SignalAttempt], Dict[str, Dict[str, TrendDirection]]]:
        """
        Run dynamic strategy runner on all K-lines.

        Returns:
            Tuple of (attempts, higher_tf_data)
        """
        attempts = []
        higher_tf_data = {}  # {timestamp: {timeframe: TrendDirection}}

        # Fetch higher timeframe data for MTF
        higher_tf = self.MTF_MAPPING.get(request.timeframe)
        higher_tf_klines = {}

        if higher_tf:
            try:
                # Calculate limit for higher timeframe data
                # Must ensure coverage of the klines time range
                if klines:
                    min_kline_ts = min(k.timestamp for k in klines)
                    max_kline_ts = max(k.timestamp for k in klines)

                    # Calculate how many higher TF candles are needed to cover from max_kline_ts back to min_kline_ts
                    # But we also need to ensure the OLDEST 4h candle <= min_kline_ts
                    # Since exchange returns from "now" backwards, we need to calculate:
                    # limit = (max_kline_ts - min_kline_ts) / (higher_tf_interval) + buffer
                    higher_tf_minutes = self._parse_timeframe(higher_tf)
                    duration_ms = max_kline_ts - min_kline_ts
                    expected_higher_tf_bars = max(
                        int(duration_ms / (higher_tf_minutes * 60 * 1000)) + 5,  # +5 for edge cases
                        100  # minimum to ensure coverage
                    )

                    # Also consider request.start_time and request.end_time if provided
                    # This is the ACTUAL time range we need to cover
                    if request.start_time and request.end_time:
                        start_ts = int(request.start_time)
                        end_ts = int(request.end_time)
                        full_duration_ms = end_ts - start_ts
                        full_expected_bars = int(full_duration_ms / (higher_tf_minutes * 60 * 1000)) + 5
                        expected_higher_tf_bars = max(expected_higher_tf_bars, full_expected_bars, 1000)

                    # IMPORTANT: The exchange returns candles from "latest available" backwards.
                    # We need to ensure that the oldest returned candle has timestamp <= min_kline_ts
                    # Conservative approach: always fetch at least 1000 candles for higher TF
                    limit = max(expected_higher_tf_bars, 1000)

                    logger.info(f"Fetching {limit} {higher_tf} candles for MTF (klines range: {min_kline_ts}-{max_kline_ts}, duration: {duration_ms}ms)")
                else:
                    limit = max(request.limit, 1000)

                higher_tf_klines_list = await self._gateway.fetch_historical_ohlcv(
                    symbol=request.symbol,
                    timeframe=higher_tf,
                    limit=limit,
                )

                # Build a map of timestamp -> trend
                for kline in higher_tf_klines_list:
                    ts = kline.timestamp
                    higher_tf_data[ts] = {
                        higher_tf: TrendDirection.BULLISH if kline.close > kline.open else TrendDirection.BEARISH
                    }

                logger.info(f"Loaded {len(higher_tf_data)} {higher_tf} candles for MTF validation")
            except Exception as e:
                logger.warning(f"Failed to fetch higher TF data for MTF: {e}")

        # Process each K-line
        for kline in klines:
            # Update internal state (all stateful filters)
            runner.update_state(kline)

            # Get higher TF trends for this timestamp
            higher_tf_trends = self._get_closest_higher_tf_trends(
                kline.timestamp, higher_tf_data
            )

            # Run all strategies with their filter chains
            strat_attempts = runner.run_all(kline, higher_tf_trends)
            attempts.extend(strat_attempts)

        return attempts, higher_tf_data

    def _get_closest_higher_tf_trends(
        self,
        timestamp: int,
        higher_tf_data: Dict[int, Dict[str, TrendDirection]],
    ) -> Dict[str, TrendDirection]:
        """Get the closest available higher timeframe trends."""
        if not higher_tf_data:
            return {}

        # Find the closest timestamp <= current timestamp
        closest_ts = None
        for ts in higher_tf_data:
            if ts <= timestamp:
                if closest_ts is None or ts > closest_ts:
                    closest_ts = ts

        if closest_ts is None:
            return {}

        return higher_tf_data.get(closest_ts, {})

    def _calculate_signal_stats(self, attempts: List[SignalAttempt]) -> SignalStats:
        """Calculate signal statistics from attempts."""
        stats = SignalStats()

        for attempt in attempts:
            stats.total_attempts += 1

            if attempt.final_result == "SIGNAL_FIRED":
                stats.signals_fired += 1
                if attempt.direction:
                    if attempt.direction == Direction.LONG:
                        stats.long_signals += 1
                    else:
                        stats.short_signals += 1

                # By strategy
                strategy = attempt.strategy_name
                stats.by_strategy[strategy] = stats.by_strategy.get(strategy, 0) + 1

            elif attempt.final_result == "NO_PATTERN":
                stats.no_pattern += 1

            elif attempt.final_result == "FILTERED":
                stats.filtered_out += 1

                # Determine which filter rejected
                for filter_name, filter_result in attempt.filter_results:
                    if not filter_result.passed:
                        stats.filtered_by_filters[filter_name] = stats.filtered_by_filters.get(filter_name, 0) + 1
                        break

        return stats

    def _calculate_reject_reasons(self, attempts: List[SignalAttempt]) -> Dict[str, int]:
        """Calculate rejection reason distribution generically."""
        reasons: Dict[str, int] = {}

        for attempt in attempts:
            if attempt.final_result != "FILTERED":
                continue

            for filter_name, filter_result in attempt.filter_results:
                if not filter_result.passed:
                    reason = filter_result.reason
                    reasons[reason] = reasons.get(reason, 0) + 1
                    break

        return reasons

    async def _simulate_win_rate(
        self,
        attempts: List[SignalAttempt],
        klines: List[KlineData],
        request: BacktestRequest,
        risk_config: RiskConfig,
    ) -> Tuple[float, float, float]:
        """
        Simulate win rate based on stop-loss distance.

        This is a simplified simulation - in a real backtest, you would
        need to track actual price movement after entry.

        For this implementation, we use a heuristic:
        - If the signal fired, we check subsequent candles
        - Win if price moved in signal direction by 2x the stop-loss distance
        - Loss if price hit stop-loss first
        """
        fired_signals = [a for a in attempts if a.final_result == "SIGNAL_FIRED"]

        if not fired_signals:
            return 0.0, 0.0, 0.0

        wins = 0
        losses = 0
        total_gain = Decimal("0")
        total_loss = Decimal("0")

        # Build kline map by timestamp for quick lookup
        kline_map = {k.timestamp: k for k in klines}

        for i, attempt in enumerate(fired_signals):
            # Find the entry kline
            entry_kline = None
            for k in klines:
                if k.timestamp == attempt.kline_timestamp:
                    entry_kline = k
                    break

            if not entry_kline:
                continue

            # Calculate stop-loss level
            if attempt.direction == Direction.LONG:
                stop_loss = entry_kline.low
                take_profit_target = entry_kline.close + (entry_kline.close - stop_loss) * 2
            else:  # SHORT
                stop_loss = entry_kline.high
                take_profit_target = entry_kline.close - (stop_loss - entry_kline.close) * 2

            # Look at subsequent candles to determine outcome
            outcome = self._determine_trade_outcome(
                klines, attempt.kline_timestamp, entry_kline,
                stop_loss, take_profit_target, attempt.direction
            )

            if outcome == "WIN":
                wins += 1
                total_gain += Decimal("2")  # 2R gain
            elif outcome == "LOSS":
                losses += 1
                total_loss += Decimal("1")  # 1R loss

        total_trades = wins + losses
        if total_trades == 0:
            return 0.0, 0.0, 0.0

        win_rate = wins / total_trades
        avg_gain = float(total_gain / wins) if wins > 0 else 0.0
        avg_loss = float(total_loss / losses) if losses > 0 else 0.0

        return win_rate, avg_gain, avg_loss

    def _determine_trade_outcome(
        self,
        klines: List[KlineData],
        entry_timestamp: int,
        entry_kline: KlineData,
        stop_loss: Decimal,
        take_profit: Decimal,
        direction: Direction,
    ) -> Optional[str]:
        """
        Determine if a trade would have won or lost.

        Looks at subsequent candles and checks if:
        - Take profit was hit first -> WIN
        - Stop loss was hit first -> LOSS
        """
        found_entry = False

        for kline in klines:
            if not found_entry:
                if kline.timestamp == entry_timestamp:
                    found_entry = True
                continue

            # Check if price hit stop loss or take profit
            if direction == Direction.LONG:
                # Check stop loss (low of candle)
                if kline.low <= stop_loss:
                    return "LOSS"
                # Check take profit (high of candle)
                if kline.high >= take_profit:
                    return "WIN"
            else:  # SHORT
                # Check stop loss (high of candle)
                if kline.high >= stop_loss:
                    return "LOSS"
                # Check take profit (low of candle)
                if kline.low <= take_profit:
                    return "WIN"

        # No clear outcome (trade still open or reached end of data)
        return None

    def _attempt_to_dict(self, attempt: SignalAttempt) -> Dict[str, Any]:
        """Convert SignalAttempt to dictionary for JSON serialization."""
        return {
            "strategy_name": attempt.strategy_name,
            "final_result": attempt.final_result,
            "direction": attempt.direction.value if attempt.direction else None,
            "kline_timestamp": attempt.kline_timestamp,
            "pattern_score": attempt.pattern.score if attempt.pattern else None,
            "filter_results": [
                {"filter": name, "passed": r.passed, "reason": r.reason}
                for name, r in attempt.filter_results
            ],
        }

    async def _save_backtest_signals(
        self,
        attempts: List[SignalAttempt],
        klines: List[KlineData],
        request: BacktestRequest,
        repository,  # SignalRepository
    ) -> int:
        """
        Save fired signals from backtest to database.

        Args:
            attempts: List of signal attempts
            klines: List of K-line data
            request: Backtest request
            repository: SignalRepository instance

        Returns:
            Number of signals saved
        """
        from src.domain.risk_calculator import RiskCalculator
        from src.domain.models import SignalResult, AccountSnapshot

        saved_count = 0
        risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)
        calculator = RiskCalculator(risk_config)

        # Create mock account for position sizing
        account_snapshot = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        )

        # Build kline map for quick lookup
        kline_map = {k.timestamp: k for k in klines}

        for attempt in attempts:
            if attempt.final_result != "SIGNAL_FIRED" or not attempt.pattern:
                continue

            # Get entry kline
            entry_kline = kline_map.get(attempt.kline_timestamp)
            if not entry_kline:
                continue

            # Calculate stop loss
            stop_loss = calculator.calculate_stop_loss(
                entry_kline, attempt.pattern.direction
            )

            # Calculate position size
            position_size, leverage = calculator.calculate_position_size(
                account_snapshot,
                entry_kline.close,
                stop_loss,
                attempt.pattern.direction,
            )

            # Generate dynamic tags from filter_results (same as real-time signals)
            tags = self._generate_tags_from_filter_results(attempt.filter_results)
            # Add backtest source tag
            tags.append({"name": "Source", "value": "Backtest"})

            # Build SignalResult
            signal = SignalResult(
                symbol=request.symbol,
                timeframe=request.timeframe,
                direction=attempt.pattern.direction,
                entry_price=entry_kline.close,
                suggested_stop_loss=stop_loss,
                suggested_position_size=position_size,
                current_leverage=leverage,
                tags=tags,
                risk_reward_info=f"Risk {risk_config.max_loss_percent*100}% = {calculator._quantize_price(account_snapshot.available_balance * risk_config.max_loss_percent, entry_kline.close)} USDT",
                status="PENDING",
                pnl_ratio=0.0,
                kline_timestamp=attempt.kline_timestamp,
                strategy_name=attempt.strategy_name,
                score=attempt.pattern.score,
            )

            # Save to database with source='backtest'
            await repository.save_signal(signal, source="backtest")
            saved_count += 1

        return saved_count

    def _generate_tags_from_filter_results(self, filter_results: list) -> List[Dict[str, str]]:
        """
        Generate dynamic tags from filter results (same as signal_pipeline.py).

        Args:
            filter_results: List of (filter_name, FilterResult) tuples from attempt

        Returns:
            List of tag dicts e.g., [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
        """
        tags = []
        for filter_name, filter_result in filter_results:
            if filter_result.passed:
                if filter_name == "ema" or filter_name == "ema_trend":
                    # Extract trend direction from reason
                    trend_value = "Bullish" if "bullish" in filter_result.reason.lower() else "Bearish"
                    tags.append({"name": "EMA", "value": trend_value})
                elif filter_name == "mtf":
                    mtf_value = "Confirmed" if "confirm" in filter_result.reason.lower() else "Passed"
                    tags.append({"name": "MTF", "value": mtf_value})
                elif filter_name == "atr":
                    tags.append({"name": "ATR", "value": "Passed"})
                elif filter_name == "volume_surge":
                    tags.append({"name": "Volume", "value": "Surge"})
        return tags


# ============================================================
# Convenience function
# ============================================================
async def run_backtest(
    gateway: ExchangeGateway,
    request: BacktestRequest,
    account_snapshot: Optional[AccountSnapshot] = None,
    repository = None,  # Optional SignalRepository for saving signals
) -> BacktestReport:
    """
    Run a backtest with isolated sandbox.

    Backtest signals are automatically saved to database if repository is provided.

    Args:
        gateway: Exchange gateway for fetching data
        request: Backtest request parameters
        account_snapshot: Optional account snapshot
        repository: Optional SignalRepository for saving signals

    Returns:
        BacktestReport with detailed statistics
    """
    backtester = Backtester(gateway)
    return await backtester.run_backtest(request, account_snapshot, repository=repository)
