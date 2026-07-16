"""
Exchange Gateway - All exchange communication (REST + WebSocket).
Handles historical data warmup, real-time K-line streaming, and asset polling.
"""
import asyncio
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Awaitable, Any
from decimal import Decimal

try:
    import ccxt.pro as ccxtpro
except ImportError:
    ccxtpro = None

import ccxt.async_support as ccxt_async

from pydantic import BaseModel

from src.domain.models import KlineData, AccountSnapshot, PositionInfo, OrderPlacementResult, OrderCancelResult, OrderStatus, OrderType, Order, OrderRole
from src.domain.ticket_bound_exchange_command import (
    ExchangeOrderLookupRequest,
    ExchangeOrderLookupResult,
    ExchangeOrderLookupStatus,
    ExchangeOrderLookupView,
    required_exchange_order_lookup_view,
)
from decimal import Decimal
from src.domain.exceptions import FatalStartupError, ConnectionLostError, DataQualityWarning, InsufficientMarginError, InvalidOrderError, OrderNotFoundError, OrderAlreadyFilledError, RateLimitError
from src.infrastructure.logger import logger


# ============================================================
# Order Local State Model (P0 修复：替换 Dict[str, Any])
# ============================================================
class OrderLocalState(BaseModel):
    """Order local state tracking for dedup and status"""
    filled_qty: Decimal
    status: str
    updated_at: int  # 毫秒时间戳


@dataclass(frozen=True)
class CcxtOrderParamsBuildResult:
    """Normalized exchange-specific order params passed to ccxt."""

    params: Dict[str, Any]
    exchange_reduce_only_param_sent: bool = False
    exchange_reduce_only_omit_reason: Optional[str] = None


# ============================================================
# Exchange Gateway
# ============================================================
class ExchangeGateway:
    """
    Handles all exchange communication:
    - REST API for historical data warmup and asset queries
    - WebSocket for real-time K-line streaming
    """

    # Timeframe mapping from user-friendly to ccxt format
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "12h": "12h",
        "1d": "1d",
        "1w": "1w",
    }

    def __init__(
        self,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Exchange Gateway.

        Args:
            exchange_name: Exchange name (ccxt id, e.g., 'binance')
            api_key: API key (read-only permission required)
            api_secret: API secret
            testnet: Use testnet endpoint
            options: Additional exchange options
        """
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # Build exchange options
        exchange_options = {
            'defaultType': 'swap',  # Default to futures/swap
            'adjustForTimezone': True,
            'recvWindow': 30000,
            'timeout': 30000,
        }
        if options:
            exchange_options.update(options)

        # Create both REST and WebSocket exchange instances
        self.rest_exchange = self._create_rest_exchange(exchange_options)
        self.ws_exchange = None  # Created on demand

        # Reconnection settings
        self._max_reconnect_attempts = 10
        self._initial_reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

        # WebSocket state
        self._ws_running = False
        self._order_ws_running = False
        self._order_ws_running_symbols: Dict[str, bool] = {}
        self._order_watch_exchanges: List[Any] = []

        # Asset snapshot cache
        self._account_snapshot: Optional[AccountSnapshot] = None
        self._asset_polling_task: Optional[asyncio.Task] = None
        self._polling_failures = 0
        self._max_polling_failures = 5

        # Candle closure tracking (instance variable, not class variable)
        self._candle_timestamps: Dict[str, int] = {}

        # Order state tracking (G-002: dedup based on filled_qty)
        # P0 修复：使用 OrderLocalState 替换 Dict[str, Any]
        self._order_local_state: Dict[str, OrderLocalState] = {}
        self._recent_order_updates: Dict[str, Dict[str, Any]] = {}
        self._recent_order_updates_by_symbol: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._order_confirmation_retry_delays = (0.25, 0.75)

        # P5-011: Global order update callback (for order persistence)
        self._global_order_callback: Optional[Callable[[Order], Awaitable[None]]] = None

        # Permission-check audit state
        self._permissions_verified = False
        self._permissions_check_status = "not_checked"
        self._permissions_check_reason: Optional[str] = None

        # P0-WS-Exception-Protection: 待恢复订单集合（WS 回调失败时标记）
        self._pending_recovery_orders: Dict[str, Dict[str, Any]] = {}

    def _build_exchange_config(self, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        构建通用交易所配置

        P2-3: 重复代码重构 - 提取 _create_rest_exchange 和 _create_ws_exchange 的公共配置逻辑

        Returns:
            Dict[str, Any]: CCXT 交易所配置字典
        """
        config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # USDT-M Futures
                'warnOnFetchOpenOrdersWithoutSymbol': False,
                # R8: Binance Futures WS sends PING but never PONGs, so ccxt.pro's
                # keepalive mechanism (which only updates lastPong on PONG frames)
                # will always timeout. Setting keepAlive=0 disables this check.
                # Connection health is instead monitored by continuous kline data flow.
                'ws': {'keepAlive': 0},
            }
        }
        # Merge user-provided options
        if options:
            config['options'].update(options)
        return config

    def _create_rest_exchange(self, options: Dict[str, Any]):
        """Create REST exchange instance

        CCXT 币安合约测试网连接指南:
        - 旧方法 (已废弃): set_sandbox_mode(True) - 可能导致 Endpoint 路由错误
        - 新方法 (CCXT v4.5.6+): enable_demo_trading(True) - 自动切换到 demo-fapi.binance.com
        """
        config = self._build_exchange_config(options)

        # Create exchange by name
        exchange_class = getattr(ccxt_async, self.exchange_name)
        exchange = exchange_class(config)

        # 币安测试网：使用新的 enable_demo_trading 方法
        if self.testnet and self.exchange_name.lower() == 'binance':
            exchange.enable_demo_trading(True)

        return exchange

    def _create_ws_exchange(self, options: Dict[str, Any]):
        """Create WebSocket exchange instance

        CCXT Pro 币安合约测试网 WebSocket:
        - 自动路由到 wss://demo-stream.binancefuture.com
        """
        config = self._build_exchange_config(options)

        # Create exchange by name
        exchange_class = getattr(ccxtpro, self.exchange_name)
        exchange = exchange_class(config)

        # 币安测试网：使用新的 enable_demo_trading 方法
        if self.testnet and self.exchange_name.lower() == 'binance':
            exchange.enable_demo_trading(True)

        return exchange

    # ============================================================
    # Lifecycle Management
    # ============================================================
    async def initialize(self) -> None:
        """
        Initialize exchange connections.
        Verifies connectivity and sets up contracts mode.

        Raises:
            FatalStartupError: If exchange initialization fails
        """
        try:
            # Load markets to verify connection
            # defaultType is already set to 'swap' in _create_rest_exchange,
            # so CCXT will only fetch futures market data
            await self.rest_exchange.load_markets()
            logger.info(f"Exchange {self.exchange_name} initialized successfully")
            logger.info(f"Available symbols: {len(self.rest_exchange.symbols)}")

        except Exception as e:
            raise FatalStartupError(
                f"Failed to initialize exchange: {e}",
                "F-004"
            )

    async def initialize_lifecycle_readonly(self) -> None:
        """Verify the lifecycle read path without loading the market catalog.

        The ticket lifecycle worker already receives an immutable PG-bound
        Binance market id. Loading every CCXT market on each short-lived
        maintenance invocation adds no reconciliation truth and materially
        increases latency and memory. This initializer performs one public,
        read-only venue-time request and leaves market loading disabled.
        """

        if self.exchange_name.lower() != "binance":
            raise FatalStartupError(
                "Lifecycle read-only initialization is only certified for Binance",
                "F-004",
            )
        server_time_fetch = getattr(self.rest_exchange, "fapiPublicGetTime", None)
        if not callable(server_time_fetch):
            raise FatalStartupError(
                "Binance lifecycle server-time endpoint is unavailable",
                "F-004",
            )
        try:
            payload = await server_time_fetch()
            if not isinstance(payload, dict) or not payload.get("serverTime"):
                raise RuntimeError("binance_server_time_response_invalid")
            logger.info(
                "Exchange %s lifecycle read path initialized without market load",
                self.exchange_name,
            )
        except Exception as e:
            raise FatalStartupError(
                f"Failed to initialize lifecycle exchange read path: {e}",
                "F-004",
            )

    async def check_api_key_permissions(self) -> None:
        """Check API key permission policy.

        Sim/Live requires:
        - Withdraw permission must be disabled (F-002).
        - Trade permission may be enabled (Phase 5+), so we do not block on it here.
        """
        exchange = self.exchange_name.lower()
        if exchange != "binance":
            self._permissions_verified = False
            self._permissions_check_status = "skipped_unsupported_exchange"
            self._permissions_check_reason = f"unsupported_exchange:{exchange}"
            logger.warning(
                "API key permission check not implemented for exchange=%s; "
                "skipping permission enforcement",
                self.exchange_name,
            )
            return

        try:
            restrictions = await self.rest_exchange.sapi_get_account_apirestrictions()
        except Exception as e:
            if self.testnet:
                self._permissions_verified = False
                self._permissions_check_status = "skipped_testnet"
                self._permissions_check_reason = str(e)
                logger.warning(
                    "Failed to check Binance API key restrictions on testnet; "
                    "skipping withdraw-permission enforcement. error=%s",
                    e,
                )
                return
            raise FatalStartupError(
                f"Failed to check Binance API key restrictions: {e}",
                "F-004",
            )

        withdraw_enabled = bool(
            restrictions.get("enableWithdrawals")
            or restrictions.get("enable_withdrawals")
            or restrictions.get("enableWithdrawalsSwitch")
        )
        if withdraw_enabled:
            raise FatalStartupError(
                "API key has withdraw permission enabled; aborting startup",
                "F-002",
            )

        self._permissions_verified = True
        self._permissions_check_status = "verified"
        self._permissions_check_reason = None
        logger.info(
            "API key restrictions checked: exchange=%s, withdraw_enabled=%s, details=%s",
            self.exchange_name,
            withdraw_enabled,
            {k: restrictions.get(k) for k in ("enableReading", "enableFutures", "enableSpotAndMarginTrading", "ipRestrict")},
        )

    def get_permission_check_summary(self) -> dict[str, Any]:
        """Return a sanitized summary for startup logging and audit trails."""
        return {
            "verified": self._permissions_verified,
            "status": self._permissions_check_status,
            "reason": self._permissions_check_reason,
            "exchange": self.exchange_name,
            "testnet": self.testnet,
        }

    async def close(self) -> None:
        """Close all exchange connections"""
        # Stop asset polling
        if self._asset_polling_task:
            self._asset_polling_task.cancel()
            try:
                await self._asset_polling_task
            except asyncio.CancelledError:
                pass

        # Stop WebSocket
        self._ws_running = False
        self._order_ws_running = False
        self._order_ws_running_symbols.clear()
        if self.ws_exchange:
            try:
                await self.ws_exchange.close()
            except Exception:
                pass

        for order_ws_exchange in list(self._order_watch_exchanges):
            try:
                await order_ws_exchange.close()
            except Exception:
                pass
        self._order_watch_exchanges.clear()

        # Close REST
        try:
            await self.rest_exchange.close()
        except Exception:
            pass

        logger.info("Exchange connections closed")

    # ============================================================
    # REST API - Historical Data Warmup
    # ============================================================

    # Timeframe to minutes mapping for pagination cursor advancement
    TIMEFRAME_MAP: Dict[str, int] = {
        "1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080
    }

    async def fetch_historical_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        since: Optional[int] = None,
    ) -> List[KlineData]:
        """
        Fetch historical K-line data via REST API.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT:USDT")
            timeframe: Timeframe (e.g., "1h", "4h")
            limit: Number of candles to fetch (default: 100)
            since: Start timestamp in milliseconds (default: None, fetches latest)

        Returns:
            List of KlineData objects
        """
        try:
            if limit <= 1000 and since is None:
                # Original single-call behavior (backward compatible)
                ohlcv_data = await self.rest_exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit,
                )
                result = []
                for candle in ohlcv_data:
                    kline = self._parse_ohlcv(candle, symbol, timeframe)
                    if kline:
                        result.append(kline)

                logger.debug(f"Fetched {len(result)} historical bars for {symbol} {timeframe}")
                return result

            # Pagination mode: limit > 1000 or since is specified
            batch = min(limit, 1000)
            current_since = since
            all_candles: List = []

            while True:
                ohlcv_data = await self.rest_exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=batch,
                    since=current_since,
                )

                if not ohlcv_data:
                    break

                all_candles.extend(ohlcv_data)

                if len(ohlcv_data) < batch:
                    break

                if len(all_candles) >= limit:
                    break

                last_ts = ohlcv_data[-1][0]
                minutes = self.TIMEFRAME_MAP.get(timeframe, 60)
                current_since = last_ts + minutes * 60 * 1000

            result = []
            for candle in all_candles[:limit]:
                kline = self._parse_ohlcv(candle, symbol, timeframe)
                if kline:
                    result.append(kline)

            logger.debug(f"Fetched {len(result)} historical bars for {symbol} {timeframe}")
            return result

        except Exception as e:
            logger.error(f"Failed to fetch historical OHLCV for {symbol} {timeframe}: {e}")
            raise

    def _parse_ohlcv(
        self,
        candle: List[Any],
        symbol: str,
        timeframe: str,
        raw_info: Optional[Dict] = None
    ) -> Optional[KlineData]:
        """
        Parse OHLCV candle to KlineData model.

        Args:
            candle: [timestamp, open, high, low, close, volume]
            symbol: Trading symbol
            timeframe: Timeframe
            raw_info: Optional exchange raw data (e.g., {"x": True} for closed candle)

        Returns:
            KlineData object or None if invalid
        """
        try:
            timestamp = int(candle[0])
            open_price = Decimal(str(candle[1]))
            high_price = Decimal(str(candle[2]))
            low_price = Decimal(str(candle[3]))
            close_price = Decimal(str(candle[4]))
            volume = Decimal(str(candle[5]))

            # Validate OHLCV data quality
            if high_price < low_price:
                raise DataQualityWarning(
                    f"Invalid K-line: high ({high_price}) < low ({low_price})",
                    "W-001"
                )
            if high_price < open_price or high_price < close_price:
                raise DataQualityWarning(
                    f"Invalid K-line: high ({high_price}) below open/close",
                    "W-001"
                )
            if low_price > open_price or low_price > close_price:
                raise DataQualityWarning(
                    f"Invalid K-line: low ({low_price}) above open/close",
                    "W-001"
                )

            # P0-1: 优先使用交易所 x 字段判断收盘状态
            is_closed = True  # 默认假设已收盘
            if raw_info and 'x' in raw_info:
                is_closed = bool(raw_info['x'])
                logger.debug(
                    f"[K 线解析] {symbol} {timeframe} x={is_closed} "
                    f"ts={timestamp} close={close_price}"
                )

            return KlineData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                is_closed=is_closed,
                info=raw_info,  # 保留原始数据（可选）
            )

        except DataQualityWarning:
            raise
        except Exception as e:
            logger.warning(f"Failed to parse OHLCV candle: {e}")
            return None

    # ============================================================
    # WebSocket - Real-time K-line Streaming
    # ============================================================
    async def subscribe_ohlcv(
        self,
        symbols: List[str],
        timeframes: List[str],
        callback: Callable[[KlineData], Awaitable[None]],
        history_bars: int = 100,
    ) -> None:
        """
        Subscribe to real-time K-line updates via WebSocket.
        Only emits KlineData when candle is closed (is_closed=True).

        Args:
            symbols: List of symbols to subscribe
            timeframes: List of timeframes to subscribe
            callback: Async callback function for each closed candle
            history_bars: Number of historical bars to preload
        """
        self._ws_running = True
        self._reconnect_count = 0

        # Create WebSocket exchange
        self.ws_exchange = self._create_ws_exchange({
            'defaultType': 'swap',
        })

        # Initialize WebSocket connection
        await self.ws_exchange.load_markets()

        # Subscribe to each symbol/timeframe combination
        tasks = []
        for symbol in symbols:
            for timeframe in timeframes:
                task = asyncio.create_task(
                    self._subscribe_single_ohlcv(
                        symbol, timeframe, callback, history_bars
                    )
                )
                tasks.append(task)

        # Wait for all subscriptions
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _subscribe_single_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[KlineData], Awaitable[None]],
        history_bars: int,
    ) -> None:
        """
        Subscribe to a single symbol/timeframe with reconnection logic.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            callback: Callback for closed candles
            history_bars: Historical bars to preload
        """
        # Local reconnect counter per symbol/timeframe (not shared)
        reconnect_count = 0

        while self._ws_running:
            try:
                logger.info(f"Subscribing to {symbol} {timeframe}")

                while self._ws_running:
                    # Watch OHLCV (this is a blocking call that receives updates)
                    ohlcv = await self.ws_exchange.watch_ohlcv(symbol, timeframe)

                    # Get the latest candle
                    if not ohlcv or len(ohlcv) < 1:
                        continue

                    # ============================================================
                    # P0-1: WebSocket K 线选择逻辑修复
                    # 核心逻辑：
                    # - 当 x=true 时，ohlcv[-1] 就是刚收盘的 K 线
                    # - 当 x=false 或无 x 字段时，使用 ohlcv[-2]（前一根已收盘 K 线）
                    # ============================================================

                    latest_candle = ohlcv[-1]

                    # 方案 1: 优先使用交易所 x 字段
                    # CCXT Pro 规范：candle[6] 可能包含 info 字典，其中有 x 字段
                    if len(latest_candle) > 6 and isinstance(latest_candle[6], dict):
                        raw_info = latest_candle[6]
                        if 'x' in raw_info:
                            is_closed = bool(raw_info['x'])

                            if is_closed:
                                # 当 x=true 时，ohlcv[-1] 就是刚收盘的 K 线
                                kline = self._parse_ohlcv(latest_candle, symbol, timeframe, raw_info)
                                if kline:
                                    logger.debug(
                                        f"[WebSocket K 线] {symbol} {timeframe} "
                                        f"收盘确认 x=true ts={kline.timestamp} close={kline.close}"
                                    )
                                    await callback(kline)
                            # else: x=false，未收盘，跳过

                            continue  # 已处理，跳过后续逻辑

                    # 方案 2: 时间戳推断（后备）
                    # 适用于不支持 x 字段的交易所
                    if len(ohlcv) >= 2:
                        prev_candle = ohlcv[-2]  # 前一根已收盘 K 线
                        kline = self._parse_ohlcv(prev_candle, symbol, timeframe)
                        if kline:
                            key = f"{symbol}:{timeframe}"
                            current_ts = kline.timestamp

                            if key not in self._candle_timestamps:
                                self._candle_timestamps[key] = current_ts
                            elif current_ts != self._candle_timestamps[key]:
                                self._candle_timestamps[key] = current_ts
                                logger.debug(
                                    f"[WebSocket K 线] {symbol} {timeframe} "
                                    f"时间戳推断收盘 ts={current_ts} close={kline.close}"
                                )
                                await callback(kline)

            except asyncio.CancelledError:
                logger.info(f"WebSocket subscription cancelled for {symbol} {timeframe}")
                break

            except Exception as e:
                logger.error(f"WebSocket error for {symbol} {timeframe}: {e}")
                reconnect_count += 1

                if reconnect_count >= self._max_reconnect_attempts:
                    raise ConnectionLostError(
                        f"Max reconnection attempts exceeded for {symbol} {timeframe}",
                        "C-001"
                    )

                # Exponential backoff
                delay = min(
                    self._initial_reconnect_delay * (2 ** (reconnect_count - 1)),
                    self._max_reconnect_delay
                )
                logger.warning(f"Reconnecting in {delay:.1f}s (attempt {reconnect_count}/{self._max_reconnect_attempts})")
                await asyncio.sleep(delay)

    def _is_candle_closed(self, kline: KlineData, symbol: str, timeframe: str) -> bool:
        """
        Track if a candle has closed by detecting timestamp change.

        Args:
            kline: Current KlineData
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            True if candle is newly closed
        """
        key = f"{symbol}:{timeframe}"
        current_ts = kline.timestamp

        if key in self._candle_timestamps:
            if current_ts != self._candle_timestamps[key]:
                # Timestamp changed - previous candle is closed
                self._candle_timestamps[key] = current_ts
                return True
        else:
            self._candle_timestamps[key] = current_ts

        return False

    # ============================================================
    # Asset Polling - Account Balance & Positions
    # ============================================================

    # ============================================================
    # WebSocket Asset Push (S5-1)
    # ============================================================
    async def subscribe_account_updates(
        self,
        callback: Callable[[AccountSnapshot], Awaitable[None]],
    ) -> None:
        """
        订阅账户资产实时更新（含降级逻辑）

        Args:
            callback: 资产更新时的异步回调
        """
        if ccxtpro is None:
            logger.warning("CCXT Pro 未安装，降级到轮询模式")
            await self._poll_assets_loop_with_callback(callback)
            return

        try:
            await self._ws_subscribe_account_loop(callback)
        except Exception as e:
            logger.warning(f"WebSocket 订阅失败，降级到轮询模式：{e}")
            await self._poll_assets_loop_with_callback(callback)

    async def _ws_subscribe_account_loop(
        self,
        callback: Callable[[AccountSnapshot], Awaitable[None]],
    ) -> None:
        """
        WebSocket 订阅循环（含重连逻辑）

        Args:
            callback: 资产更新时的异步回调
        """
        self._ws_running = True
        reconnect_count = 0

        # 创建 WebSocket 交换实例
        self.ws_exchange = self._create_ws_exchange({
            'defaultType': 'swap',
        })

        # 加载市场数据
        await self.ws_exchange.load_markets()
        logger.info("WebSocket 账户订阅已启动")

        try:
            while self._ws_running:
                try:
                    # 使用 CCXT Pro watch_balance() 方法
                    balance = await self.ws_exchange.watch_balance()

                    # 解析并回调
                    snapshot = self._parse_ws_balance(balance)
                    await callback(snapshot)

                except asyncio.CancelledError:
                    logger.info("WebSocket 账户订阅被取消")
                    break

                except Exception as e:
                    reconnect_count += 1
                    if reconnect_count >= self._max_reconnect_attempts:
                        raise ConnectionLostError(
                            f"WebSocket 重连失败超过 {self._max_reconnect_attempts} 次",
                            "C-001"
                        )

                    # 指数退避
                    delay = min(
                        self._initial_reconnect_delay * (2 ** (reconnect_count - 1)),
                        self._max_reconnect_delay
                    )
                    logger.warning(
                        f"WebSocket 重连中... {delay:.1f}s "
                        f"(尝试 {reconnect_count}/{self._max_reconnect_attempts})"
                    )
                    await asyncio.sleep(delay)

        finally:
            self._ws_running = False
            if self.ws_exchange:
                await self.ws_exchange.close()

    def _parse_ws_balance(
        self,
        balance: Dict[str, Any],
    ) -> AccountSnapshot:
        """
        解析 WebSocket 余额消息为 AccountSnapshot

        Args:
            balance: CCXT Pro watch_balance() 返回的余额数据

        Returns:
            AccountSnapshot 对象
        """
        total_balance = Decimal('0')
        available_balance = Decimal('0')
        unrealized_pnl = Decimal('0')

        # 解析 USDT 余额
        if 'total' in balance and 'USDT' in balance['total']:
            total_balance = Decimal(str(balance['total']['USDT']))
        if 'free' in balance and 'USDT' in balance['free']:
            available_balance = Decimal(str(balance['free']['USDT']))

        return AccountSnapshot(
            total_balance=total_balance,
            available_balance=available_balance,
            unrealized_pnl=unrealized_pnl,
            positions=[],  # WebSocket 余额不包含持仓，需要单独获取
            timestamp=int(time.time() * 1000),
        )

    async def _poll_assets_loop_with_callback(
        self,
        callback: Callable[[AccountSnapshot], Awaitable[None]],
        interval_seconds: int = 60,
    ) -> None:
        """
        降级轮询模式（带回调）

        Args:
            callback: 资产更新时的异步回调
            interval_seconds: 轮询间隔
        """
        logger.info(f"降级轮询模式已启动（间隔：{interval_seconds}s）")

        while True:
            try:
                snapshot = await self._poll_account()
                await callback(snapshot)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"降级轮询失败：{e}")

            await asyncio.sleep(interval_seconds)

    async def start_asset_polling(
        self,
        interval_seconds: int = 60,
    ) -> None:
        """
        Start background task to poll account balance and positions.

        Args:
            interval_seconds: Polling interval
        """
        if self._asset_polling_task:
            self._asset_polling_task.cancel()
            try:
                await self._asset_polling_task
            except asyncio.CancelledError:
                pass

        self._polling_failures = 0
        self._asset_polling_task = asyncio.create_task(
            self._poll_assets_loop(interval_seconds)
        )
        logger.info(f"Asset polling started (interval: {interval_seconds}s)")

    async def _poll_assets_loop(self, interval_seconds: int) -> None:
        """Background polling loop"""
        while True:
            try:
                await self._poll_account()
                self._polling_failures = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._polling_failures += 1
                logger.error(f"Asset polling error ({self._polling_failures}): {e}")

                if self._polling_failures >= self._max_polling_failures:
                    raise ConnectionLostError(
                        f"Asset polling failed {self._polling_failures} consecutive times",
                        "C-002"
                    )

            await asyncio.sleep(interval_seconds)

    async def _poll_account(self) -> AccountSnapshot:
        """
        Poll account balance and positions, return snapshot.

        Returns:
            AccountSnapshot object
        """
        try:
            # Fetch balance
            balance = await self.rest_exchange.fetch_balance()

            # Fetch positions
            positions = await self.rest_exchange.fetch_positions()

            # Parse balance (futures account)
            total_balance = Decimal('0')
            available_balance = Decimal('0')
            unrealized_pnl = Decimal('0')

            if 'total' in balance:
                # USDT balance for futures
                if 'USDT' in balance['total']:
                    total_balance = Decimal(str(balance['total']['USDT']))
                if 'free' in balance and 'USDT' in balance['free']:
                    available_balance = Decimal(str(balance['free']['USDT']))

            # Parse positions
            position_list: List[PositionInfo] = []
            for pos in positions:
                if pos.get('contracts') and pos['contracts'] > 0:
                    leverage_val = pos.get('leverage')
                    if leverage_val is None:
                        leverage_val = 1
                    position = PositionInfo(
                        symbol=pos['symbol'],
                        side=pos['side'] if pos['side'] else 'none',
                        size=Decimal(str(pos['contracts'])),
                        entry_price=Decimal(str(pos['entryPrice'])) if pos.get('entryPrice') else Decimal('0'),
                        mark_price=Decimal(str(pos['markPrice'])) if pos.get('markPrice') else None,
                        unrealized_pnl=Decimal(str(pos['unrealizedPnl'])) if pos.get('unrealizedPnl') else Decimal('0'),
                        leverage=int(leverage_val),
                    )
                    position_list.append(position)
                    unrealized_pnl += position.unrealized_pnl

            # Create snapshot
            snapshot = AccountSnapshot(
                total_balance=total_balance,
                available_balance=available_balance,
                unrealized_pnl=unrealized_pnl,
                positions=position_list,
                timestamp=int(time.time() * 1000),
            )

            # Update cache
            self._account_snapshot = snapshot

            logger.debug(f"Asset snapshot updated: balance={total_balance}, positions={len(position_list)}")
            return snapshot

        except Exception as e:
            raise

    def get_account_snapshot(self) -> Optional[AccountSnapshot]:
        """
        Get the latest cached account snapshot.

        Returns:
            AccountSnapshot or None if not yet polled
        """
        return self._account_snapshot

    async def fetch_account_balance(self) -> Optional[AccountSnapshot]:
        """
        获取账户余额快照（调用交易所 API）

        Phase 6: v3.0 账户管理 - GET /api/v3/account/balance

        Returns:
            AccountSnapshot 或 None（如果获取失败）

        Raises:
            F-004: 交易所初始化失败
            C-010: API 频率限制
        """
        try:
            return await self._poll_account()
        except Exception as e:
            logger.error(f"获取账户余额失败：{e}")
            return None

    async def fetch_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]:
        """
        获取持仓列表（调用交易所 API）

        Phase 6: v3.0 仓位管理 - GET /api/v3/positions

        Args:
            symbol: 币种对过滤（可选），如 "BTC/USDT:USDT"

        Returns:
            List[PositionInfo]: 持仓列表

        Raises:
            F-004: 交易所初始化失败
            C-010: API 频率限制
        """
        import ccxt

        try:
            # 调用 CCXT fetch_positions
            positions = await self.rest_exchange.fetch_positions()

            # 解析持仓
            position_list: List[PositionInfo] = []
            for pos in positions:
                # 过滤符号（如果需要）
                if symbol and pos.get('symbol') != symbol:
                    continue

                # 跳过无持仓
                if not pos.get('contracts') or pos['contracts'] <= 0:
                    continue

                leverage_val = pos.get('leverage', 1)
                liquidation_price = (
                    pos.get('liquidationPrice')
                    or pos.get('liquidation_price')
                    or (pos.get('info') or {}).get('liquidationPrice')
                )
                position = PositionInfo(
                    symbol=pos['symbol'],
                    side=pos['side'] if pos.get('side') else 'none',
                    size=Decimal(str(pos['contracts'])),
                    entry_price=Decimal(str(pos['entryPrice'])) if pos.get('entryPrice') else Decimal('0'),
                    mark_price=Decimal(str(pos['markPrice'])) if pos.get('markPrice') else None,
                    unrealized_pnl=Decimal(str(pos['unrealizedPnl'])) if pos.get('unrealizedPnl') else Decimal('0'),
                    leverage=int(leverage_val) if leverage_val is not None else 1,
                    liquidation_price=Decimal(str(liquidation_price)) if liquidation_price else None,
                    margin_mode=pos.get('marginMode') or (pos.get('info') or {}).get('marginType'),
                )
                position_list.append(position)

            return position_list

        except ccxt.NetworkError as e:
            logger.error(f"网络错误，无法获取持仓：{e}")
            raise
        except ccxt.RateLimitExceeded as e:
            logger.error(f"API 频率限制：{e}")
            raise
        except Exception as e:
            logger.error(f"获取持仓失败：{e}")
            raise

    async def fetch_position_rows(self, symbol: str) -> List[Dict[str, Any]]:
        """Return a complete, side-preserving CCXT position view.

        Lifecycle reconciliation needs zero-sized rows and Binance
        ``positionSide``.  The legacy ``fetch_positions`` method intentionally
        returns active ``PositionInfo`` objects and therefore cannot prove a
        hedge bucket flat.  This read-only method keeps the complete venue
        shape, validates quantities, and never infers a missing side.
        """

        try:
            raw_positions = await self.rest_exchange.fetch_positions()
        except Exception as exc:
            logger.error(
                "获取完整持仓视图失败：symbol=%s, error=%s",
                symbol,
                exc,
            )
            raise
        if not isinstance(raw_positions, list):
            raise RuntimeError("exchange_position_rows_root_not_list")
        rows: List[Dict[str, Any]] = []
        for raw in raw_positions:
            if not isinstance(raw, dict):
                raise RuntimeError("exchange_position_row_not_object")
            row_symbol = str(raw.get("symbol") or "").strip()
            if not row_symbol:
                raise RuntimeError("exchange_position_symbol_missing")
            if row_symbol != symbol:
                continue
            contracts = raw.get("contracts")
            if contracts is None:
                raise RuntimeError("exchange_position_contracts_missing")
            try:
                size = Decimal(str(contracts))
            except (ArithmeticError, ValueError) as exc:
                raise RuntimeError("exchange_position_contracts_invalid") from exc
            info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
            position_side = str(
                raw.get("positionSide")
                or raw.get("position_side")
                or info.get("positionSide")
                or ""
            ).upper()
            rows.append(
                {
                    **raw,
                    "symbol": row_symbol,
                    "size": str(size),
                    "position_side": position_side,
                    "info": dict(info),
                }
            )
        return rows

    async def fetch_ticket_lifecycle_snapshot(
        self,
        *,
        exchange_symbol: str,
        exchange_market_id: str,
        recent_fill_limit: int,
        funding_start_time_ms: Optional[int],
        funding_end_time_ms: Optional[int],
        conditional_parent_order_ids: List[str],
    ) -> Dict[str, Any]:
        """Read one Ticket's Binance lifecycle truth without ``load_markets``.

        The method is intentionally narrow and read-only. It consumes the
        immutable venue market id resolved from PG, calls only signed Binance
        GET endpoints, and returns the existing lifecycle snapshot shapes.
        """

        if self.exchange_name.lower() != "binance":
            raise NotImplementedError(
                "ticket_lifecycle_snapshot_only_certified_for_binance"
            )
        market_id = str(exchange_market_id or "").strip().upper()
        if not market_id or not market_id.isalnum():
            raise ValueError("ticket_lifecycle_exchange_market_id_invalid")
        normalized_exchange_symbol = str(exchange_symbol or "").strip()
        if not normalized_exchange_symbol:
            raise ValueError("ticket_lifecycle_exchange_symbol_required")
        fill_limit = int(recent_fill_limit)
        if fill_limit <= 0 or fill_limit > 1000:
            raise ValueError("ticket_lifecycle_recent_fill_limit_invalid")

        rest = self.rest_exchange
        required_methods = {
            "positions": "fapiPrivateV3GetPositionRisk",
            "orders": "fapiPrivateGetOpenOrders",
            "algo_orders": "fapiPrivateGetOpenAlgoOrders",
            "trades": "fapiPrivateGetUserTrades",
            "account": "fapiPrivateV3GetAccount",
            "commission_rate": "fapiPrivateGetCommissionRate",
            "exchange_info": "fapiPublicGetExchangeInfo",
        }
        for capability, method_name in required_methods.items():
            if not callable(getattr(rest, method_name, None)):
                raise RuntimeError(
                    f"ticket_lifecycle_raw_{capability}_endpoint_missing"
                )

        funding_requested = (
            funding_start_time_ms is not None
            and funding_end_time_ms is not None
            and int(funding_end_time_ms) >= int(funding_start_time_ms)
        )
        parent_ids = list(
            dict.fromkeys(
                str(value).strip()
                for value in conditional_parent_order_ids
                if str(value or "").strip()
            )
        )

        async def _optional_funding() -> Dict[str, Any]:
            if not funding_requested:
                return {"rows": [], "error": None}
            raw_fetch = getattr(rest, "fapiPrivateGetIncome", None)
            if not callable(raw_fetch):
                return {"rows": [], "error": "funding_endpoint_missing"}
            try:
                rows = await raw_fetch(
                    {
                        "symbol": market_id,
                        "incomeType": "FUNDING_FEE",
                        "startTime": int(funding_start_time_ms or 0),
                        "endTime": int(funding_end_time_ms or 0),
                        "limit": 1000,
                    }
                )
                return {"rows": list(rows or []), "error": None}
            except Exception as exc:
                return {"rows": [], "error": type(exc).__name__}

        async def _optional_lineage() -> Dict[str, Any]:
            if not parent_ids:
                return {"rows": [], "error": None}
            try:
                rows = await self.fetch_conditional_order_lineage(
                    normalized_exchange_symbol,
                    parent_ids,
                )
                return {"rows": list(rows or []), "error": None}
            except Exception as exc:
                return {"rows": [], "error": type(exc).__name__}

        (
            raw_positions,
            raw_orders,
            raw_algo_orders,
            raw_trades,
            raw_account,
            raw_commission_rate,
            raw_exchange_info,
            funding_result,
            conditional_result,
        ) = await asyncio.gather(
            rest.fapiPrivateV3GetPositionRisk({"symbol": market_id}),
            rest.fapiPrivateGetOpenOrders({"symbol": market_id}),
            rest.fapiPrivateGetOpenAlgoOrders({"symbol": market_id}),
            rest.fapiPrivateGetUserTrades(
                {"symbol": market_id, "limit": fill_limit}
            ),
            rest.fapiPrivateV3GetAccount(),
            rest.fapiPrivateGetCommissionRate({"symbol": market_id}),
            rest.fapiPublicGetExchangeInfo({"symbol": market_id}),
            _optional_funding(),
            _optional_lineage(),
        )
        if not all(
            isinstance(rows, list)
            for rows in (raw_positions, raw_orders, raw_algo_orders, raw_trades)
        ) or not isinstance(raw_account, dict) or not isinstance(
            raw_commission_rate, dict
        ) or not isinstance(raw_exchange_info, dict):
            raise RuntimeError("ticket_lifecycle_raw_snapshot_shape_invalid")
        if str(raw_commission_rate.get("symbol") or "") != market_id:
            raise RuntimeError("ticket_lifecycle_commission_symbol_mismatch")

        positions = [
            self._ticket_lifecycle_position_row(
                row,
                exchange_symbol=normalized_exchange_symbol,
            )
            for row in raw_positions
            if isinstance(row, dict) and str(row.get("symbol") or "") == market_id
        ]
        open_orders = [
            self._ticket_lifecycle_regular_order_row(
                row,
                exchange_symbol=normalized_exchange_symbol,
            )
            for row in raw_orders
            if isinstance(row, dict)
        ]
        open_orders.extend(
            self._ticket_lifecycle_algo_order_row(
                row,
                exchange_symbol=normalized_exchange_symbol,
            )
            for row in raw_algo_orders
            if isinstance(row, dict)
        )
        recent_fills = [
            self._ticket_lifecycle_trade_row(
                row,
                exchange_symbol=normalized_exchange_symbol,
            )
            for row in raw_trades
            if isinstance(row, dict)
        ]
        account_exposure = self._ticket_lifecycle_account_exposure(raw_account)
        commission_rate = {
            "symbol": market_id,
            "maker_commission_rate": str(
                raw_commission_rate.get("makerCommissionRate") or ""
            ),
            "taker_commission_rate": str(
                raw_commission_rate.get("takerCommissionRate") or ""
            ),
        }
        market_rule = self._ticket_lifecycle_market_rule(
            raw_exchange_info,
            market_id=market_id,
        )
        return {
            "open_orders": open_orders,
            "recent_fills": recent_fills,
            "positions": positions,
            "funding_result": funding_result,
            "conditional_result": conditional_result,
            "account_exposure_result": account_exposure,
            "commission_rate": commission_rate,
            "market_rule": market_rule,
            "exchange_request_count": (
                7 + int(funding_requested) + len(parent_ids)
            ),
        }

    @staticmethod
    def _ticket_lifecycle_market_rule(
        payload: Dict[str, Any],
        *,
        market_id: str,
    ) -> Dict[str, Any]:
        symbols = [
            row
            for row in payload.get("symbols", [])
            if isinstance(row, dict) and str(row.get("symbol") or "") == market_id
        ]
        if len(symbols) != 1:
            raise RuntimeError("ticket_lifecycle_market_rule_symbol_not_unique")
        filters = {
            str(row.get("filterType") or ""): row
            for row in symbols[0].get("filters", [])
            if isinstance(row, dict)
        }
        price_tick = str(filters.get("PRICE_FILTER", {}).get("tickSize") or "")
        quantity_step = str(filters.get("LOT_SIZE", {}).get("stepSize") or "")
        min_notional = str(
            filters.get("MIN_NOTIONAL", {}).get("notional")
            or filters.get("NOTIONAL", {}).get("minNotional")
            or ""
        )
        try:
            if Decimal(price_tick) <= 0 or Decimal(quantity_step) <= 0:
                raise ValueError
            if min_notional and Decimal(min_notional) <= 0:
                raise ValueError
        except (ArithmeticError, ValueError) as exc:
            raise RuntimeError("ticket_lifecycle_market_rule_invalid") from exc
        return {
            "exchange_market_id": market_id,
            "price_tick": price_tick,
            "quantity_step": quantity_step,
            "min_notional": min_notional or None,
            "source": "binance_usdm_public_exchange_info",
        }

    @staticmethod
    def _ticket_lifecycle_position_row(
        raw: Dict[str, Any],
        *,
        exchange_symbol: str,
    ) -> Dict[str, Any]:
        position_amount = Decimal(str(raw.get("positionAmt") or "0"))
        position_side = str(raw.get("positionSide") or "").upper()
        if position_side == "LONG":
            side = "long"
        elif position_side == "SHORT":
            side = "short"
        else:
            side = "short" if position_amount < 0 else "long"
        return {
            "symbol": exchange_symbol,
            "size": str(abs(position_amount)),
            "side": side,
            "position_side": position_side,
            "entry_price": str(raw.get("entryPrice") or ""),
            "mark_price": str(raw.get("markPrice") or ""),
            "unrealized_pnl": str(raw.get("unRealizedProfit") or ""),
            "liquidation_price": str(raw.get("liquidationPrice") or ""),
            "info": dict(raw),
        }

    @staticmethod
    def _ticket_lifecycle_regular_order_row(
        raw: Dict[str, Any],
        *,
        exchange_symbol: str,
    ) -> Dict[str, Any]:
        return {
            "id": str(raw.get("orderId") or ""),
            "clientOrderId": str(raw.get("clientOrderId") or ""),
            "symbol": exchange_symbol,
            "side": str(raw.get("side") or "").lower(),
            "positionSide": str(raw.get("positionSide") or "").upper(),
            "amount": str(raw.get("origQty") or ""),
            "price": str(raw.get("price") or ""),
            "stopPrice": str(raw.get("stopPrice") or ""),
            "status": str(raw.get("status") or "").lower(),
            "reduceOnly": bool(raw.get("reduceOnly")),
            "closePosition": bool(raw.get("closePosition")),
            "info": dict(raw),
        }

    @staticmethod
    def _ticket_lifecycle_algo_order_row(
        raw: Dict[str, Any],
        *,
        exchange_symbol: str,
    ) -> Dict[str, Any]:
        return {
            "id": str(raw.get("algoId") or ""),
            "clientOrderId": str(raw.get("clientAlgoId") or ""),
            "symbol": exchange_symbol,
            "side": str(raw.get("side") or "").lower(),
            "positionSide": str(raw.get("positionSide") or "").upper(),
            "amount": str(raw.get("quantity") or ""),
            "price": "",
            "triggerPrice": str(raw.get("triggerPrice") or ""),
            "status": str(raw.get("algoStatus") or "").lower(),
            "reduceOnly": bool(raw.get("reduceOnly")),
            "closePosition": bool(raw.get("closePosition")),
            "info": dict(raw),
        }

    @staticmethod
    def _ticket_lifecycle_trade_row(
        raw: Dict[str, Any],
        *,
        exchange_symbol: str,
    ) -> Dict[str, Any]:
        return {
            "id": str(raw.get("id") or ""),
            "order": str(raw.get("orderId") or ""),
            "symbol": exchange_symbol,
            "side": str(raw.get("side") or "").lower(),
            "positionSide": str(raw.get("positionSide") or "").upper(),
            "amount": str(raw.get("qty") or ""),
            "price": str(raw.get("price") or ""),
            "commission": raw.get("commission"),
            "commissionAsset": raw.get("commissionAsset"),
            "timestamp": raw.get("time"),
            "maker": raw.get("maker"),
            "realizedPnl": raw.get("realizedPnl"),
            "info": dict(raw),
        }

    def _ticket_lifecycle_account_exposure(
        self,
        raw_account: Dict[str, Any],
    ) -> Dict[str, Any]:
        margin_balance = self._optional_nonnegative_decimal(
            raw_account.get("totalMarginBalance")
        )
        gross_notional = Decimal("0")
        raw_positions = raw_account.get("positions")
        if not isinstance(raw_positions, list):
            raise RuntimeError("ticket_lifecycle_account_positions_missing")
        for raw in raw_positions:
            if not isinstance(raw, dict):
                raise RuntimeError("ticket_lifecycle_account_position_invalid")
            notional = self._optional_nonnegative_decimal_abs(raw.get("notional"))
            if notional is not None:
                gross_notional += notional
        blockers: List[str] = []
        effective = None
        if margin_balance is None or margin_balance <= 0:
            blockers.append("account_margin_balance_missing_or_zero")
        else:
            effective = gross_notional / margin_balance
        return {
            "status": "ready" if not blockers else "partial",
            "account_id": str(getattr(self, "runtime_account_id", "") or ""),
            "exchange_id": str(getattr(self, "runtime_exchange_id", "") or ""),
            "account_margin_balance": (
                str(margin_balance) if margin_balance is not None else None
            ),
            "gross_open_position_notional": str(gross_notional),
            "effective_account_exposure_leverage": (
                str(effective) if effective is not None else None
            ),
            "observed_at_ms": int(time.time() * 1000),
            "blockers": blockers,
        }

    async def fetch_account_exposure_snapshot(self) -> Dict[str, Any]:
        """Return signed cross-margin exposure facts without mutating account state."""

        balance, positions = await asyncio.gather(
            self.rest_exchange.fetch_balance(),
            self.rest_exchange.fetch_positions(),
        )
        if not isinstance(balance, dict) or not isinstance(positions, list):
            raise RuntimeError("account_exposure_snapshot_shape_invalid")
        info = balance.get("info") if isinstance(balance.get("info"), dict) else {}
        margin_raw = info.get("totalMarginBalance")
        if margin_raw in {None, ""}:
            totals = balance.get("total") if isinstance(balance.get("total"), dict) else {}
            margin_raw = totals.get("USDT")
        margin_balance = self._optional_nonnegative_decimal(margin_raw)
        gross_notional = Decimal("0")
        for raw in positions:
            if not isinstance(raw, dict):
                raise RuntimeError("account_exposure_position_row_invalid")
            position_info = (
                raw.get("info") if isinstance(raw.get("info"), dict) else {}
            )
            direct_notional = raw.get("notional")
            if direct_notional in {None, ""}:
                direct_notional = position_info.get("notional")
            notional = self._optional_nonnegative_decimal_abs(direct_notional)
            if notional is None:
                contracts = self._optional_nonnegative_decimal_abs(
                    raw.get("contracts")
                )
                mark_price = self._optional_nonnegative_decimal_abs(
                    raw.get("markPrice")
                    or raw.get("mark_price")
                    or position_info.get("markPrice")
                )
                contract_size = self._optional_nonnegative_decimal_abs(
                    raw.get("contractSize")
                    or raw.get("contract_size")
                    or position_info.get("contractSize")
                    or "1"
                )
                if contracts is None or mark_price is None or contract_size is None:
                    if contracts in {None, Decimal("0")}:
                        continue
                    raise RuntimeError("account_exposure_position_notional_missing")
                notional = contracts * mark_price * contract_size
            gross_notional += notional
        blockers: list[str] = []
        effective = None
        if margin_balance is None or margin_balance <= 0:
            blockers.append("account_margin_balance_missing_or_zero")
        else:
            effective = gross_notional / margin_balance
        return {
            "status": "ready" if not blockers else "partial",
            "account_id": str(
                getattr(self, "runtime_account_id", "") or ""
            ),
            "exchange_id": str(
                getattr(self, "runtime_exchange_id", "") or ""
            ),
            "account_margin_balance": (
                str(margin_balance) if margin_balance is not None else None
            ),
            "gross_open_position_notional": str(gross_notional),
            "effective_account_exposure_leverage": (
                str(effective) if effective is not None else None
            ),
            "observed_at_ms": int(time.time() * 1000),
            "blockers": blockers,
        }

    @staticmethod
    def _optional_nonnegative_decimal(value: Any) -> Optional[Decimal]:
        if value in {None, ""}:
            return None
        parsed = Decimal(str(value))
        return parsed if parsed >= 0 else None

    @staticmethod
    def _optional_nonnegative_decimal_abs(value: Any) -> Optional[Decimal]:
        if value in {None, ""}:
            return None
        return abs(Decimal(str(value)))

    # ============================================================
    # Phase 5: Order Management APIs
    # ============================================================

    async def fetch_open_orders(
        self,
        symbol: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch exchange open orders for a symbol.

        LS-003a read-model wrapper: keep reconciliation callers off the raw
        exchange object while preserving the raw CCXT payload for parsing.
        """
        try:
            return await self.rest_exchange.fetch_open_orders(symbol, params=params or {})
        except Exception as e:
            logger.error(f"获取未完成订单失败：symbol={symbol}, error={e}")
            raise

    async def fetch_all_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch the complete venue open-order view for one symbol.

        Binance USDT-M exposes regular orders and conditional/algo orders via
        separate CCXT views.  Both reads are required: a failure in either view
        is propagated so callers cannot mistake an incomplete snapshot for an
        authoritative absence.  Other exchanges retain the unified default
        view until their gateway capability contract says otherwise.
        """

        normal_orders = await self.fetch_open_orders(symbol)
        order_views = [normal_orders]
        if str(getattr(self, "exchange_name", "")).lower() == "binance":
            conditional_orders = await self.fetch_open_orders(
                symbol,
                params={"stop": True},
            )
            order_views.append(conditional_orders)
        return self._merge_open_order_views(order_views)

    async def fetch_my_trades(
        self,
        symbol: str,
        limit: int = 50,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch account trade fills for a symbol.

        Ticket-bound lifecycle close projection uses this as a read-only source
        for final exit / TP1 / SL fills. It must not submit, cancel, amend,
        withdraw, or transfer anything.
        """
        try:
            return await self.rest_exchange.fetch_my_trades(
                symbol,
                limit=limit,
                params=params or {},
            )
        except Exception as e:
            logger.error(f"获取成交记录失败：symbol={symbol}, error={e}")
            raise

    async def fetch_funding_income(
        self,
        symbol: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> List[Dict[str, Any]]:
        """Fetch signed Binance USD-M funding income for one exact market window.

        This is a read-only post-trade accounting source.  It does not submit,
        cancel, amend, withdraw, transfer, or mutate account configuration.
        """

        exchange_name = str(getattr(self, "exchange_name", "")).lower()
        raw_fetch = getattr(self.rest_exchange, "fapiPrivateGetIncome", None)
        if "binance" not in exchange_name or not callable(raw_fetch):
            raise NotImplementedError("funding_income_read_not_supported")
        if int(start_time_ms) < 0 or int(end_time_ms) < int(start_time_ms):
            raise ValueError("funding_income_time_window_invalid")
        market = self.rest_exchange.market(symbol)
        market_id = str(market.get("id") or "").strip()
        if not market_id:
            raise ValueError("funding_income_exchange_market_id_missing")
        params = {
            "symbol": market_id,
            "incomeType": "FUNDING_FEE",
            "startTime": int(start_time_ms),
            "endTime": int(end_time_ms),
            "limit": 1000,
        }
        try:
            rows = await raw_fetch(params)
        except Exception as e:
            logger.error(
                "获取资金费收入失败：symbol=%s, start=%s, end=%s, error=%s",
                symbol,
                start_time_ms,
                end_time_ms,
                e,
            )
            raise
        return list(rows or [])

    async def place_order(
        self,
        symbol: str,
        order_type: str,           # "market", "limit", "stop_market"
        side: str,                 # "buy" (开多/平空), "sell" (开空/平多)
        amount: Decimal,           # 数量
        price: Optional[Decimal] = None,      # 限价单价格
        trigger_price: Optional[Decimal] = None,  # 条件单触发价
        reduce_only: bool = False,  # 仅减仓（平仓单必须设置）
        position_side: Optional[str] = None,  # Binance futures hedge mode: LONG/SHORT
        desired_leverage: Optional[int] = None,  # ENTRY-only Action-Time leverage
        client_order_id: Optional[str] = None,  # 客户端订单 ID
        time_in_force: Optional[str] = None,  # normalized GTC/GTX intent
        post_only: bool = False,  # typed passive-limit intent
    ) -> OrderPlacementResult:
        """
        下单接口

        Args:
            symbol: 币种对，如 "BTC/USDT:USDT"
            order_type: 订单类型 ("market", "limit", "stop_market")
            side: 买卖方向 ("buy" | "sell")
            amount: 订单数量
            price: 限价单价格（LIMIT 订单必填）
            trigger_price: 条件单触发价（STOP_MARKET 订单必填）
            reduce_only: 是否仅减仓（平仓单必须为 True）
            position_side: 持仓方向（Binance futures hedge mode 使用 LONG/SHORT）
            client_order_id: 客户端订单 ID（可选）
            time_in_force: 限价单有效期（GTC/GTX）
            post_only: 是否要求只做 maker（当前仅认证 Binance GTX）

        Returns:
            OrderPlacementResult: 订单放置结果

        Raises:
            InsufficientMarginError: 保证金不足
            InvalidOrderError: 订单参数错误
            RateLimitError: API 频率限制
        """
        import uuid
        import ccxt

        # 生成系统订单 ID
        system_order_id = str(uuid.uuid4())

        # 参数验证（在 try 块之外，直接抛出异常）
        if order_type == "limit" and price is None:
            raise InvalidOrderError("LIMIT 订单必须指定价格", "F-011")

        if order_type == "stop_market" and trigger_price is None:
            raise InvalidOrderError("STOP_MARKET 订单必须指定触发价", "F-011")

        normalized_tif = str(time_in_force or "").strip().upper() or None
        if normalized_tif not in {None, "GTC", "GTX"}:
            raise InvalidOrderError("不支持的限价单有效期", "F-011")
        if order_type != "limit" and (normalized_tif is not None or post_only):
            raise InvalidOrderError("仅限价单可设置 GTC/GTX 或 post-only", "F-011")
        if normalized_tif == "GTC" and post_only:
            raise InvalidOrderError("GTC 限价单不得声明 post-only", "F-011")
        if normalized_tif == "GTX" and not post_only:
            raise InvalidOrderError("GTX 必须声明 post-only", "F-011")
        if post_only and normalized_tif != "GTX":
            raise InvalidOrderError("post-only 必须使用 GTX", "F-011")
        if post_only and self.exchange_name.lower() != "binance":
            raise InvalidOrderError("当前交易所未认证 post-only 限价执行", "F-011")

        if desired_leverage is not None:
            if reduce_only:
                raise InvalidOrderError(
                    "保护/退出订单不得改变杠杆", "F-011"
                )
            if self.exchange_name.lower() != "binance":
                raise InvalidOrderError(
                    "动态杠杆当前仅支持 Binance USD-M", "F-011"
                )
            if isinstance(desired_leverage, bool) or not 1 <= int(desired_leverage) <= 125:
                raise InvalidOrderError("目标杠杆必须是 1-125 的整数", "F-011")

        try:
            configured_leverage = None
            leverage_verified_at_ms = None
            if desired_leverage is not None:
                configured_leverage, leverage_verified_at_ms = (
                    await self._set_and_verify_entry_leverage(
                        symbol=symbol,
                        selected_leverage=int(desired_leverage),
                        position_side=position_side,
                    )
                )
            # 映射订单类型到 CCXT 格式
            ccxt_type = self._map_order_type_to_ccxt(order_type)

            payload = self._build_ccxt_order_params(
                order_type=order_type,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                position_side=position_side,
                client_order_id=client_order_id,
                time_in_force=normalized_tif,
                post_only=post_only,
            )

            # 调用 CCXT create_order 方法
            # P0 修复：使用 str() 而非 float() 避免精度污染 (CCXT 支持字符串输入)
            order = await self.rest_exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=side,
                amount=str(amount),
                price=str(price) if price is not None else None,
                params=payload.params,
            )

            # 解析订单响应
            order_status = self._parse_order_status(order.get('status', 'open'))
            filled_qty = Decimal(str(order['filled'])) if order.get('filled') else None
            average_exec_price = Decimal(str(order['average'])) if order.get('average') else None

            return OrderPlacementResult(
                order_id=system_order_id,
                exchange_order_id=order.get('id'),
                symbol=symbol,
                order_type=OrderType(order_type.upper()),
                direction=self._map_side_to_direction(side, reduce_only),
                side=side,
                amount=amount,
                price=price,
                filled_qty=filled_qty,
                average_exec_price=average_exec_price,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                exchange_reduce_only_param_sent=payload.exchange_reduce_only_param_sent,
                exchange_reduce_only_omit_reason=payload.exchange_reduce_only_omit_reason,
                selected_leverage=(
                    int(desired_leverage)
                    if desired_leverage is not None
                    else None
                ),
                exchange_configured_initial_leverage=configured_leverage,
                leverage_verified_at_ms=leverage_verified_at_ms,
                client_order_id=client_order_id,
                status=order_status,
            )

        except InvalidOrderError:
            raise

        except ccxt.InsufficientFunds as e:
            logger.warning(f"保证金不足：{e}")
            raise InsufficientMarginError(f"保证金不足以下单：{e}", "F-010")

        except ccxt.InvalidOrder as e:
            logger.warning(f"订单参数错误：{e}")
            raise InvalidOrderError(f"订单参数错误：{e}", "F-011")

        except ccxt.DDoSProtection as e:
            logger.warning(f"API 频率限制：{e}")
            raise RateLimitError(f"API 频率限制：{e}", "C-010")

        except ccxt.NetworkError as e:
            logger.error(f"网络错误：{e}")
            raise ConnectionLostError(f"网络错误：{e}", "C-001")

        except Exception as e:
            logger.error(f"下单失败：{e}")
            raise ConnectionLostError(
                "下单请求结果不确定，必须按 client_order_id 查询交易所事实："
                f"{e}",
                "C-002",
            )

    async def _set_and_verify_entry_leverage(
        self,
        *,
        symbol: str,
        selected_leverage: int,
        position_side: Optional[str],
    ) -> tuple[int, int]:
        before_rows = await self.fetch_position_rows(symbol)
        exact_before = self._exact_leverage_position_rows(
            before_rows,
            position_side=position_side,
        )
        if any(Decimal(str(row.get("size") or "0")) != 0 for row in exact_before):
            raise InvalidOrderError(
                "entry_leverage_open_position_bucket_not_flat",
                "F-011",
            )
        await self.rest_exchange.set_leverage(selected_leverage, symbol)
        after_rows = await self.fetch_position_rows(symbol)
        exact_after = self._exact_leverage_position_rows(
            after_rows,
            position_side=position_side,
        )
        configured_values: set[int] = set()
        for row in exact_after:
            info = row.get("info") if isinstance(row.get("info"), dict) else {}
            raw = row.get("leverage")
            if raw is None:
                raw = info.get("leverage")
            if raw in {None, ""}:
                continue
            try:
                configured_values.add(int(Decimal(str(raw))))
            except (ArithmeticError, ValueError) as exc:
                raise InvalidOrderError(
                    "exchange_configured_leverage_readback_invalid",
                    "F-011",
                ) from exc
        if not configured_values:
            raise InvalidOrderError(
                "exchange_configured_leverage_readback_missing",
                "F-011",
            )
        if configured_values != {selected_leverage}:
            raise InvalidOrderError(
                "exchange_configured_leverage_readback_mismatch",
                "F-011",
            )
        return selected_leverage, int(time.time() * 1000)

    @staticmethod
    def _exact_leverage_position_rows(
        rows: List[Dict[str, Any]],
        *,
        position_side: Optional[str],
    ) -> List[Dict[str, Any]]:
        expected_side = str(position_side or "").upper()
        if expected_side:
            return [
                row
                for row in rows
                if str(row.get("position_side") or "").upper() == expected_side
            ]
        return [
            row
            for row in rows
            if str(row.get("position_side") or "").upper() in {"", "BOTH"}
        ]

    async def _cancel_conditional_open_order_if_visible(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:
        """Cancel Binance futures conditional orders visible only in stop-order views."""
        try:
            raw_orders = await self.fetch_all_open_orders(symbol)
        except Exception as exc:
            logger.warning(
                "Conditional open-order lookup failed during cancel fallback: "
                "symbol=%s exchange_order_id=%s error=%s",
                symbol,
                exchange_order_id,
                exc,
                exc_info=True,
            )
            raise

        for raw_order in raw_orders or []:
            if not self._raw_order_matches(
                raw_order,
                exchange_order_id=exchange_order_id,
                client_order_id=None,
                expected_symbol=symbol,
            ):
                continue
            logger.warning(
                "Order cancel fallback matched conditional open order: "
                "symbol=%s exchange_order_id=%s",
                symbol,
                exchange_order_id,
            )
            try:
                return await self.rest_exchange.cancel_order(
                    exchange_order_id,
                    symbol,
                    params={"stop": True},
                )
            except Exception as exc:
                logger.warning(
                    "Conditional order cancel fallback failed: "
                    "symbol=%s exchange_order_id=%s error=%s",
                    symbol,
                    exchange_order_id,
                    exc,
                    exc_info=True,
                )
                return None

        return None

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> OrderCancelResult:
        """
        取消订单

        Args:
            exchange_order_id: 交易所订单 ID（注意：不是系统内部的 order_id UUID）
            symbol: 币种对

        Returns:
            OrderCancelResult: 订单取消结果

        Raises:
            OrderNotFoundError: 订单不存在
            OrderAlreadyFilledError: 订单已成交（无法取消）
            RateLimitError: API 频率限制
        """
        import ccxt

        try:
            # CCXT cancel_order 参数顺序：(id, symbol) - 注意 id 在前
            # 注意：这里的 id 必须是交易所返回的订单 ID（exchange_order_id），而非系统内部 UUID
            order = await self.rest_exchange.cancel_order(exchange_order_id, symbol)

            # 解析订单状态
            order_status = self._parse_order_status(order.get('status') or 'canceled')

            if order_status == OrderStatus.FILLED:
                raise OrderAlreadyFilledError(f"订单已成交，无法取消：{exchange_order_id}", "F-013")

            return OrderCancelResult(
                order_id=exchange_order_id,
                exchange_order_id=order.get('id'),
                symbol=symbol,
                status=order_status,
                message="Order canceled successfully",
            )

        except ccxt.OrderNotFound as e:
            order = await self._cancel_conditional_open_order_if_visible(
                exchange_order_id,
                symbol,
            )
            if order is not None:
                order_status = self._parse_order_status(order.get('status') or 'canceled')
                if order_status == OrderStatus.FILLED:
                    raise OrderAlreadyFilledError(f"订单已成交，无法取消：{exchange_order_id}", "F-013")
                return OrderCancelResult(
                    order_id=exchange_order_id,
                    exchange_order_id=order.get('id'),
                    symbol=symbol,
                    status=order_status,
                    message="Conditional order canceled successfully",
                )

            logger.warning(f"订单不存在：{e}")
            raise OrderNotFoundError(f"订单不存在：{exchange_order_id}", "F-012")

        except ccxt.OrderNotFillable as e:
            logger.warning(f"订单已成交：{e}")
            raise OrderAlreadyFilledError(f"订单已成交，无法取消：{exchange_order_id}", "F-013")

        except ccxt.DDoSProtection as e:
            logger.warning(f"API 频率限制：{e}")
            raise RateLimitError(f"API 频率限制：{e}", "C-010")

        except ccxt.NetworkError as e:
            logger.error(f"网络错误：{e}")
            raise ConnectionLostError(f"网络错误：{e}", "C-001")

        except Exception as e:
            logger.error(f"取消订单失败：{e}")
            raise

    async def confirm_order_exists(
        self,
        *,
        exchange_order_id: Optional[str],
        symbol: str,
        client_order_id: Optional[str] = None,
        order_type: Optional[OrderType] = None,
        side: Optional[str] = None,
        reduce_only: Optional[bool] = None,
        stop_price: Optional[Decimal] = None,
        expected_type: Optional[str] = None,
        amount: Optional[Decimal] = None,
    ) -> bool:
        """Confirm an exchange-native order exists using conservative query paths.

        Binance futures conditional orders can surface different ids across
        normal order, trigger/conditional order, and websocket payloads. This
        helper accepts either the returned exchange id or the client order id
        and checks normal plus conditional open-order paths without mutating
        exchange state.
        """
        if not exchange_order_id and not client_order_id:
            return False

        for observed in self._recent_order_update_candidates(
            exchange_order_id,
            client_order_id,
            expected_symbol=symbol,
        ):
            if self._raw_order_matches(
                observed,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                expected_symbol=symbol,
                expected_side=side,
                expected_reduce_only=reduce_only,
                expected_type=expected_type,
                expected_stop_price=stop_price,
            ):
                return True

        fetch_order_missed = False
        if exchange_order_id:
            try:
                raw_fetched = await self.rest_exchange.fetch_order(exchange_order_id, symbol)
                status = str(raw_fetched.get("status", "")).lower()
                if status not in {"canceled", "rejected", "expired", "closed"}:
                    if self._raw_order_matches(
                        raw_fetched,
                        exchange_order_id=exchange_order_id,
                        client_order_id=client_order_id,
                        expected_symbol=symbol,
                        expected_side=side,
                        expected_reduce_only=reduce_only,
                        expected_type=expected_type,
                        expected_stop_price=stop_price,
                    ):
                        return True
            except Exception as exc:
                fetch_order_missed = True
                logger.warning(
                    "Order confirmation fetch_order miss: symbol=%s exchange_order_id=%s error=%s",
                    symbol,
                    exchange_order_id,
                    exc,
                )

        retry_delays = list(self._order_confirmation_retry_delays) if fetch_order_missed else []
        attempts = 1 + len(retry_delays)
        for attempt_idx in range(attempts):
            try:
                raw_orders = await self.fetch_all_open_orders(symbol)
            except Exception as exc:
                logger.warning(
                    "Order confirmation complete open-order read failed: "
                    "symbol=%s error=%s",
                    symbol,
                    exc,
                )
                raw_orders = []

            for raw_order in raw_orders:
                if self._raw_order_matches(
                    raw_order,
                    exchange_order_id=exchange_order_id,
                    client_order_id=client_order_id,
                    expected_symbol=symbol,
                    expected_side=side,
                    expected_reduce_only=reduce_only,
                    expected_type=expected_type,
                    expected_stop_price=stop_price,
                ):
                    return True
            if attempt_idx < len(retry_delays):
                await asyncio.sleep(retry_delays[attempt_idx])

        return False

    def _recent_order_update_candidates(
        self,
        exchange_order_id: Optional[str],
        client_order_id: Optional[str],
        expected_symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        if expected_symbol:
            symbol_key = self._normalize_symbol_key(expected_symbol)
            symbol_updates = self._recent_order_updates_by_symbol.get(symbol_key, {})
            for key in (exchange_order_id, client_order_id):
                if key is None:
                    continue
                raw_order = symbol_updates.get(str(key))
                if raw_order is not None and raw_order not in candidates:
                    candidates.append(raw_order)
        for key in (exchange_order_id, client_order_id):
            if key is None:
                continue
            raw_order = self._recent_order_updates.get(str(key))
            if raw_order is not None and raw_order not in candidates:
                candidates.append(raw_order)
        return candidates

    def _remember_recent_order_update(self, raw_order: Dict[str, Any]) -> None:
        raw_symbol = raw_order.get("symbol") or (raw_order.get("info") or {}).get("symbol")
        symbol_updates = None
        if raw_symbol:
            symbol_key = self._normalize_symbol_key(str(raw_symbol))
            symbol_updates = self._recent_order_updates_by_symbol.setdefault(symbol_key, {})
        for candidate_id in self._candidate_order_ids(raw_order):
            self._recent_order_updates[candidate_id] = raw_order
            if symbol_updates is not None:
                symbol_updates[candidate_id] = raw_order
        if len(self._recent_order_updates) > 1000:
            for stale_key in list(self._recent_order_updates.keys())[:200]:
                self._recent_order_updates.pop(stale_key, None)
        for symbol_key, updates in list(self._recent_order_updates_by_symbol.items()):
            if len(updates) > 1000:
                for stale_key in list(updates.keys())[:200]:
                    updates.pop(stale_key, None)
            if not updates:
                self._recent_order_updates_by_symbol.pop(symbol_key, None)

    @staticmethod
    def _normalize_symbol_key(symbol: str) -> str:
        return symbol.replace("/", "").replace(":", "").lower()

    @staticmethod
    def _candidate_order_ids(raw_order: Dict[str, Any]) -> set[str]:
        return ExchangeGateway._open_order_exchange_ids(
            raw_order
        ) | ExchangeGateway._open_order_client_ids(raw_order)

    @staticmethod
    def _open_order_exchange_ids(raw_order: Dict[str, Any]) -> set[str]:
        info = raw_order.get("info") if isinstance(raw_order.get("info"), dict) else {}
        values = {
            raw_order.get("id"),
            raw_order.get("orderId"),
            raw_order.get("exchange_order_id"),
            info.get("orderId"),
            info.get("algoId"),
            info.get("triggerOrderId"),
        }
        return {str(value) for value in values if value is not None and str(value)}

    @staticmethod
    def _open_order_client_ids(raw_order: Dict[str, Any]) -> set[str]:
        info = raw_order.get("info") if isinstance(raw_order.get("info"), dict) else {}
        values = {
            raw_order.get("clientOrderId"),
            raw_order.get("clientOrderid"),
            raw_order.get("client_order_id"),
            info.get("origClientOrderId"),
            info.get("clientOrderId"),
            info.get("clientOrderid"),
            info.get("clientAlgoId"),
        }
        return {str(value) for value in values if value is not None and str(value)}

    @classmethod
    def _merge_open_order_views(
        cls,
        order_views: List[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        merged_orders: List[Dict[str, Any]] = []
        exchange_id_indexes: Dict[str, int] = {}
        client_id_indexes: Dict[str, int] = {}

        for orders in order_views:
            for raw_order in orders or []:
                if not isinstance(raw_order, dict):
                    raise ConnectionLostError(
                        "Open-order view returned a non-structured order",
                        "C-002",
                    )
                exchange_ids = cls._open_order_exchange_ids(raw_order)
                client_ids = cls._open_order_client_ids(raw_order)
                matching_indexes = {
                    index
                    for identity, index in exchange_id_indexes.items()
                    if identity in exchange_ids
                } | {
                    index
                    for identity, index in client_id_indexes.items()
                    if identity in client_ids
                }
                if len(matching_indexes) > 1:
                    raise ConnectionLostError(
                        "Open-order views returned contradictory order identities",
                        "C-002",
                    )

                if matching_indexes:
                    index = next(iter(matching_indexes))
                    existing = merged_orders[index]
                    combined_exchange_ids = (
                        cls._open_order_exchange_ids(existing) | exchange_ids
                    )
                    combined_client_ids = (
                        cls._open_order_client_ids(existing) | client_ids
                    )
                    merged_orders[index] = cls._merge_open_order_payload(
                        existing,
                        raw_order,
                    )
                else:
                    index = len(merged_orders)
                    merged_orders.append(dict(raw_order))
                    combined_exchange_ids = exchange_ids
                    combined_client_ids = client_ids

                cls._bind_open_order_identities(
                    exchange_id_indexes,
                    combined_exchange_ids,
                    index,
                )
                cls._bind_open_order_identities(
                    client_id_indexes,
                    combined_client_ids,
                    index,
                )

        return merged_orders

    @staticmethod
    def _bind_open_order_identities(
        identity_indexes: Dict[str, int],
        identities: set[str],
        index: int,
    ) -> None:
        for identity in identities:
            existing_index = identity_indexes.get(identity)
            if existing_index is not None and existing_index != index:
                raise ConnectionLostError(
                    "Open-order views returned contradictory order identities",
                    "C-002",
                )
            identity_indexes[identity] = index

    @staticmethod
    def _merge_open_order_payload(
        existing: Dict[str, Any],
        incoming: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = dict(existing)
        identity_keys = {
            "clientOrderId",
            "clientOrderid",
            "client_order_id",
            "symbol",
        }
        for key, value in incoming.items():
            if key == "info":
                existing_info = (
                    dict(merged.get("info"))
                    if isinstance(merged.get("info"), dict)
                    else {}
                )
                incoming_info = value if isinstance(value, dict) else {}
                existing_info.update(
                    {
                        info_key: info_value
                        for info_key, info_value in incoming_info.items()
                        if info_value is not None and info_value != ""
                    }
                )
                merged["info"] = existing_info
                continue
            if value is None or value == "":
                continue
            if key in identity_keys and merged.get(key) not in {None, ""}:
                continue
            merged[key] = value
        return merged

    @staticmethod
    def _raw_order_matches(
        raw_order: Dict[str, Any],
        *,
        exchange_order_id: Optional[str],
        client_order_id: Optional[str],
        expected_symbol: str,
        expected_side: Optional[str] = None,
        expected_reduce_only: Optional[bool] = None,
        expected_type: Optional[str] = None,
        expected_stop_price: Optional[Decimal] = None,
    ) -> bool:
        info = raw_order.get("info") or {}
        candidate_ids = ExchangeGateway._candidate_order_ids(raw_order)
        id_matched = (
            (exchange_order_id is not None and str(exchange_order_id) in candidate_ids)
            or (client_order_id is not None and str(client_order_id) in candidate_ids)
        )
        if not id_matched:
            return False

        try:
            raw_symbol = raw_order.get("symbol") or info.get("symbol")
            if raw_symbol:
                s_raw = str(raw_symbol).replace("/", "").replace(":", "").lower()
                s_exp = str(expected_symbol).replace("/", "").replace(":", "").lower()
                if s_raw != s_exp and str(raw_symbol) != expected_symbol:
                    logger.warning(f"[_raw_order_matches] false positive prevented: symbol {raw_symbol} != {expected_symbol}")
                    return False

            if expected_side:
                raw_side = raw_order.get("side") or info.get("side")
                if raw_side and str(raw_side).lower() != str(expected_side).lower():
                    logger.warning(f"[_raw_order_matches] false positive prevented: side {raw_side} != {expected_side}")
                    return False

            if expected_reduce_only is not None:
                raw_reduce = raw_order.get("reduceOnly")
                if raw_reduce is None:
                    raw_reduce = info.get("reduceOnly")
                if raw_reduce is not None:
                    act_ro = str(raw_reduce).lower() in ("true", "1", "yes")
                    if act_ro != expected_reduce_only:
                        logger.warning(f"[_raw_order_matches] false positive prevented: reduceOnly {act_ro} != {expected_reduce_only}")
                        return False

            if expected_type:
                raw_type = raw_order.get("type") or info.get("type") or info.get("origType") or info.get("stopType")
                if raw_type:
                    t_raw = str(raw_type).lower()
                    t_exp = str(expected_type).lower()
                    if t_exp not in t_raw and t_raw not in t_exp:
                        logger.warning(f"[_raw_order_matches] false positive prevented: type {raw_type} != {expected_type}")
                        return False

            if expected_stop_price is not None:
                raw_stop_price = raw_order.get("stopPrice") or info.get("stopPrice") or info.get("triggerPrice")
                if raw_stop_price is not None:
                    act_sp = Decimal(str(raw_stop_price))
                    # Binance truncates stopPrice to tick size (e.g., 0.01 for ETH).
                    # Use relative tolerance of 0.1% + absolute tolerance of 0.02
                    # to absorb tick-size truncation while still catching mismatches.
                    tolerance = max(
                        abs(expected_stop_price) * Decimal("0.001"),
                        Decimal("0.02"),
                    )
                    if abs(act_sp - expected_stop_price) > tolerance:
                        logger.warning(f"[_raw_order_matches] false positive prevented: stopPrice {act_sp} != {expected_stop_price} (tolerance={tolerance})")
                        return False

            return True
        except Exception as exc:
            logger.warning(f"[_raw_order_matches] validation exception: {exc}")
            return False

    async def fetch_order(self, exchange_order_id: str, symbol: str) -> OrderPlacementResult:
        """
        查询订单状态

        Args:
            exchange_order_id: 交易所订单 ID（注意：不是系统内部的 order_id UUID）
            symbol: 币种对

        Returns:
            OrderPlacementResult: 订单状态结果

        Raises:
            OrderNotFoundError: 订单不存在
            RateLimitError: API 频率限制
        """
        import ccxt

        try:
            # CCXT fetch_order 参数顺序：(id, symbol) - 注意 id 在前
            # 注意：这里的 id 必须是交易所返回的订单 ID（exchange_order_id），而非系统内部 UUID
            order = await self.rest_exchange.fetch_order(exchange_order_id, symbol)
            return self._order_placement_result_from_raw_order(
                order,
                exchange_order_id=exchange_order_id,
                symbol=symbol,
            )

        except ccxt.OrderNotFound as e:
            fallback = await self._fetch_conditional_open_order_by_id(
                exchange_order_id,
                symbol,
            )
            if fallback is not None:
                logger.warning(
                    "fetch_order fallback matched conditional open order: "
                    "symbol=%s exchange_order_id=%s",
                    symbol,
                    exchange_order_id,
                )
                return self._order_placement_result_from_raw_order(
                    fallback,
                    exchange_order_id=exchange_order_id,
                    symbol=symbol,
                )
            logger.warning(f"订单不存在：{e}")
            raise OrderNotFoundError(f"订单不存在：{exchange_order_id}", "F-012")

        except ccxt.DDoSProtection as e:
            logger.warning(f"API 频率限制：{e}")
            raise RateLimitError(f"API 频率限制：{e}", "C-010")

        except ccxt.NetworkError as e:
            logger.error(f"网络错误：{e}")
            raise ConnectionLostError(f"网络错误：{e}", "C-001")

        except Exception as e:
            logger.error(f"查询订单失败：{e}")
            raise

    async def fetch_conditional_order_lineage(
        self,
        symbol: str,
        parent_exchange_order_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Read Binance conditional parent-to-actual order identity.

        Binance USDT-M exposes the submitted conditional order as ``algoId``
        and the triggered exchange order as ``actualOrderId``.  User trades
        contain only the latter, so both ids are required to conserve the
        ticket-bound SL/runner role after a trigger.  This method is read-only.
        """

        parent_ids = list(
            dict.fromkeys(
                str(value).strip()
                for value in parent_exchange_order_ids
                if str(value or "").strip()
            )
        )
        if not parent_ids:
            return []
        if self.exchange_name.lower() != "binance":
            return []
        rows: List[Dict[str, Any]] = []
        for parent_id in parent_ids:
            raw = await self.rest_exchange.fapiPrivateGetAlgoOrder(
                {"algoId": parent_id}
            )
            if not isinstance(raw, dict):
                raise ConnectionLostError(
                    "条件订单血缘查询返回非结构化响应",
                    "C-002",
                )
            observed_parent_id = str(raw.get("algoId") or "").strip()
            if observed_parent_id != parent_id:
                raise ConnectionLostError(
                    "条件订单血缘返回了不一致的父订单标识",
                    "C-002",
                )
            rows.append(
                {
                    "parent_exchange_order_id": observed_parent_id,
                    "actual_exchange_order_id": str(
                        raw.get("actualOrderId") or ""
                    ).strip(),
                    "client_order_id": str(
                        raw.get("clientAlgoId") or ""
                    ).strip(),
                    "status": str(raw.get("algoStatus") or "").lower(),
                    "symbol": str(raw.get("symbol") or ""),
                    "side": str(raw.get("side") or "").lower(),
                    "position_side": str(
                        raw.get("positionSide") or ""
                    ).upper(),
                    "order_type": str(raw.get("orderType") or "").upper(),
                    "qty": str(raw.get("quantity") or ""),
                    "actual_qty": str(raw.get("actualQty") or ""),
                    "trigger_price": str(raw.get("triggerPrice") or ""),
                    "trigger_time_ms": raw.get("triggerTime"),
                    "reduce_only": str(raw.get("reduceOnly")).lower()
                    in {"true", "1", "yes"},
                    "close_position": str(raw.get("closePosition")).lower()
                    in {"true", "1", "yes"},
                }
            )
        return rows

    async def find_order_by_client_id(
        self,
        request: ExchangeOrderLookupRequest,
        *,
        observed_at_ms: int,
    ) -> ExchangeOrderLookupResult:
        """Read one durable command through its required venue identity view.

        The returned status only means the selected view completed.  Transport,
        malformed-payload, and unsupported-command failures remain exceptions,
        so callers cannot confuse an incomplete view with authoritative absence.
        """

        import ccxt

        if not request.client_order_id or not request.gateway_symbol:
            raise InvalidOrderError(
                "client_order_id and symbol are required for order lookup",
                "F-011",
            )
        try:
            lookup_view = required_exchange_order_lookup_view(request)
        except ValueError as exc:
            raise InvalidOrderError(str(exc), "F-011") from exc
        identity_kind = (
            "clientAlgoId"
            if lookup_view is ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER
            else (
                "origClientOrderId"
                if self.exchange_name.lower() == "binance"
                else "clientOrderId"
            )
        )
        try:
            if lookup_view is ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER:
                raw = await self.rest_exchange.fapiPrivateGetAlgoOrder(
                    {"clientAlgoId": request.client_order_id}
                )
            else:
                params = (
                    {"origClientOrderId": request.client_order_id}
                    if self.exchange_name.lower() == "binance"
                    else {"clientOrderId": request.client_order_id}
                )
                raw = await self.rest_exchange.fetch_order(
                    None,
                    request.gateway_symbol,
                    params=params,
                )
        except ccxt.OrderNotFound:
            return ExchangeOrderLookupResult(
                status=ExchangeOrderLookupStatus.NOT_FOUND,
                lookup_view=lookup_view,
                identity_kind=identity_kind,
                observed_at_ms=observed_at_ms,
                client_order_id=request.client_order_id,
                gateway_symbol=request.gateway_symbol,
            )
        except ccxt.DDoSProtection as exc:
            raise RateLimitError(f"API 频率限制：{exc}", "C-010") from exc
        except ccxt.NetworkError as exc:
            raise ConnectionLostError(f"网络错误：{exc}", "C-001") from exc
        if not isinstance(raw, dict):
            raise ConnectionLostError(
                "Order lookup returned non-structured response",
                "C-002",
            )
        info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
        if lookup_view is ExchangeOrderLookupView.CONDITIONAL_ALGO_ORDER:
            exchange_order_id = self._required_lookup_value(
                raw,
                "algoId",
            )
            actual_client_id = self._required_lookup_value(
                raw,
                "clientAlgoId",
            )
            exchange_status = self._optional_lookup_value(raw, "algoStatus")
        else:
            exchange_order_id = self._optional_lookup_value(
                raw,
                "id",
                "orderId",
            )
            if exchange_order_id is None:
                exchange_order_id = self._required_lookup_value(info, "orderId")
            actual_client_id = self._optional_lookup_value(
                raw,
                "clientOrderId",
                "clientOrderid",
            )
            if actual_client_id is None:
                actual_client_id = self._required_lookup_value(
                    info,
                    "origClientOrderId",
                    "clientOrderId",
                    "clientOrderid",
                )
            exchange_status = self._optional_lookup_value(raw, "status")
        raw_symbol = self._optional_lookup_value(raw, "symbol")
        if raw_symbol is None:
            raw_symbol = self._required_lookup_value(info, "symbol")
        gateway_symbol = (
            request.gateway_symbol
            if self._lookup_symbols_match(raw_symbol, request.gateway_symbol)
            else raw_symbol
        )
        return ExchangeOrderLookupResult(
            status=ExchangeOrderLookupStatus.FOUND,
            lookup_view=lookup_view,
            identity_kind=identity_kind,
            observed_at_ms=observed_at_ms,
            exchange_order_id=exchange_order_id,
            client_order_id=actual_client_id,
            gateway_symbol=gateway_symbol,
            exchange_status=exchange_status,
        )

    @classmethod
    def _lookup_symbols_match(cls, raw_symbol: str, gateway_symbol: str) -> bool:
        raw_key = cls._normalize_symbol_key(raw_symbol)
        gateway_key = cls._normalize_symbol_key(gateway_symbol)
        if raw_key == gateway_key:
            return True
        # Binance native USD-M payloads omit the CCXT settle suffix, e.g.
        # ``ETHUSDT`` instead of ``ETH/USDT:USDT``.
        gateway_market_key = cls._normalize_symbol_key(
            gateway_symbol.split(":", maxsplit=1)[0]
        )
        return raw_key == gateway_market_key

    @staticmethod
    def _optional_lookup_value(
        raw: Dict[str, Any],
        *keys: str,
    ) -> Optional[str]:
        for key in keys:
            value = raw.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @classmethod
    def _required_lookup_value(
        cls,
        raw: Dict[str, Any],
        *keys: str,
    ) -> str:
        value = cls._optional_lookup_value(raw, *keys)
        if value is None:
            raise ConnectionLostError(
                "Order lookup response is missing required identity",
                "C-002",
            )
        return value

    async def _fetch_conditional_open_order_by_id(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:
        raw_orders = await self.fetch_all_open_orders(symbol)
        for raw_order in raw_orders:
            if self._raw_order_matches(
                raw_order,
                exchange_order_id=exchange_order_id,
                client_order_id=None,
                expected_symbol=symbol,
            ):
                return raw_order
        return None

    def _order_placement_result_from_raw_order(
        self,
        order: Dict[str, Any],
        *,
        exchange_order_id: str,
        symbol: str,
    ) -> OrderPlacementResult:
        info = order.get("info") or {}
        order_status = self._parse_order_status(str(order.get("status", "open")))
        amount_raw = (
            order.get("amount")
            or info.get("origQty")
            or info.get("quantity")
            or info.get("origQuantity")
            or 0
        )
        amount = Decimal(str(amount_raw)) if amount_raw else Decimal("0")
        filled_raw = order.get("filled") or info.get("executedQty") or info.get("actualQty")
        filled_qty = Decimal(str(filled_raw)) if filled_raw else None
        price_raw = order.get("price") or info.get("price")
        price = Decimal(str(price_raw)) if price_raw else None
        trigger_raw = (
            order.get("triggerPrice")
            or order.get("stopPrice")
            or info.get("triggerPrice")
            or info.get("stopPrice")
        )
        trigger_price = Decimal(str(trigger_raw)) if trigger_raw else None
        average_raw = order.get("average") or info.get("avgPrice")
        average_exec_price = Decimal(str(average_raw)) if average_raw else None
        reduce_raw = order.get("reduceOnly")
        if reduce_raw is None:
            reduce_raw = info.get("reduceOnly")
        reduce_only = str(reduce_raw).lower() in {"true", "1", "yes"}
        side = str(order.get("side") or info.get("side") or "buy").lower()
        order_type = (
            info.get("orderType")
            or info.get("type")
            or info.get("origType")
            or order.get("type")
            or "limit"
        )

        return OrderPlacementResult(
            order_id=exchange_order_id,
            exchange_order_id=str(
                order.get("id")
                or info.get("orderId")
                or info.get("algoId")
                or exchange_order_id
            ),
            symbol=symbol,
            order_type=self._parse_order_type(str(order_type)),
            direction=self._map_side_to_direction(side, reduce_only),
            side=side,
            amount=amount,
            price=price,
            trigger_price=trigger_price,
            filled_qty=filled_qty,
            average_exec_price=average_exec_price,
            reduce_only=reduce_only,
            status=order_status,
        )

    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        """
        获取盘口价格（用于市价单预估）

        Args:
            symbol: 币种对

        Returns:
            Decimal: 最新市场价格

        Raises:
            ConnectionLostError: 无法获取价格
        """
        import ccxt

        try:
            # 调用 CCXT fetch_ticker 方法
            ticker = await self.rest_exchange.fetch_ticker(symbol)

            # 获取最新成交价（优先使用 last，否则使用 close）
            price = ticker.get('last') or ticker.get('close') or ticker.get('bid') or ticker.get('ask')

            if price is None:
                raise ConnectionLostError(f"无法获取 {symbol} 的价格", "C-001")

            return Decimal(str(price))

        except ccxt.NetworkError as e:
            logger.error(f"网络错误，无法获取价格：{e}")
            raise ConnectionLostError(f"网络错误：{e}", "C-001")

        except Exception as e:
            logger.error(f"获取价格失败：{e}")
            raise

    async def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取交易对精度信息（P0-004：订单参数合理性检查）

        Args:
            symbol: 币种对

        Returns:
            Dict containing:
            - min_quantity: 最小交易量
            - quantity_precision: 数量精度（小数位数）
            - price_precision: 价格精度（小数位数）
            - min_notional: 最小名义价值（USDT）
            - step_size: 数量步长

        Raises:
            ValueError: 无法获取市场信息
        """
        try:
            # 确保市场数据已加载
            if not self.rest_exchange.markets:
                await self.rest_exchange.load_markets()

            # 获取交易对信息
            market = self.rest_exchange.market(symbol)

            if not market:
                raise ValueError(f"无法获取 {symbol} 的市场信息")

            # 提取精度信息
            limits = market.get('limits', {})
            precision = market.get('precision', {})

            min_quantity = Decimal(str(limits.get('amount', {}).get('min', 0)))
            quantity_precision = precision.get('amount', 6)
            price_precision = precision.get('price', 2)
            min_notional = Decimal(str(limits.get('cost', {}).get('min', 5)))

            # stepSize（数量步长）. Some ccxt Binance futures markets expose the
            # actionable amount step through precision.amount instead of
            # limits.amount.step.
            step_size = Decimal(str(limits.get('amount', {}).get('step', 0)))
            if step_size == Decimal("0"):
                step_size = Decimal(str(quantity_precision))

            return {
                'min_quantity': min_quantity,
                'quantity_precision': quantity_precision,
                'price_precision': price_precision,
                'min_notional': min_notional,
                'step_size': step_size,
            }

        except Exception as e:
            logger.error(f"获取市场精度信息失败：{e} (symbol={symbol})")
            raise ValueError(f"无法获取 {symbol} 的市场精度信息：{e}")

    def get_min_notional(self, symbol: str) -> Optional[Decimal]:
        """Return the exchange market min notional if already available.

        This is intentionally synchronous so local control/preflight endpoints
        can read loaded market metadata without creating a hidden network call.
        """
        try:
            markets = getattr(self.rest_exchange, "markets", None)
            if not markets:
                return None
            try:
                market = self.rest_exchange.market(symbol)
            except Exception:
                market = markets.get(symbol)
            return self._extract_market_min_notional(market)
        except Exception as exc:
            logger.warning(
                "Failed to extract min_notional from loaded market metadata: symbol=%s error=%s",
                symbol,
                exc,
            )
            return None

    @staticmethod
    def _extract_market_min_notional(market: Any) -> Optional[Decimal]:
        if not isinstance(market, dict):
            return None

        limits = market.get("limits")
        if isinstance(limits, dict):
            cost = limits.get("cost")
            if isinstance(cost, dict):
                value = cost.get("min")
                if value is not None:
                    return Decimal(str(value))

        value = market.get("min_notional") or market.get("minNotional")
        if value is not None:
            return Decimal(str(value))

        info = market.get("info")
        if isinstance(info, dict):
            filters = info.get("filters")
            if isinstance(filters, list):
                for item in filters:
                    if not isinstance(item, dict):
                        continue
                    filter_type = item.get("filterType")
                    if filter_type in {"MIN_NOTIONAL", "NOTIONAL"}:
                        value = item.get("notional") or item.get("minNotional")
                        if value is not None:
                            return Decimal(str(value))

        return None

    # ============================================================
    # Helper Methods
    # ============================================================

    def _map_order_type_to_ccxt(self, order_type: str) -> str:
        """
        映射订单类型到 CCXT 格式

        Args:
            order_type: 内部订单类型 ("market", "limit", "stop_market")

        Returns:
            CCXT 订单类型
        """
        type_mapping = {
            "market": "market",
            "limit": "limit",
            "stop_market": "STOP_MARKET",
        }
        return type_mapping.get(order_type.lower(), order_type.lower())

    def _should_omit_reduce_only_param(self, position_side: Optional[str]) -> bool:
        """Binance futures hedge mode rejects reduceOnly when positionSide is set."""
        return self.exchange_name.lower() == "binance" and bool(position_side)

    def _build_ccxt_order_params(
        self,
        *,
        order_type: str,
        trigger_price: Optional[Decimal],
        reduce_only: bool,
        position_side: Optional[str],
        client_order_id: Optional[str],
        time_in_force: Optional[str] = None,
        post_only: bool = False,
    ) -> CcxtOrderParamsBuildResult:
        """Build the only raw exchange-specific params sent to ccxt.create_order().

        Business code passes normalized intent fields such as ``position_side``
        and ``reduce_only``. Binance-specific keys such as ``positionSide`` and
        the hedge-mode reduceOnly omission are governed here.
        """

        params: Dict[str, Any] = {}
        exchange_reduce_only_param_sent = False
        exchange_reduce_only_omit_reason = None

        normalized_position_side = position_side.upper() if position_side else None
        if normalized_position_side is not None:
            if normalized_position_side not in {"LONG", "SHORT"}:
                raise InvalidOrderError(
                    f"Unsupported hedge position side: {position_side}",
                    "F-011",
                )
            if self.exchange_name.lower() != "binance":
                raise InvalidOrderError(
                    "position_side is only supported by the Binance hedge-mode ccxt adapter",
                    "F-011",
                )
            params["positionSide"] = normalized_position_side

        if reduce_only:
            if self._should_omit_reduce_only_param(normalized_position_side):
                exchange_reduce_only_omit_reason = "binance_hedge_mode_position_side"
            else:
                params["reduceOnly"] = True
                exchange_reduce_only_param_sent = True

        if order_type == "stop_market" and trigger_price is not None:
            params["stopPrice"] = str(trigger_price)
            params["triggerPrice"] = str(trigger_price)

        if time_in_force is not None:
            params["timeInForce"] = time_in_force
        if post_only:
            params["postOnly"] = True

        if client_order_id:
            params["clientOrderId"] = client_order_id

        return CcxtOrderParamsBuildResult(
            params=params,
            exchange_reduce_only_param_sent=exchange_reduce_only_param_sent,
            exchange_reduce_only_omit_reason=exchange_reduce_only_omit_reason,
        )

    def _map_side_to_direction(self, side: str, reduce_only: bool) -> "Direction":
        """
        映射 side 到 Direction 枚举

        Args:
            side: "buy" | "sell"
            reduce_only: 是否减仓

        Returns:
            Direction 枚举
        """
        from src.domain.models import Direction

        # 开仓单：buy=LONG, sell=SHORT
        # 平仓单：buy=SHORT(平空), sell=LONG(平多)
        if not reduce_only:
            return Direction.LONG if side == "buy" else Direction.SHORT
        else:
            # 平仓单：方向与原始持仓相反
            return Direction.SHORT if side == "buy" else Direction.LONG

    def _parse_order_status(self, ccxt_status: str) -> OrderStatus:
        """
        解析 CCXT 订单状态到内部 OrderStatus

        Args:
            ccxt_status: CCXT 返回的订单状态

        Returns:
            OrderStatus 枚举
        """
        status_mapping = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELED,
            'rejected': OrderStatus.REJECTED,
            'expired': OrderStatus.EXPIRED,
        }
        # 部分成交处理
        if ccxt_status == 'open':
            # 需要检查是否有已成交数量，这里简化处理
            return OrderStatus.OPEN
        return status_mapping.get(ccxt_status.lower(), OrderStatus.PENDING)

    def _parse_order_type(self, ccxt_type: str) -> OrderType:
        """
        解析 CCXT 订单类型到内部 OrderType

        Args:
            ccxt_type: CCXT 返回的订单类型

        Returns:
            OrderType 枚举
        """
        type_mapping = {
            'market': OrderType.MARKET,
            'limit': OrderType.LIMIT,
            'stop': OrderType.STOP_MARKET,
            'stop_market': OrderType.STOP_MARKET,
            'stop_limit': OrderType.STOP_LIMIT,
        }
        return type_mapping.get(ccxt_type.lower(), OrderType.LIMIT)

    async def _handle_order_update(self, raw_order: Dict[str, Any]) -> Optional[Order]:
        """
        处理订单更新

        G-002 修复核心：
        - 基于 filled_qty 推进判断
        - 避免同一毫秒多次 Partial Fill 导致重复处理

        Args:
            raw_order: CCXT 原始订单数据

        Returns:
            Order 对象，如果是重复更新则返回 None
        """
        import uuid

        try:
            self._remember_recent_order_update(raw_order)

            # 解析订单数据
            order_id = str(raw_order.get('id', uuid.uuid4()))
            symbol = raw_order.get('symbol', '')
            status = raw_order.get('status', 'open')
            order_type = raw_order.get('type', 'limit')
            side = raw_order.get('side', 'buy')

            # 解析数量和价格（使用 Decimal 精度）
            amount = Decimal(str(raw_order.get('amount', 0))) if raw_order.get('amount') else Decimal('0')
            filled_qty = Decimal(str(raw_order.get('filled', 0))) if raw_order.get('filled') else Decimal('0')
            remaining = Decimal(str(raw_order.get('remaining', 0))) if raw_order.get('remaining') else Decimal('0')
            price = Decimal(str(raw_order['price'])) if raw_order.get('price') else None
            average_exec_price = Decimal(str(raw_order['average'])) if raw_order.get('average') else None

            # 解析时间戳
            timestamp = raw_order.get('timestamp')
            if timestamp is None:
                timestamp = int(time.time() * 1000)
            elif isinstance(timestamp, float):
                timestamp = int(timestamp)

            # G-002 修复：基于 filled_qty 去重
            local_state = self._order_local_state.get(order_id)
            if local_state:
                local_filled_qty = local_state.filled_qty
                local_status = local_state.status

                # 如果成交量未增加且状态未变化，跳过重复推送
                if filled_qty <= local_filled_qty and status == local_status:
                    logger.debug(f"订单 {order_id} 重复更新：filled_qty={filled_qty}, status={status}")
                    return None

                # 如果成交量减少（异常情况），记录警告
                if filled_qty < local_filled_qty:
                    logger.warning(
                        f"订单 {order_id} filled_qty 异常减少："
                        f"{local_filled_qty} -> {filled_qty}"
                    )

            # 更新本地状态 (P0 修复：使用 OrderLocalState 类)
            self._order_local_state[order_id] = OrderLocalState(
                filled_qty=filled_qty,
                status=status,
                updated_at=timestamp,
            )

            # 解析订单状态
            order_status = self._parse_order_status_with_filled_qty(status, filled_qty, amount)

            # P1-3 修复：尝试从多个可能的字段提取 trigger_price
            # CCXT 在 info.triggerPrice 或 info.stopPrice 中返回触发价
            trigger_price_raw = (
                raw_order.get('info', {}).get('triggerPrice')
                or raw_order.get('info', {}).get('stopPrice')
                or raw_order.get('stopPrice')
                or raw_order.get('triggerPrice')
            )
            trigger_price = Decimal(str(trigger_price_raw)) if trigger_price_raw else None

            # 构建 Order 对象
            order = Order(
                id=order_id,
                signal_id=raw_order.get('clientOrderId', ''),  # 使用 clientOrderId 作为 signal_id
                exchange_order_id=order_id,
                symbol=symbol,
                direction=self._map_side_to_direction(side, raw_order.get('reduceOnly', False)),
                order_type=self._parse_order_type(order_type),
                order_role=OrderRole.ENTRY,  # 默认设为 ENTRY，具体角色由上层业务逻辑判断
                price=price,
                trigger_price=trigger_price,  # P1-3 修复：使用提取的 trigger_price
                requested_qty=amount,
                filled_qty=filled_qty,
                average_exec_price=average_exec_price,
                status=order_status,
                created_at=timestamp,
                updated_at=timestamp,
                reduce_only=raw_order.get('reduceOnly', False),
            )

            logger.info(
                f"订单更新：{order_id} {symbol} {order_status.value} "
                f"filled={filled_qty}/{amount} price={average_exec_price or price}"
            )

            return order

        except Exception as e:
            logger.error(
                "处理订单更新失败：order_id=%s, symbol=%s, error=%s",
                raw_order.get('id'),
                raw_order.get('symbol'),
                e,
                exc_info=True,
            )
            return None

    def _parse_order_status_with_filled_qty(
        self,
        ccxt_status: str,
        filled_qty: Decimal,
        amount: Decimal,
    ) -> OrderStatus:
        """
        解析 CCXT 订单状态，支持部分成交判断

        Args:
            ccxt_status: CCXT 返回的订单状态
            filled_qty: 已成交数量
            amount: 订单总数量

        Returns:
            OrderStatus 枚举
        """
        status_mapping = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELED,
            'rejected': OrderStatus.REJECTED,
            'expired': OrderStatus.EXPIRED,
        }

        # 首先检查标准状态
        base_status = status_mapping.get(ccxt_status.lower(), OrderStatus.PENDING)

        # 特殊处理：open 状态下检查是否有部分成交
        if ccxt_status.lower() == 'open':
            if filled_qty > 0 and filled_qty < amount:
                return OrderStatus.PARTIALLY_FILLED

        return base_status

    def clear_order_state(self, order_id: str) -> None:
        """
        清除订单本地状态（用于订单完成后清理内存）

        Args:
            order_id: 订单 ID
        """
        if order_id in self._order_local_state:
            del self._order_local_state[order_id]
            logger.debug(f"已清除订单状态：{order_id}")

    # ============================================================
    # P5-011: Global Order Callback Registration
    # ============================================================

    def set_global_order_callback(
        self,
        callback: Callable[[Order], Awaitable[None]],
    ) -> None:
        """
        设置全局订单更新回调（用于订单持久化）

        P5-011: 订单清理机制 - 架构决策 3.a
        启动时注册全局 WebSocket 回调，所有订单更新自动入库

        Args:
            callback: 异步回调函数，接收 Order 对象作为参数
        """
        self._global_order_callback = callback
        logger.info("全局订单更新回调已注册")

    async def _notify_global_order_callback(self, order: Order) -> None:
        """
        通知全局订单回调

        Args:
            order: 订单对象
        """
        if self._global_order_callback:
            try:
                await self._global_order_callback(order)
            except Exception as e:
                logger.error(f"全局订单回调执行失败：{e}")

    def _register_order_watch_exchange(self, ws_exchange: Any) -> None:
        """Track a dedicated order-watch WebSocket exchange for cleanup."""
        self._order_watch_exchanges.append(ws_exchange)

    def _unregister_order_watch_exchange(self, ws_exchange: Any) -> None:
        """Remove a dedicated order-watch WebSocket exchange from cleanup tracking."""
        try:
            self._order_watch_exchanges.remove(ws_exchange)
        except ValueError:
            pass

    async def watch_orders(
        self,
        symbol: str,
        callback: Callable[[Order], Awaitable[None]],
    ) -> None:
        """
        WebSocket 监听订单推送

        G-002 修复：基于 filled_qty 去重，而非时间戳
        避免同一毫秒多次 Partial Fill 导致重复处理

        P5-011 增强：在调用用户 callback 前，先调用全局回调（订单入库）

        Args:
            symbol: 币种对，如 "BTC/USDT:USDT"
            callback: 订单更新时的异步回调

        Raises:
            ConnectionLostError: WebSocket 重连超限
        """
        if ccxtpro is None:
            logger.warning("CCXT Pro 未安装，无法使用 WebSocket 订单推送")
            return

        self._order_ws_running = True
        self._order_ws_running_symbols[symbol] = True
        reconnect_count = 0

        # 创建专用的订单监听 WebSocket 实例，避免与 K-line WS 状态互相干扰
        order_ws_exchange = self._create_ws_exchange({
            'defaultType': 'swap',
        })
        self._register_order_watch_exchange(order_ws_exchange)

        # 加载市场数据
        await order_ws_exchange.load_markets()
        logger.info(f"WebSocket 订单监听已启动：{symbol}")

        try:
            while self._order_ws_running and self._order_ws_running_symbols.get(symbol, False):
                try:
                    # 使用 CCXT Pro watch_orders 方法
                    orders = await order_ws_exchange.watch_orders(symbol)

                    # 处理每个订单更新
                    for raw_order in orders:
                        order = await self._handle_order_update(raw_order)
                        if order:
                            # P5-011: 先调用全局回调（订单入库）
                            await self._notify_global_order_callback(order)

                            # P0-WS-Exception-Protection: 业务回调异常保护
                            try:
                                await callback(order)
                            except Exception as e:
                                # 记录高优错误日志
                                logger.error(
                                    f"⚠️ 订单回调失败，订单已标记为待恢复: "
                                    f"exchange_order_id={order.exchange_order_id}, "
                                    f"symbol={order.symbol}, status={order.status}, "
                                    f"error={e}"
                                )

                                # 标记为待恢复对象
                                self._pending_recovery_orders[order.exchange_order_id] = {
                                    "order": order,
                                    "error": str(e),
                                    "failed_at": int(time.time() * 1000),
                                }

                                # 继续处理后续订单事件（不中断消费循环）

                except asyncio.CancelledError:
                    logger.info(f"WebSocket 订单监听被取消：{symbol}")
                    break

                except Exception as e:
                    reconnect_count += 1
                    if reconnect_count >= self._max_reconnect_attempts:
                        raise ConnectionLostError(
                            f"WebSocket 重连失败超过 {self._max_reconnect_attempts} 次：{symbol}",
                            "C-001"
                        )

                    # 指数退避
                    delay = min(
                        self._initial_reconnect_delay * (2 ** (reconnect_count - 1)),
                        self._max_reconnect_delay
                    )
                    logger.warning(
                        f"WebSocket 重连中... {delay:.1f}s "
                        f"(尝试 {reconnect_count}/{self._max_reconnect_attempts})"
                    )
                    await asyncio.sleep(delay)

        finally:
            self._order_ws_running_symbols.pop(symbol, None)
            self._unregister_order_watch_exchange(order_ws_exchange)
            if not self._order_watch_exchanges:
                self._order_ws_running = False

            try:
                await order_ws_exchange.close()
            except Exception:
                pass

    def get_pending_recovery_orders(self) -> Dict[str, Dict[str, Any]]:
        """
        获取待恢复订单列表（P0-WS-Exception-Protection）

        Returns:
            Dict[str, Dict[str, Any]]: 待恢复订单字典，key 为 exchange_order_id
        """
        return self._pending_recovery_orders

    def clear_pending_recovery_order(self, exchange_order_id: str) -> None:
        """
        清除待恢复订单标记（P0-WS-Exception-Protection）

        Args:
            exchange_order_id: 交易所订单 ID
        """
        if exchange_order_id in self._pending_recovery_orders:
            del self._pending_recovery_orders[exchange_order_id]
            logger.info(f"已清除待恢复订单标记: {exchange_order_id}")
