"""
Signal Pipeline - Core orchestration logic.
Receives K-line data, runs strategy engine, calculates risk, and sends notifications.

Supports:
- Hot-reload observer pattern for dynamic strategy updates
- Async lock protection for concurrency safety during config reload
- Async queue worker for non-blocking SQLite persistence
"""
import asyncio
import time
import json
from typing import Optional, Dict, List, Any
from decimal import Decimal

from src.domain.models import (
    KlineData, SignalResult, AccountSnapshot, Direction, TrendDirection,
    StrategyDefinition, SignalAttempt, SignalStatus,
)
from src.domain.strategy_engine import create_dynamic_runner
from src.domain.risk_calculator import RiskCalculator, RiskConfig
from src.domain.indicators import EMACalculator
from src.domain.timeframe_utils import (
    get_higher_timeframe,
    get_last_closed_kline_index,
)
from src.infrastructure.notifier import NotificationService, get_notification_service
from src.infrastructure.logger import logger
from src.infrastructure.signal_repository import SignalRepository
from src.application.config_manager import ConfigManager
from src.application.signal_tracker import SignalStatusTracker


class SignalPipeline:
    """
    Signal processing pipeline:
    K-line -> Strategy Engine -> Risk Calculator -> Notification -> Persistence

    Features:
    - Hot-reload observer for dynamic strategy updates
    - Async lock for concurrency safety
    - Async queue worker for batch SQLite persistence
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        risk_config: RiskConfig,
        notification_service: Optional[NotificationService] = None,
        signal_repository: Optional[SignalRepository] = None,
        cooldown_seconds: int = 14400,  # Signal deduplication cooldown in seconds (default 4 hours)
    ):
        """
        Initialize Signal Pipeline.

        Args:
            config_manager: ConfigManager instance (for hot-reload observer)
            risk_config: Risk configuration
            notification_service: Notification service instance
            signal_repository: Optional signal repository for persistence
            cooldown_seconds: Signal deduplication cooldown period in seconds
        """
        self._config_manager = config_manager
        self._risk_config = risk_config
        self._notification_service = notification_service or get_notification_service()
        self._repository = signal_repository
        self._cooldown_seconds = cooldown_seconds
        self._status_tracker = SignalStatusTracker(signal_repository)

        # Queue configuration from core.yaml (S4-2)
        self._queue_batch_size = config_manager.core_config.signal_pipeline.queue.batch_size
        self._queue_flush_interval = config_manager.core_config.signal_pipeline.queue.flush_interval
        self._queue_max_size = config_manager.core_config.signal_pipeline.queue.max_queue_size

        # Store K-line history per symbol/timeframe (for warmup on reload)
        self._kline_history: Dict[str, List[KlineData]] = {}

        # Concurrency primitives - lazily initialized when event loop is available
        self._runner_lock: Optional[asyncio.Lock] = None
        self._attempts_queue: Optional[asyncio.Queue] = None
        self._flush_task: Optional[asyncio.Task] = None

        # Store latest account snapshot
        self._account_snapshot: Optional[AccountSnapshot] = None

        # Signal deduplication cache: key = "symbol:timeframe:direction:strategy", value = last fired timestamp
        self._signal_cooldown_cache: Dict[str, float] = {}

        # S3-1: MTF EMA indicators (one per symbol:timeframe combination)
        self._mtf_ema_indicators: Dict[str, EMACalculator] = {}
        self._mtf_ema_period = config_manager.user_config.mtf_ema_period or 60

        # Build dynamic strategy runner from config (uses _kline_history for warmup)
        self._runner = self._build_and_warmup_runner()

        # Register observer for hot-reload
        self._config_manager.add_observer(self.on_config_updated)

    def _ensure_async_primitives(self) -> None:
        """
        Lazily initialize async primitives (Lock, Queue) when event loop is available.
        This prevents RuntimeError when no event loop exists during testing.
        """
        if self._runner_lock is None:
            try:
                self._runner_lock = asyncio.Lock()
            except RuntimeError:
                # No running event loop
                pass

        if self._attempts_queue is None:
            try:
                self._attempts_queue = asyncio.Queue()
            except RuntimeError:
                # No running event loop
                pass

    def _ensure_flush_worker(self) -> None:
        """Ensure flush worker is running (lazy initialization)."""
        self._ensure_async_primitives()
        # Only start flush worker if async primitives are available
        if self._attempts_queue is None or self._runner_lock is None:
            return  # No event loop available (e.g., during testing)
        if self._flush_task is None or self._flush_task.done():
            self._start_flush_worker()

    def _start_flush_worker(self) -> None:
        """Start background task for batch flushing attempts to SQLite with recovery."""
        try:
            self._flush_task = asyncio.create_task(
                self._flush_attempts_worker(
                    batch_size=self._queue_batch_size,
                    flush_interval=self._queue_flush_interval,
                )
            )
            logger.info(
                f"Attempt flush worker started (batch_size={self._queue_batch_size}, "
                f"flush_interval={self._queue_flush_interval}s, max_size={self._queue_max_size})"
            )
            # Schedule recovery check
            asyncio.create_task(self._monitor_flush_worker())
        except RuntimeError:
            # No running event loop (e.g., during testing)
            # Worker will start on first process_kline call
            logger.debug("Flush worker deferred - no running event loop")

    async def _monitor_flush_worker(self) -> None:
        """
        Monitor flush worker health and restart on failure (S4-2).

        Implements exponential backoff with max restart limit.
        """
        restart_count = 0
        max_restarts = 5
        restart_delay = 1.0

        while restart_count < max_restarts:
            try:
                # Wait for worker to complete (should not happen unless error)
                if self._flush_task and not self._flush_task.done():
                    await self._flush_task

                # If we reach here, worker completed without error (unexpected)
                logger.info("Flush worker completed normally")
                return

            except Exception as e:
                restart_count += 1
                logger.error(
                    f"Flush worker crashed (restart {restart_count}/{max_restarts}): {e}"
                )

                if restart_count >= max_restarts:
                    logger.error(
                        "CRITICAL: Flush worker exceeded max restarts, "
                        "data persistence may be compromised"
                    )
                    return

                # Exponential backoff before restart
                delay = restart_delay * (2 ** (restart_count - 1))
                logger.info(f"Waiting {delay}s before restart...")
                await asyncio.sleep(delay)

                # Attempt restart
                try:
                    self._ensure_async_primitives()
                    if self._attempts_queue is None or self._runner_lock is None:
                        logger.debug("Cannot restart flush worker: no event loop")
                        return

                    self._flush_task = asyncio.create_task(
                        self._flush_attempts_worker(
                            batch_size=self._queue_batch_size,
                            flush_interval=self._queue_flush_interval,
                        )
                    )
                    logger.info(f"Flush worker restarted (attempt #{restart_count})")

                except Exception as restart_e:
                    logger.error(f"Failed to restart flush worker: {restart_e}")

    async def _flush_attempts_worker(self, batch_size: int = 10, flush_interval: float = 5.0) -> None:
        """
        Background worker that batches and flushes signal attempts to SQLite.

        Features (S4-2):
        - Backpressure monitoring: alerts when queue approaches max capacity
        - Consecutive error tracking: alerts on repeated failures

        Args:
            batch_size: Number of attempts to batch before flushing
            flush_interval: Maximum time to wait before flushing (seconds)
        """
        buffer: List[tuple] = []
        last_flush = time.time()
        consecutive_drops = 0  # Track consecutive drop events

        while True:
            try:
                # Check queue size for backpressure monitoring
                queue_size = self._attempts_queue.qsize()

                # Alert if queue is approaching max capacity (80% threshold)
                if queue_size > int(self._queue_max_size * 0.8):
                    logger.warning(
                        f"BACKPRESSURE ALERT: Queue size ({queue_size}) approaching "
                        f"max capacity ({self._queue_max_size})"
                    )

                # Wait for item or timeout
                try:
                    item = await asyncio.wait_for(self._attempts_queue.get(), timeout=1.0)
                    buffer.append(item)
                except asyncio.TimeoutError:
                    pass

                # Flush if batch is full or interval exceeded
                now = time.time()
                if len(buffer) >= batch_size or (buffer and now - last_flush >= flush_interval):
                    await self._flush_buffer(buffer)
                    buffer = []
                    last_flush = now
                    consecutive_drops = 0  # Reset on successful flush

            except asyncio.CancelledError:
                # Flush remaining on cancel
                if buffer:
                    await self._flush_buffer(buffer)
                raise
            except Exception as e:
                logger.error(f"Flush worker error: {e}")
                consecutive_drops += 1

                # Alert on consecutive errors
                if consecutive_drops >= 3:
                    logger.error(
                        f"CRITICAL: {consecutive_drops} consecutive flush worker errors, "
                        f"potential database connectivity issue"
                    )
                buffer = []

    async def _flush_buffer(self, buffer: List[tuple]) -> None:
        """Flush a batch of attempts to database."""
        if not buffer or not self._repository:
            return

        try:
            for attempt, symbol, timeframe in buffer:
                await self._repository.save_attempt(attempt, symbol, timeframe)
            logger.debug(f"Flushed {len(buffer)} attempts to database")
        except Exception as e:
            logger.error(f"Failed to flush attempts batch: {e}")

    async def on_config_updated(self) -> None:
        """
        Observer callback for configuration hot-reload.

        Called by ConfigManager when user.yaml is updated.
        Rebuilds the strategy runner and warms up with cached K-line history.
        """
        logger.info("Configuration hot-reload triggered, rebuilding strategy runner...")

        async with self._get_runner_lock():
            # Step 1: Build new runner from updated config
            self._runner = self._build_and_warmup_runner()

            # Step 2: Clear stale cooldown cache (config params may have changed)
            self._signal_cooldown_cache.clear()
            logger.info("Signal cooldown cache cleared (stale cache prevention)")

            logger.info("Strategy runner rebuilt and warmup complete")

    def _get_runner_lock(self) -> asyncio.Lock:
        """Get or create the runner lock."""
        self._ensure_async_primitives()
        if self._runner_lock is None:
            self._runner_lock = asyncio.Lock()
        return self._runner_lock

    def _get_attempts_queue(self) -> asyncio.Queue:
        """Get or create the attempts queue."""
        self._ensure_async_primitives()
        if self._attempts_queue is None:
            self._attempts_queue = asyncio.Queue()
        return self._attempts_queue

    def _build_and_warmup_runner(self) -> Any:
        """
        Build dynamic strategy runner from current config and warmup with K-line history.

        Returns:
            DynamicStrategyRunner instance
        """
        # Get active strategies from config
        active_strategies = self._config_manager.user_config.active_strategies
        core_config = self._config_manager.core_config

        # Build runner using factory function
        runner = create_dynamic_runner(active_strategies, core_config)

        # Warmup: replay cached K-lines to restore EMA and other stateful indicators
        if self._kline_history:
            warmup_count = 0
            warmup_details = []
            for key, history in self._kline_history.items():
                parts = key.split(":")
                symbol = parts[0]
                timeframe = parts[1]
                count = len(history)
                warmup_details.append(f"{symbol}:{timeframe}({count} bars)")
                for kline in history:
                    # The runner's update_state takes only kline, symbol/timeframe are extracted internally
                    runner.update_state(kline)
                    warmup_count += 1

            logger.info(f"Runner warmup complete: {warmup_count} K-lines replayed from {len(warmup_details)} streams")
            logger.debug(f"Warmup details: {', '.join(warmup_details)}")

        return runner

    def update_account_snapshot(self, snapshot: AccountSnapshot) -> None:
        """
        Update the latest account snapshot for risk calculations.

        Args:
            snapshot: Latest account snapshot
        """
        self._account_snapshot = snapshot
        logger.debug(f"Account snapshot updated: balance={snapshot.total_balance}")

    async def process_kline(self, kline: KlineData) -> None:
        """
        Process a single closed K-line.

        Args:
            kline: Closed K-line data
        """
        try:
            # Ensure async primitives and flush worker are running (lazy init)
            self._ensure_flush_worker()

            # Ensure lock is available for this call
            lock = self._get_runner_lock()

            # Check pending signals for performance tracking (before processing new signal)
            if self._repository is not None:
                from src.application.performance_tracker import PerformanceTracker
                tracker = PerformanceTracker()
                await tracker.check_pending_signals(kline, self._repository)

            # Store in history
            self._store_kline(kline)

            # Run strategy engine with lock protection (prevents race condition during hot-reload)
            async with lock:
                attempts = self._run_strategy(kline)

            # Log filter rejection details for analysis
            for attempt in attempts:
                if attempt.pattern is None:
                    continue  # No pattern detected, skip filter logging

                symbol = kline.symbol
                timeframe = kline.timeframe
                pattern_type = attempt.strategy_name
                direction = attempt.pattern.direction.value

                for filter_name, filter_result in attempt.filter_results:
                    if not filter_result.passed:
                        metadata_json = json.dumps(filter_result.metadata) if filter_result.metadata else "{}"
                        logger.warning(
                            f"[FILTER_REJECTED] symbol={symbol} timeframe={timeframe} "
                            f"pattern={pattern_type} direction={direction} "
                            f"filter={filter_name} reason={filter_result.reason} "
                            f"metadata={metadata_json}"
                        )

            # Persist all attempt records via async queue (fire-and-forget, backpressure relief)
            if self._repository is not None:
                queue = self._get_attempts_queue()
                try:
                    for attempt in attempts:
                        queue.put_nowait((attempt, kline.symbol, kline.timeframe))
                except asyncio.QueueFull:
                    logger.warning("Attempt queue full, dropping oldest entries")

            # Process all SIGNAL_FIRED attempts
            for attempt in attempts:
                if attempt.final_result == "SIGNAL_FIRED" and attempt.pattern:
                    # Signal deduplication: check cooldown period
                    # Key includes strategy_name to allow concurrent strategies to fire independently
                    dedup_key = f"{kline.symbol}:{kline.timeframe}:{attempt.pattern.direction.value}:{attempt.strategy_name}"
                    now = time.time()
                    last_fired = self._signal_cooldown_cache.get(dedup_key, 0)

                    if now - last_fired < self._cooldown_seconds:
                        remaining = int(self._cooldown_seconds - (now - last_fired)) // 60
                        logger.debug(
                            f"Signal deduplicated: {kline.symbol} {kline.timeframe} "
                            f"{attempt.pattern.direction.value} [{attempt.strategy_name}] "
                            f"(cooldown: {remaining}min remaining)"
                        )
                        # Skip notification and persistence, but attempt already recorded
                        continue

                    # Calculate complete signal result with risk
                    signal = self._calculate_risk(kline, attempt.pattern.direction, attempt, attempt.strategy_name, attempt.pattern.score)

                    # Start tracking signal status
                    signal_id = await self._status_tracker.track_signal(signal)
                    await self._status_tracker.update_status(signal_id, SignalStatus.PENDING)

                    # Send notification
                    await self._notification_service.send_signal(signal)
                    logger.info(f"Signal sent: {kline.symbol} {kline.timeframe} {attempt.pattern.direction.value} [{attempt.strategy_name}]")

                    # Update cooldown cache after successful send
                    self._signal_cooldown_cache[dedup_key] = now

                    # Persist signal to database if repository is available
                    if self._repository is not None:
                        try:
                            await self._repository.save_signal(signal, signal_id, "PENDING")
                            logger.info(f"Signal persisted: {kline.symbol} {kline.timeframe} [{attempt.strategy_name}]")
                        except Exception as e:
                            logger.error(f"Failed to persist signal: {e}")

        except Exception as e:
            logger.error(f"Error processing K-line: {e}")

    def _store_kline(self, kline: KlineData) -> None:
        """Store K-line in history for MTF analysis"""
        key = f"{kline.symbol}:{kline.timeframe}"
        if key not in self._kline_history:
            self._kline_history[key] = []

        # Keep last 200 bars
        self._kline_history[key].append(kline)
        if len(self._kline_history[key]) > 200:
            self._kline_history[key] = self._kline_history[key][-200:]

    def _run_strategy(self, kline: KlineData) -> List[SignalAttempt]:
        """
        Run strategy engine on K-line.

        Args:
            kline: K-line data

        Returns:
            List[SignalAttempt] with full filtering chain results for all strategies
        """
        # Get K-line history for strategies that need it (like Engulfing)
        key = f"{kline.symbol}:{kline.timeframe}"
        kline_history = self._kline_history.get(key, [])[:-1]  # Exclude current kline

        # Update runner state
        self._runner.update_state(kline)

        # S3-1: Calculate higher timeframe trends for MTF filtering
        higher_tf_trends = self._get_closest_higher_tf_trends(kline)

        # Log MTF status for debugging
        if higher_tf_trends:
            logger.debug(
                f"MTF trends for {kline.symbol}:{kline.timeframe}: "
                f"{higher_tf_trends}"
            )

        # Run all strategies with MTF trends
        return self._runner.run_all(
            kline=kline,
            higher_tf_trends=higher_tf_trends,  # Changed from {} to calculated trends
            kline_history=kline_history,
        )

    def _get_closest_higher_tf_trends(self, kline: KlineData) -> Dict[str, TrendDirection]:
        """
        Calculate higher timeframe trends for MTF filtering.

        Uses the last CLOSED kline of each higher timeframe to ensure
        data consistency and avoid using incomplete running klines.

        Args:
            kline: Current kline that triggered a signal

        Returns:
            Dict mapping timeframe to TrendDirection
            e.g., {"1h": TrendDirection.BULLISH, "4h": TrendDirection.BEARISH}
        """
        result: Dict[str, TrendDirection] = {}
        current_tf = kline.timeframe

        # Get higher timeframe from config
        higher_tf = get_higher_timeframe(
            current_tf,
            self._config_manager.user_config.mtf_mapping
        )

        if higher_tf is None:
            return result  # No higher timeframe (e.g., 1w)

        # Fetch higher timeframe klines from history
        key = f"{kline.symbol}:{higher_tf}"
        higher_tf_klines = self._kline_history.get(key, [])

        if len(higher_tf_klines) == 0:
            return result  # No data available

        # Find last closed kline index
        last_closed_idx = get_last_closed_kline_index(
            higher_tf_klines,
            kline.timestamp,
            higher_tf
        )

        if last_closed_idx < 0:
            return result  # No closed kline found

        last_closed_kline = higher_tf_klines[last_closed_idx]

        # Get or create EMA indicator for this symbol:timeframe
        ema_key = f"{kline.symbol}:{higher_tf}"
        if ema_key not in self._mtf_ema_indicators:
            self._mtf_ema_indicators[ema_key] = EMACalculator(period=self._mtf_ema_period)

        ema = self._mtf_ema_indicators[ema_key]

        # Update EMA with last closed kline's close price
        ema.update(last_closed_kline.close)

        if not ema.is_ready:
            return result  # EMA needs more data

        # Determine trend direction from EMA
        # Use price vs EMA to determine trend
        ema_value = ema.value
        if ema_value is None:
            return result

        if last_closed_kline.close > ema_value:
            result[higher_tf] = TrendDirection.BULLISH
        else:
            result[higher_tf] = TrendDirection.BEARISH

        return result

    def _calculate_risk(self, kline: KlineData, direction: Direction, attempt: SignalAttempt, strategy_name: str = "unknown", score: float = 0.0) -> SignalResult:
        """
        Calculate complete signal result with risk parameters.

        Args:
            kline: K-line data where signal was detected
            direction: Signal direction
            attempt: SignalAttempt that fired (contains filter_results for tag generation)
            strategy_name: Strategy name that generated this signal
            score: Pattern quality score (0.0 ~ 1.0)

        Returns:
            Complete SignalResult with all fields populated
        """
        # Create dummy account snapshot if not available
        if not self._account_snapshot:
            logger.warning("No account snapshot available, using dummy for risk calc")
            self._account_snapshot = AccountSnapshot(
                total_balance=Decimal("10000"),
                available_balance=Decimal("10000"),
                unrealized_pnl=Decimal("0"),
                positions=[],
                timestamp=0,
            )

        # Generate dynamic tags from filter_results
        tags = self._generate_tags_from_filters(attempt.filter_results)

        # Use risk_calculator's calculate_signal_result with tags
        return self._risk_calculator.calculate_signal_result(
            kline=kline,
            account=self._account_snapshot,
            direction=direction,
            tags=tags,
            kline_timestamp=kline.timestamp,
            strategy_name=strategy_name,
            score=score,
        )

    def _generate_tags_from_filters(self, filter_results: list) -> List[Dict[str, str]]:
        """
        Generate dynamic tags from filter results.

        Args:
            filter_results: List of (filter_name, FilterResult) tuples from attempt

        Returns:
            List of tag dicts e.g., [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
        """
        tags = []
        for filter_name, filter_result in filter_results:
            if filter_result.passed:
                # Generate tag based on filter type
                if filter_name == "ema" or filter_name == "ema_trend":
                    # Extract trend direction from reason or params
                    trend_value = self._extract_trend_from_reason(filter_result.reason)
                    tags.append({"name": "EMA", "value": trend_value})
                elif filter_name == "mtf":
                    mtf_value = "Confirmed" if "confirm" in filter_result.reason.lower() else "Passed"
                    tags.append({"name": "MTF", "value": mtf_value})
                elif filter_name == "volume_surge":
                    tags.append({"name": "Volume", "value": "Surge"})
                elif filter_name == "volatility_filter":
                    tags.append({"name": "Volatility", "value": "Normal"})
                elif filter_name == "time_filter":
                    tags.append({"name": "Time", "value": "Valid"})
                elif filter_name == "price_action":
                    tags.append({"name": "Price Action", "value": "Valid"})
                else:
                    # Generic tag for unknown filters
                    tag_name = filter_name.replace("_", " ").title()
                    tags.append({"name": tag_name, "value": "Passed"})
        return tags

    def _extract_trend_from_reason(self, reason: str) -> str:
        """Extract trend direction from filter reason string."""
        reason_lower = reason.lower()
        if "bull" in reason_lower:
            return "Bullish"
        elif "bear" in reason_lower:
            return "Bearish"
        else:
            return "Neutral"

    def get_queue_size(self) -> int:
        """
        Get current queue size.

        Returns:
            Number of items currently in the attempt queue
        """
        self._ensure_async_primitives()
        if self._attempts_queue is None:
            return 0
        return self._attempts_queue.qsize()

    async def close(self) -> None:
        """
        Close the pipeline and cleanup resources.

        Cancels the flush worker and closes the notification service.
        """
        # Cancel flush worker
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Close notification service
        if self._notification_service:
            await self._notification_service.close()

        logger.info("SignalPipeline closed")

    @property
    def _risk_calculator(self) -> RiskCalculator:
        """Get risk calculator instance."""
        return RiskCalculator(self._risk_config)
