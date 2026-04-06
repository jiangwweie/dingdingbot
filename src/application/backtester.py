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
from typing import List, Dict, Any, Optional, Tuple, Union
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
    PMSBacktestReport,
    PositionSummary,
    Account,
    Position,
    Order,
    Signal,
    OrderStatus,
    OrderStrategy,
)
from src.domain.matching_engine import MockMatchingEngine
from src.domain.risk_manager import DynamicRiskManager
from src.domain.models import RiskManagerConfig, AccountSnapshot, RiskConfig
from src.domain.order_manager import OrderManager
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
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.historical_data_repository import HistoricalDataRepository
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

    def __init__(
        self,
        exchange_gateway: ExchangeGateway,
        data_repository: Optional[HistoricalDataRepository] = None,
    ):
        """
        Initialize backtester.

        Args:
            exchange_gateway: Exchange gateway for fetching historical data
            data_repository: Optional historical data repository for local data access.
                            If not provided, will fetch directly from exchange gateway.
        """
        self._gateway = exchange_gateway
        self._data_repo = data_repository

    async def run_backtest(
        self,
        request: BacktestRequest,
        account_snapshot: Optional[AccountSnapshot] = None,
        repository = None,  # SignalRepository for saving signals (always saved if provided)
        backtest_repository = None,  # BacktestReportRepository for saving reports
        order_repository = None,  # OrderRepository for saving orders (T4)
    ) -> Union[BacktestReport, PMSBacktestReport]:
        """
        Run backtest with isolated config sandbox.

        Supports both:
        1. Legacy mode: Simple pinbar + EMA + MTF config
        2. Dynamic rule engine mode: Multiple strategies with custom filter chains
        3. v3_pms mode: Position-level backtesting with MockMatchingEngine

        Backtest signals are automatically saved to database with source='backtest'.
        Signals can be viewed in the Signals page with K-line chart visualization.

        T4/T5/T6: Orders and backtest reports are automatically saved to database.

        Args:
            request: Backtest request parameters
            account_snapshot: Optional account snapshot for position sizing.
                              If not provided, uses a default snapshot.
            repository: SignalRepository instance for saving signals
            backtest_repository: BacktestReportRepository for saving reports
            order_repository: OrderRepository for saving orders

        Returns:
            BacktestReport (v2_classic mode) or PMSBacktestReport (v3_pms mode)
        """
        # Step 0: Load KV configs as defaults for v3_pms mode
        kv_configs = {}
        if request.mode == "v3_pms":
            try:
                from src.application.config_manager import ConfigManager
                config_manager = ConfigManager.get_instance()
                if config_manager:
                    kv_configs = await config_manager.get_backtest_configs()
                    logger.debug(f"Loaded backtest configs from KV: {kv_configs}")
                else:
                    logger.warning("ConfigManager instance not available, using code defaults")
            except Exception as e:
                logger.warning(f"Failed to load backtest configs from KV, using defaults: {e}")
                kv_configs = {}

        # Determine mode: v3_pms or dynamic rule engine or legacy
        use_v3_pms = request.mode == "v3_pms"
        use_dynamic = request.strategies is not None and len(request.strategies) > 0

        if use_v3_pms:
            # v3 PMS mode: Use MockMatchingEngine for position-level backtesting
            return await self._run_v3_pms_backtest(request, repository, backtest_repository, order_repository, kv_configs)

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

        # Step 6.5: Calculate pnl_ratio and exit_reason for each attempt (BT-4)
        risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=20)
        for attempt in attempts:
            pnl_ratio, exit_reason = self._calculate_attempt_outcome(
                attempt, klines, risk_config
            )
            attempt._pnl_ratio = pnl_ratio
            attempt._exit_reason = exit_reason

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

    async def _serialize_strategy_snapshot_for_report(
        self,
        request: BacktestRequest,
        strategy_id: str,
        strategy_name: str,
    ) -> str:
        """
        Serialize strategy configuration to JSON snapshot for storage.

        Args:
            request: Backtest request
            strategy_id: Strategy ID
            strategy_name: Strategy name

        Returns:
            JSON string of strategy snapshot
        """
        import json
        from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf

        def serialize_logic_tree(node) -> Dict[str, Any]:
            """Recursively serialize logic tree node."""
            if isinstance(node, LogicNode):
                return {
                    "type": "node",
                    "gate": node.gate,
                    "children": [serialize_logic_tree(child) for child in node.children]
                }
            elif isinstance(node, TriggerLeaf):
                return {
                    "type": "trigger",
                    "id": node.id,
                    "config": node.config.model_dump(mode="json")
                }
            elif isinstance(node, FilterLeaf):
                return {
                    "type": "filter",
                    "id": node.id,
                    "config": node.config.model_dump(mode="json")
                }
            else:
                return {}

        # Build strategy snapshot
        snapshot = {
            "id": strategy_id,
            "name": strategy_name,
            "logic_tree": None,
            "triggers": [],
            "filters": [],
        }

        # Serialize strategy definitions if provided
        if request.strategies:
            for strat_def_dict in request.strategies:
                try:
                    strat_def = StrategyDefinition(**strat_def_dict)
                    if strat_def.logic_tree:
                        snapshot["logic_tree"] = serialize_logic_tree(strat_def.logic_tree)
                    snapshot["triggers"] = [t.model_dump(mode="json") for t in strat_def.get_triggers_from_logic_tree()]
                    snapshot["filters"] = [f.model_dump(mode="json") for f in strat_def.get_filters_from_logic_tree()]
                except Exception as e:
                    logger.warning(f"Failed to serialize strategy: {e}")
        else:
            # Legacy mode: use default pinbar config
            pinbar_config = PinbarConfig(
                min_wick_ratio=request.min_wick_ratio or Decimal("0.6"),
                max_body_ratio=request.max_body_ratio or Decimal("0.3"),
                body_position_tolerance=request.body_position_tolerance or Decimal("0.1"),
            )
            snapshot["triggers"] = [{
                "type": "pinbar",
                "params": {
                    "min_wick_ratio": float(pinbar_config.min_wick_ratio),
                    "max_body_ratio": float(pinbar_config.max_body_ratio),
                    "body_position_tolerance": float(pinbar_config.body_position_tolerance),
                }
            }]
            snapshot["filters"] = [
                {"type": "ema_trend", "params": {"enabled": request.trend_filter_enabled if request.trend_filter_enabled is not None else True}},
                {"type": "mtf", "params": {"enabled": request.mtf_validation_enabled if request.mtf_validation_enabled is not None else True}},
            ]

        return json.dumps(snapshot, ensure_ascii=False)

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
        """Fetch historical K-line data using HistoricalDataRepository (local-first with fallback)."""
        try:
            # 优先使用 HistoricalDataRepository (本地 SQLite 优先)
            if self._data_repo is not None:
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

                klines = await self._data_repo.get_klines(
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    start_time=request.start_time,
                    end_time=request.end_time,
                    limit=limit,
                )

                logger.info(f"Fetched {len(klines)} candles from local DB for {request.symbol} {request.timeframe}")
                if klines:
                    return klines
                # DB 无数据时，降级到 Exchange Gateway
                logger.info("DB has no data, falling back to Exchange Gateway...")

            # 降级：直接使用 exchange gateway (旧版行为)
            if request.start_time and request.end_time:
                duration_ms = int(request.end_time) - int(request.start_time)
                timeframe_minutes = self._parse_timeframe(request.timeframe)
                expected_bars = duration_ms // (timeframe_minutes * 60 * 1000)
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

                    # CRITICAL: Exchange returns candles from "latest available" backwards.
                    # We need to ensure the oldest returned candle <= min_kline_ts.
                    # Calculate bars needed from "now" back to min_kline_ts.
                    current_ts = int(time.time() * 1000)
                    time_from_now_ms = current_ts - min_kline_ts
                    bars_from_now = int(time_from_now_ms / (higher_tf_minutes * 60 * 1000)) + 10  # +10 buffer

                    # Use the larger of the two calculations
                    limit = max(expected_higher_tf_bars, bars_from_now, 1000)

                    logger.info(f"Fetching {limit} {higher_tf} candles for MTF (klines range: {min_kline_ts}-{max_kline_ts}, need {bars_from_now} bars from now)")
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

                    # CRITICAL: Exchange returns candles from "latest available" backwards.
                    # We need to ensure the oldest returned candle <= min_kline_ts.
                    # Calculate bars needed from "now" back to min_kline_ts.
                    current_ts = int(time.time() * 1000)
                    time_from_now_ms = current_ts - min_kline_ts
                    bars_from_now = int(time_from_now_ms / (higher_tf_minutes * 60 * 1000)) + 10  # +10 buffer

                    # Use the larger of the two calculations
                    limit = max(expected_higher_tf_bars, bars_from_now, 1000)

                    logger.info(f"Fetching {limit} {higher_tf} candles for MTF (klines range: {min_kline_ts}-{max_kline_ts}, need {bars_from_now} bars from now)")
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
        """
        Get the closest available higher timeframe trends.

        CRITICAL: A higher timeframe candle is considered "closed" only when:
        higher_tf_timestamp + higher_tf_period <= current_timestamp

        This prevents the "future function" problem where unreleased candles
        are incorrectly used in MTF filtering.

        Example:
        - 1h candle at 10:00 closes at 11:00
        - At 10:15, the 10:00-11:00 candle is NOT yet closed
        - Should use 09:00 candle (closed at 10:00) instead
        """
        if not higher_tf_data:
            return {}

        # Get the higher timeframe from the first entry to calculate period
        first_entry = next(iter(higher_tf_data.values()))
        higher_tf = next(iter(first_entry.keys())) if first_entry else None

        if higher_tf is None:
            return {}

        higher_tf_period_ms = self._parse_timeframe(higher_tf) * 60 * 1000

        # Find the closest timestamp where the candle is already closed
        # Candle closes at: timestamp + period
        closest_ts = None
        for ts, trends in higher_tf_data.items():
            candle_close_time = ts + higher_tf_period_ms
            if candle_close_time <= timestamp:
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

    def _calculate_attempt_outcome(
        self,
        attempt: SignalAttempt,
        klines: List[KlineData],
        risk_config: RiskConfig,
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        Calculate pnl_ratio and exit_reason for a fired signal.

        Args:
            attempt: Signal attempt with SIGNAL_FIRED result
            klines: Historical K-line data
            risk_config: Risk configuration for stop-loss calculation

        Returns:
            Tuple of (pnl_ratio, exit_reason)
            - pnl_ratio: float or None (e.g., 2.0 for 2R gain, -1.0 for 1R loss)
            - exit_reason: str or None (e.g., "STOP_LOSS", "TAKE_PROFIT", "TIME_EXIT")
        """
        if attempt.final_result != "SIGNAL_FIRED" or not attempt.pattern:
            return None, None

        # Find entry kline
        entry_kline = None
        for k in klines:
            if k.timestamp == attempt.kline_timestamp:
                entry_kline = k
                break

        if not entry_kline:
            return None, None

        # Calculate stop-loss level
        if attempt.direction == Direction.LONG:
            stop_loss = entry_kline.low
            take_profit_target = entry_kline.close + (entry_kline.close - stop_loss) * 2
        else:  # SHORT
            stop_loss = entry_kline.high
            take_profit_target = entry_kline.close - (stop_loss - entry_kline.close) * 2

        # Determine outcome using existing logic
        outcome = self._determine_trade_outcome(
            klines,
            attempt.kline_timestamp,
            entry_kline,
            stop_loss,
            take_profit_target,
            attempt.direction,
        )

        if outcome == "WIN":
            return 2.0, "TAKE_PROFIT"  # 2R gain
        elif outcome == "LOSS":
            return -1.0, "STOP_LOSS"   # 1R loss
        else:
            return 0.0, "TIME_EXIT"    # No clear outcome

    def _attempt_to_dict(self, attempt: SignalAttempt) -> Dict[str, Any]:
        """Convert SignalAttempt to dictionary for JSON serialization.

        BT-4 归因分析扩展字段:
        - pnl_ratio: 盈亏比 (仅 SIGNAL_FIRED 信号)
        - exit_reason: 出场原因 (仅 SIGNAL_FIRED 信号)
        - metadata: 标准化元数据
        """
        return {
            "strategy_name": attempt.strategy_name,
            "final_result": attempt.final_result,
            "direction": attempt.direction.value if attempt.direction else None,
            "kline_timestamp": attempt.kline_timestamp,
            "pattern_score": attempt.pattern.score if attempt.pattern else None,
            "filter_results": [
                {
                    "filter": name,
                    "passed": r.passed,
                    "reason": r.reason,
                    "metadata": r.metadata,  # BT-4: 包含标准化 metadata
                }
                for name, r in attempt.filter_results
            ],
            # BT-4 新增字段
            "pnl_ratio": attempt.pnl_ratio,
            "exit_reason": attempt.exit_reason,
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

            # S6-3: Calculate take profit levels
            take_profit_levels = calculator.calculate_take_profit_levels(
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
                take_profit_levels=take_profit_levels,
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

    async def _run_v3_pms_backtest(
        self,
        request: BacktestRequest,
        repository = None,
        backtest_repository = None,
        order_repository = None,  # T4: OrderRepository for persisting orders
        kv_configs: Optional[Dict[str, Any]] = None,  # KV configs as defaults
    ) -> PMSBacktestReport:
        """
        Run v3 PMS mode backtest with MockMatchingEngine.

        Core logic:
        1. Generate signals from strategy definitions (or legacy pinbar)
        2. Create Orders from signals
        3. Use MockMatchingEngine to simulate order execution
        4. Track Position and Account state changes
        5. Generate PMSBacktestReport with detailed position-level statistics
        6. T4: Persist all orders to database if order_repository is provided

        Config Priority:
        1. API request parameters (highest priority)
        2. KV configs (config_entries_v2)
        3. Code defaults (lowest priority)

        Args:
            request: Backtest request with v3_pms mode
            repository: Optional SignalRepository for saving signals
            order_repository: Optional OrderRepository for saving orders
            kv_configs: Optional KV configs dict with backtest defaults

        Returns:
            PMSBacktestReport with detailed position-level statistics
        """
        from src.domain.matching_engine import MockMatchingEngine
        from src.domain.risk_calculator import RiskCalculator
        from src.domain.models import OrderType, OrderRole, OrderStrategy
        from src.domain.order_manager import OrderManager
        import uuid

        # Step 1: Merge configs with priority: request > KV > code defaults
        slippage_rate = request.slippage_rate or (kv_configs.get('slippage_rate') if kv_configs else None) or Decimal('0.001')
        fee_rate = request.fee_rate or (kv_configs.get('fee_rate') if kv_configs else None) or Decimal('0.0004')
        initial_balance = request.initial_balance or (kv_configs.get('initial_balance') if kv_configs else None) or Decimal('10000')
        tp_slippage_rate = (
            request.tp_slippage_rate
            or (kv_configs.get('tp_slippage_rate') if kv_configs else None)
            or Decimal('0.0005')
        )  # 0.05% default

        logger.info(
            f"Running v3 PMS backtest with config: "
            f"slippage={slippage_rate}, fee={fee_rate}, "
            f"initial_balance={initial_balance}, tp_slippage={tp_slippage_rate}"
        )

        # Step 2: Initialize MockMatchingEngine with merged configs
        engine = MockMatchingEngine(
            slippage_rate=slippage_rate,
            fee_rate=fee_rate,
            tp_slippage_rate=tp_slippage_rate,
        )

        # Step 2: Fetch historical K-line data
        klines = await self._fetch_klines(request)
        if not klines:
            raise ValueError("No K-line data fetched for backtest")

        # Step 3: Build strategy runner (same as dynamic mode)
        use_dynamic = request.strategies is not None and len(request.strategies) > 0
        if use_dynamic:
            runner = self._build_dynamic_runner(request.strategies)
            strategy_id = request.strategies[0].get('id', 'unknown')
            strategy_name = request.strategies[0].get('name', 'unknown')
        else:
            strategy_config = self._build_strategy_config(request)
            runner = IsolatedStrategyRunner(strategy_config)
            strategy_id = 'pinbar'
            strategy_name = 'pinbar'

        # Step 4: Initialize Account and state tracking (use merged initial_balance)
        account = Account(
            account_id="backtest_wallet",
            total_balance=initial_balance,
            frozen_margin=Decimal('0'),
        )

        # Risk calculator for position sizing
        risk_config = RiskConfig(
            max_loss_percent=Decimal('0.01'),  # 1% risk per trade
            max_leverage=20,
        )
        calculator = RiskCalculator(risk_config)

        # State tracking
        positions_map: Dict[str, Position] = {}  # {signal_id: Position}
        active_orders: List[Order] = []  # All open orders
        position_summaries: List[PositionSummary] = []
        all_executed_orders: List[Order] = []

        # Statistics tracking
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        total_pnl = Decimal('0')
        total_fees_paid = Decimal('0')
        total_slippage_cost = Decimal('0')

        # Step 5: Generate signals and create orders
        higher_tf_data = {}  # For MTF validation

        # Fetch higher timeframe data if needed
        higher_tf = self.MTF_MAPPING.get(request.timeframe)
        if higher_tf:
            try:
                limit = max(request.limit, 1000)
                higher_tf_klines_list = await self._gateway.fetch_historical_ohlcv(
                    symbol=request.symbol,
                    timeframe=higher_tf,
                    limit=limit,
                )
                for kline in higher_tf_klines_list:
                    higher_tf_data[kline.timestamp] = {
                        higher_tf: TrendDirection.BULLISH if kline.close > kline.open else TrendDirection.BEARISH
                    }
            except Exception as e:
                logger.warning(f"Failed to fetch higher TF data for MTF: {e}")

        # Step 6: Main backtest loop
        for kline in klines:
            # Update strategy state
            runner.update_state(kline)

            # Get higher TF trends
            higher_tf_trends = self._get_closest_higher_tf_trends(kline.timestamp, higher_tf_data)

            # Run strategy to generate signals
            if use_dynamic:
                attempts = runner.run_all(kline, higher_tf_trends)
            else:
                attempt = runner.run(kline, higher_tf_trends)
                attempts = [attempt]

            # Create ENTRY orders for fired signals
            for attempt in attempts:
                if attempt.final_result == "SIGNAL_FIRED" and attempt.pattern:
                    # Create signal
                    signal_id = f"sig_{uuid.uuid4().hex[:8]}"
                    stop_loss = calculator.calculate_stop_loss(kline, attempt.pattern.direction)

                    signal = Signal(
                        id=signal_id,
                        strategy_id=attempt.strategy_name,
                        symbol=request.symbol,
                        direction=attempt.pattern.direction,
                        timestamp=kline.timestamp,
                        expected_entry=kline.close,
                        expected_sl=stop_loss,
                        pattern_score=attempt.pattern.score,
                        is_active=True,
                    )

                    # Calculate position size
                    account_snapshot = AccountSnapshot(
                        total_balance=account.total_balance,
                        available_balance=account.available_balance,
                        unrealized_pnl=Decimal('0'),
                        positions=[],
                        timestamp=kline.timestamp,
                    )
                    position_size, leverage = calculator.calculate_position_size(
                        account_snapshot,
                        kline.close,
                        stop_loss,
                        attempt.pattern.direction,
                    )

                    # Create ENTRY order using OrderManager (Phase 4)
                    # Note: TP/SL orders will be generated dynamically after ENTRY is filled
                    order_manager = OrderManager()

                    # 使用 request 中的 order_strategy，如果未提供则使用默认单 TP 策略
                    strategy = request.order_strategy or OrderStrategy(
                        id="default_single_tp",
                        name="Default Single TP",
                        tp_levels=1,
                        tp_ratios=[Decimal('1.0')],
                        tp_targets=[Decimal('1.5')],  # 默认 1.5R 止盈
                        initial_stop_loss_rr=Decimal('-1.0'),
                        trailing_stop_enabled=True,
                        oco_enabled=True,
                    )

                    entry_orders = order_manager.create_order_chain(
                        strategy=strategy,
                        signal_id=signal_id,
                        symbol=request.symbol,
                        direction=attempt.pattern.direction,
                        total_qty=position_size,
                        initial_sl_rr=Decimal('-1.0'),
                        tp_targets=strategy.tp_targets,  # 使用 strategy 配置的 tp_targets
                    )
                    active_orders.extend(entry_orders)

                    # T4: Save ENTRY orders to database
                    if order_repository is not None:
                        await order_repository.save_batch(entry_orders)
                        logger.debug(f"已保存 {len(entry_orders)} 个入场订单到数据库")

            # Step 7: Run MockMatchingEngine
            executed = engine.match_orders_for_kline(
                kline=kline,
                active_orders=active_orders,
                positions_map=positions_map,
                account=account,
            )

            # Step 7.5: Handle ENTRY filled events to dynamically generate TP/SL orders
            # OrderManager handles order chain lifecycle
            order_manager = OrderManager()
            for order in list(active_orders):  # Use list() to avoid modification during iteration
                if order.status == OrderStatus.FILLED and order.order_role == OrderRole.ENTRY:
                    # ENTRY filled: dynamically generate TP and SL orders based on actual_exec_price
                    new_orders = await order_manager.handle_order_filled(
                        filled_order=order,
                        active_orders=active_orders,
                        positions_map=positions_map,
                        strategy=strategy,  # 使用 strategy 配置的 tp_targets
                        tp_targets=strategy.tp_targets,  # 使用 strategy 配置的 tp_targets
                    )
                    active_orders.extend(new_orders)

                    # T4: Save TP/SL orders to database
                    if order_repository is not None and new_orders:
                        await order_repository.save_batch(new_orders)
                        logger.debug(f"已保存 {len(new_orders)} 个 TP/SL 订单到数据库")

            # Track executed orders
            for order in executed:
                all_executed_orders.append(order)

                # Calculate slippage cost (for MARKET orders)
                if order.order_type == OrderType.MARKET and order.average_exec_price:
                    # For MARKET orders, compare exec price with kline.open
                    if order.direction == Direction.LONG:
                        expected_price = kline.open * (Decimal('1') + engine.slippage_rate)
                    else:
                        expected_price = kline.open * (Decimal('1') - engine.slippage_rate)
                    slippage = abs(order.average_exec_price - expected_price)
                    total_slippage_cost += slippage * order.filled_qty

                # Track position changes
                if order.order_role == OrderRole.ENTRY:
                    # New position opened
                    position = positions_map.get(order.signal_id)
                    if position:
                        position_summaries.append(PositionSummary(
                            position_id=position.id,
                            signal_id=position.signal_id,
                            symbol=request.symbol,
                            direction=position.direction,
                            entry_price=position.entry_price,
                            entry_time=kline.timestamp,
                        ))

                elif order.order_role in [OrderRole.TP1, OrderRole.SL]:
                    # Position closed (partially or fully)
                    position = positions_map.get(order.signal_id)
                    if position and position.is_closed:
                        # Update position summary
                        for summary in position_summaries:
                            if summary.position_id == position.id:
                                summary.exit_price = order.average_exec_price
                                summary.exit_time = kline.timestamp
                                summary.realized_pnl = position.realized_pnl
                                summary.exit_reason = order.exit_reason or order.order_role.value
                                break

                        # Update statistics
                        total_trades += 1
                        if position.realized_pnl > 0:
                            winning_trades += 1
                        else:
                            losing_trades += 1
                        total_pnl += position.realized_pnl
                        total_fees_paid += position.total_fees_paid

            # 【新增】Step 8: 风控状态机评估与状态突变
            # 在撮合引擎撮合订单后，对每个活跃仓位执行风控状态评估
            # T+1 时序声明：TP1 引发的 SL 修改在下一根 K 线生效
            dynamic_risk_manager = DynamicRiskManager(
                config=RiskManagerConfig(
                    trailing_percent=Decimal('0.02'),      # 默认 2%
                    step_threshold=Decimal('0.005'),       # 默认 0.5%
                ),
            )
            for position in positions_map.values():
                if not position.is_closed and position.current_qty > 0:
                    dynamic_risk_manager.evaluate_and_mutate(kline, position, active_orders)

            # Remove executed/cancelled orders from active list
            active_orders = [o for o in active_orders if o.status == OrderStatus.OPEN]

        # Step 9: Build PMSBacktestReport
        final_balance = account.total_balance
        total_return = ((final_balance - initial_balance) / initial_balance)
        win_rate = (Decimal(winning_trades) / Decimal(total_trades)) if total_trades > 0 else Decimal('0')

        # Calculate max drawdown (simplified)
        max_drawdown = Decimal('0')
        peak = initial_balance
        for summary in position_summaries:
            if summary.exit_price:
                current_balance = initial_balance + summary.realized_pnl
                if current_balance > peak:
                    peak = current_balance
                drawdown = (peak - current_balance) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        report = PMSBacktestReport(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            backtest_start=klines[0].timestamp,
            backtest_end=klines[-1].timestamp,
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_fees_paid=total_fees_paid,
            total_slippage_cost=total_slippage_cost,
            max_drawdown=max_drawdown,
            sharpe_ratio=None,
            positions=position_summaries,
        )

        # Step 10: Save report to database (if backtest_repository is provided)
        if backtest_repository is not None:
            try:
                # Serialize strategy snapshot
                strategy_snapshot = await self._serialize_strategy_snapshot_for_report(
                    request, strategy_id, strategy_name
                )
                await backtest_repository.save_report(
                    report,
                    strategy_snapshot,
                    request.symbol,
                    request.timeframe
                )
                logger.info(f"Saved backtest report to database: {report.strategy_id}")
            except Exception as e:
                logger.warning(f"Failed to save backtest report: {e}")

        logger.info(
            f"v3 PMS backtest completed: {request.symbol} {request.timeframe}, "
            f"{total_trades} trades, win_rate={win_rate:.2f}%, pnl={total_pnl:.2f} USDT"
        )

        return report


# ============================================================
# Convenience function
# ============================================================
async def run_backtest(
    gateway: ExchangeGateway,
    request: BacktestRequest,
    account_snapshot: Optional[AccountSnapshot] = None,
    repository = None,  # Optional SignalRepository for saving signals
    backtest_repository = None,  # Optional BacktestReportRepository for saving reports
) -> BacktestReport:
    """
    Run a backtest with isolated sandbox.

    Backtest signals are automatically saved to database if repository is provided.
    Backtest report is automatically saved if backtest_repository is provided.

    Args:
        gateway: Exchange gateway for fetching data
        request: Backtest request parameters
        account_snapshot: Optional account snapshot
        repository: Optional SignalRepository for saving signals
        backtest_repository: Optional BacktestReportRepository for saving reports

    Returns:
        BacktestReport with detailed statistics
    """
    backtester = Backtester(gateway)
    return await backtester.run_backtest(
        request,
        account_snapshot,
        repository=repository,
        backtest_repository=backtest_repository
    )
