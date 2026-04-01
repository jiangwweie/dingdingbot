"""
Exchange Gateway - All exchange communication (REST + WebSocket).
Handles historical data warmup, real-time K-line streaming, and asset polling.
"""
import asyncio
import time
from typing import List, Dict, Optional, Callable, Awaitable, Any
from decimal import Decimal

try:
    import ccxt.pro as ccxtpro
except ImportError:
    ccxtpro = None

import ccxt.async_support as ccxt_async

from pydantic import BaseModel

from src.domain.models import KlineData, AccountSnapshot, PositionInfo, OrderPlacementResult, OrderCancelResult, OrderStatus, OrderType, Order, OrderRole
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

        # P5-011: Global order update callback (for order persistence)
        self._global_order_callback: Optional[Callable[[Order], Awaitable[None]]] = None

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

    def _parse_ohlcv(self, candle: List[Any], symbol: str, timeframe: str) -> Optional[KlineData]:
        """
        Parse OHLCV candle to KlineData model.

        Args:
            candle: [timestamp, open, high, low, close, volume]
            symbol: Trading symbol
            timeframe: Timeframe

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

            return KlineData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                is_closed=True,
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
                    if not ohlcv:
                        continue

                    # Get last candle (most recent)
                    candle = ohlcv[-1]
                    kline = self._parse_ohlcv(candle, symbol, timeframe)

                    if not kline:
                        continue

                    # Check if candle is closed (completed)
                    # In CCXT, we need to track previous timestamp to detect closure
                    if self._is_candle_closed(kline, symbol, timeframe):
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
                position = PositionInfo(
                    symbol=pos['symbol'],
                    side=pos['side'] if pos.get('side') else 'none',
                    size=Decimal(str(pos['contracts'])),
                    entry_price=Decimal(str(pos['entryPrice'])) if pos.get('entryPrice') else Decimal('0'),
                    unrealized_pnl=Decimal(str(pos['unrealizedPnl'])) if pos.get('unrealizedPnl') else Decimal('0'),
                    leverage=int(leverage_val) if leverage_val is not None else 1,
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

    # ============================================================
    # Phase 5: Order Management APIs
    # ============================================================

    async def place_order(
        self,
        symbol: str,
        order_type: str,           # "market", "limit", "stop_market"
        side: str,                 # "buy" (开多/平空), "sell" (开空/平多)
        amount: Decimal,           # 数量
        price: Optional[Decimal] = None,      # 限价单价格
        trigger_price: Optional[Decimal] = None,  # 条件单触发价
        reduce_only: bool = False,  # 仅减仓（平仓单必须设置）
        client_order_id: Optional[str] = None,  # 客户端订单 ID
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
            client_order_id: 客户端订单 ID（可选）

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

        try:
            # 映射订单类型到 CCXT 格式
            ccxt_type = self._map_order_type_to_ccxt(order_type)

            # 构建 CCXT 下单参数
            params = {
                'reduceOnly': reduce_only,
            }

            # 止损单需要 triggerPrice 参数
            if order_type == "stop_market" and trigger_price is not None:
                params['triggerPrice'] = str(trigger_price)
                # CCXT 要求 stop 订单必须有 price 参数，即使是 stop_market
                # 使用 trigger_price 作为 price 传递
                if price is None:
                    price = trigger_price

            if client_order_id:
                params['clientOrderId'] = client_order_id

            # 调用 CCXT create_order 方法
            # P0 修复：使用 str() 而非 float() 避免精度污染 (CCXT 支持字符串输入)
            order = await self.rest_exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=side,
                amount=str(amount),
                price=str(price) if price is not None else None,
                params=params,
            )

            # 解析订单响应
            order_status = self._parse_order_status(order.get('status', 'open'))

            return OrderPlacementResult(
                order_id=system_order_id,
                exchange_order_id=order.get('id'),
                symbol=symbol,
                order_type=OrderType(order_type.upper()),
                direction=self._map_side_to_direction(side, reduce_only),
                side=side,
                amount=amount,
                price=price,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                client_order_id=client_order_id,
                status=order_status,
            )

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
            return OrderPlacementResult(
                order_id=system_order_id,
                symbol=symbol,
                order_type=OrderType(order_type.upper()),
                direction=self._map_side_to_direction(side, reduce_only),
                side=side,
                amount=amount,
                price=price,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                client_order_id=client_order_id,
                error_code="F-011",
                error_message=f"下单失败：{str(e)}",
            )

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
            order_status = self._parse_order_status(order.get('status', 'canceled'))

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

            # 解析订单状态
            order_status = self._parse_order_status(order.get('status', 'open'))

            # 解析订单数据
            amount = Decimal(str(order.get('amount', 0))) if order.get('amount') else Decimal('0')
            price = Decimal(str(order['price'])) if order.get('price') else None
            average_exec_price = Decimal(str(order['average'])) if order.get('average') else None

            return OrderPlacementResult(
                order_id=exchange_order_id,
                exchange_order_id=order.get('id'),
                symbol=symbol,
                order_type=self._parse_order_type(order.get('type', 'limit')),
                direction=self._map_side_to_direction(order.get('side', 'buy'), False),
                side=order.get('side', 'buy'),
                amount=amount,
                price=price,
                reduce_only=order.get('reduceOnly', False),
                status=order_status,
            )

        except ccxt.OrderNotFound as e:
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

            # stepSize（数量步长）
            step_size = Decimal(str(limits.get('amount', {}).get('step', 0)))

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
            "stop_market": "stop",  # CCXT 使用 "stop" 表示条件单
        }
        return type_mapping.get(order_type.lower(), order_type.lower())

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

    # ============================================================
    # Phase 5: WebSocket Order Push Monitoring (G-002)
    # ============================================================

    async def watch_orders(
        self,
        symbol: str,
        callback: Callable[[Order], Awaitable[None]],
    ) -> None:
        """
        WebSocket 监听订单推送

        G-002 修复：基于 filled_qty 去重，而非时间戳
        避免同一毫秒多次 Partial Fill 导致重复处理

        Args:
            symbol: 币种对，如 "BTC/USDT:USDT"
            callback: 订单更新时的异步回调

        Raises:
            ConnectionLostError: WebSocket 重连超限
        """
        if ccxtpro is None:
            logger.warning("CCXT Pro 未安装，无法使用 WebSocket 订单推送")
            return

        self._ws_running = True
        reconnect_count = 0

        # 创建 WebSocket 交换实例
        self.ws_exchange = self._create_ws_exchange({
            'defaultType': 'swap',
        })

        # 加载市场数据
        await self.ws_exchange.load_markets()
        logger.info(f"WebSocket 订单监听已启动：{symbol}")

        try:
            while self._ws_running:
                try:
                    # 使用 CCXT Pro watch_orders 方法
                    orders = await self.ws_exchange.watch_orders(symbol)

                    # 处理每个订单更新
                    for raw_order in orders:
                        order = await self._handle_order_update(raw_order)
                        if order:
                            await callback(order)

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
            self._ws_running = False
            if self.ws_exchange:
                await self.ws_exchange.close()

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
            logger.error(f"处理订单更新失败：{e}")
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

        self._ws_running = True
        reconnect_count = 0

        # 创建 WebSocket 交换实例
        self.ws_exchange = self._create_ws_exchange({
            'defaultType': 'swap',
        })

        # 加载市场数据
        await self.ws_exchange.load_markets()
        logger.info(f"WebSocket 订单监听已启动：{symbol}")

        try:
            while self._ws_running:
                try:
                    # 使用 CCXT Pro watch_orders 方法
                    orders = await self.ws_exchange.watch_orders(symbol)

                    # 处理每个订单更新
                    for raw_order in orders:
                        order = await self._handle_order_update(raw_order)
                        if order:
                            # P5-011: 先调用全局回调（订单入库）
                            await self._notify_global_order_callback(order)
                            # 再调用业务回调
                            await callback(order)

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
            self._ws_running = False
            if self.ws_exchange:
                await self.ws_exchange.close()
