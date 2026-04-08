"""
Exchange Gateway - All exchange communication (REST + WebSocket).
Handles historical data warmup, real-time K-line streaming, and asset polling.
"""
import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable
from decimal import Decimal

try:
    import ccxt.pro as ccxtpro
except ImportError:
    ccxtpro = None

import ccxt.async_support as ccxt_async

from src.domain.models import KlineData, AccountSnapshot, PositionInfo
from src.domain.exceptions import FatalStartupError, ConnectionLostError, DataQualityWarning
from src.infrastructure.logger import logger


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
        options: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Exchange Gateway.

        Args:
            exchange_name: Exchange name (ccxt id, e.g., 'binance')
            api_key: API key (read-only permission required)
            api_secret: API secret
            options: Additional exchange options
        """
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret

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

        # Asset snapshot cache
        self._account_snapshot: Optional[AccountSnapshot] = None
        self._asset_polling_task: Optional[asyncio.Task] = None
        self._polling_failures = 0
        self._max_polling_failures = 5

        # Candle closure tracking (instance variable, not class variable)
        self._candle_timestamps: Dict[str, int] = {}

    def _create_rest_exchange(self, options: Dict[str, Any]):
        """Create REST exchange instance"""
        config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # Force swap/futures mode
                'warnOnFetchOpenOrdersWithoutSymbol': False,  # Suppress CCXT warnings
            }
        }

        # Merge user-provided options
        if options:
            config['options'].update(options)

        # 仅支持实盘，禁用沙盒模式
        config['sandboxMode'] = False

        # Create exchange by name
        exchange_class = getattr(ccxt_async, self.exchange_name)
        return exchange_class(config)

    def _create_ws_exchange(self, options: Dict[str, Any]):
        """Create WebSocket exchange instance"""
        config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # Force swap/futures mode
                'warnOnFetchOpenOrdersWithoutSymbol': False,  # Suppress CCXT warnings
            }
        }

        # Merge user-provided options
        if options:
            config['options'].update(options)

        # 仅支持实盘，禁用沙盒模式
        config['sandboxMode'] = False

        # Create exchange by name
        exchange_class = getattr(ccxtpro, self.exchange_name)
        return exchange_class(config)

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
        if self.ws_exchange:
            try:
                await self.ws_exchange.close()
            except Exception:
                pass

        # Close REST
        try:
            await self.rest_exchange.close()
        except Exception:
            pass

        logger.info("Exchange connections closed")

    # ============================================================
    # REST API - Historical Data Warmup
    # ============================================================
    async def fetch_historical_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> List[KlineData]:
        """
        Fetch historical K-line data via REST API.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT:USDT")
            timeframe: Timeframe (e.g., "1h", "4h")
            limit: Number of candles to fetch (default: 100)

        Returns:
            List of KlineData objects
        """
        try:
            # Fetch OHLCV data
            ohlcv_data = await self.rest_exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )

            # Convert to KlineData models
            result = []
            for candle in ohlcv_data:
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
        raw_info: Optional[Dict] = None  # ✅ 新增参数：原始交易所数据（包含 x 字段）
    ) -> Optional[KlineData]:
        """
        Parse OHLCV candle to KlineData model.

        Args:
            candle: [timestamp, open, high, low, close, volume]
            symbol: Trading symbol
            timeframe: Timeframe
            raw_info: 交易所原始数据（包含 x 字段）

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

            # ✅ 新增：使用 x 字段判断收盘状态（CCXT Pro 第 7 个元素）
            if raw_info and 'x' in raw_info:
                is_closed = bool(raw_info['x'])
            else:
                is_closed = True  # 默认值（REST API 或无 x 字段时）

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
                info=raw_info,  # ✅ 新增：传递原始数据
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
                    if not ohlcv or len(ohlcv) < 2:
                        continue

                    # Check if candle is closed (completed)
                    # In CCXT, we need to track previous timestamp to detect closure
                    # Returns the closed candle data if detected
                    closed_kline = self._get_closed_candle(ohlcv, symbol, timeframe)
                    if closed_kline:
                        await callback(closed_kline)

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

    def _get_closed_candle(self, ohlcv: List[Any], symbol: str, timeframe: str) -> Optional[KlineData]:
        """
        Detect candle closure and return the closed candle data.

        Priority logic:
        1. Check CCXT Pro 'x' field (ohlcv[-1][6]) - if true, candle just closed
        2. If 'x' is false, skip (candle still forming)
        3. If 'x' field missing, fallback to timestamp change detection

        Args:
            ohlcv: Array of OHLCV data from WebSocket [timestamp, open, high, low, close, volume, x?]
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            KlineData of the closed candle if detected, None otherwise
        """
        if len(ohlcv) < 2:
            return None

        key = f"{symbol}:{timeframe}"
        latest_candle = ohlcv[-1]

        # ✅ 优先检查 CCXT Pro 的 'x' 字段（第 7 个元素，索引 6）
        # 'x' = true 表示该 K 线已收盘
        if len(latest_candle) >= 7:
            x_field = latest_candle[6]
            if x_field is True:
                # ✅ x=true，K 线已收盘，返回 ohlcv[-1]
                logger.debug(
                    f"[X_FIELD] {symbol} {timeframe}: candle closed (x=true) "
                    f"ts={latest_candle[0]}"
                )
                return self._parse_ohlcv(latest_candle, symbol, timeframe, raw_info={'x': True})
            elif x_field is False:
                # ❌ x=false，K 线还未收盘，跳过
                logger.debug(
                    f"[X_FIELD] {symbol} {timeframe}: candle still forming (x=false) "
                    f"ts={latest_candle[0]}"
                )
                return None
            # 如果 x 字段存在但不是明确的 True/False，继续降级逻辑

        # ✅ 降级到时间戳推断逻辑（旧方法）
        current_ts = latest_candle[0]  # Latest candle timestamp

        if key in self._candle_timestamps:
            if current_ts != self._candle_timestamps[key]:
                # 时间戳变化 - 前一根 K 线已收盘
                self._candle_timestamps[key] = current_ts

                # 返回 ohlcv[-2]（刚收盘的 K 线）
                closed_candle = ohlcv[-2]
                logger.debug(
                    f"[TIMESTAMP_FALLBACK] {symbol} {timeframe}: "
                    f"closed candle ts={closed_candle[0]}"
                )
                return self._parse_ohlcv(closed_candle, symbol, timeframe, raw_info=None)
        else:
            # 第一次见到这个 symbol/timeframe
            self._candle_timestamps[key] = current_ts

        return None

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
