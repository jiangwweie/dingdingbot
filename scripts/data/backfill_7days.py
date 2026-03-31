#!/usr/bin/env python3
"""
历史信号回测脚本 - 监测过去 7 天的历史信号并入库保存

用法:
    python3 scripts/backfill_7days.py

    或指定天数:
    python3 scripts/backfill_7days.py --days 7

    或指定币对和时间周期:
    python3 scripts/backfill_7days.py --symbols BTC/USDT:USDT ETH/USDT:USDT --timeframes 1h 4h
"""
import asyncio
import argparse
import time
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, '/Users/jiangwei/Documents/final')

import ccxt.async_support as ccxt_async

from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.strategy_engine import StrategyEngine, StrategyConfig, PinbarConfig, SignalAttempt
from src.domain.risk_calculator import RiskCalculator, RiskConfig
from src.domain.models import KlineData, AccountSnapshot, Direction, TrendDirection, MtfStatus
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.logger import logger


class HistoricalBackfiller:
    """历史信号回填器"""

    def __init__(
        self,
        days: int = 7,
        symbols: List[str] = None,
        timeframes: List[str] = None,
        exchange_name: str = "binance",
        testnet: bool = False,
    ):
        """
        初始化回填器

        Args:
            days: 回测天数
            symbols: 币对列表
            timeframes: 时间周期列表
            exchange_name: 交易所名称
            testnet: 是否使用测试网
        """
        self.days = days
        self.symbols = symbols or []
        self.timeframes = timeframes or []
        self.exchange_name = exchange_name
        self.testnet = testnet

        # 交易所
        self.exchange: Optional[ExchangeGateway] = None

        # 策略引擎
        self.strategy_engine: Optional[StrategyEngine] = None

        # 风险计算器
        self.risk_calculator: Optional[RiskCalculator] = None

        # 信号仓库
        self.repository: Optional[SignalRepository] = None

        # 统计
        self.stats = {
            "total_klines": 0,
            "signals_fired": 0,
            "signals_saved": 0,
            "errors": 0,
        }

    async def initialize(self):
        """初始化所有组件"""
        logger.info("=" * 60)
        logger.info("历史信号回测脚本 - 初始化中")
        logger.info("=" * 60)

        # 1. 加载配置
        logger.info("加载配置...")
        config_manager = load_all_configs()

        # 使用配置的币对和时间周期（如果未指定）
        if not self.symbols:
            self.symbols = config_manager.merged_symbols
        if not self.timeframes:
            self.timeframes = config_manager.user_config.timeframes

        logger.info(f"币对：{self.symbols}")
        logger.info(f"时间周期：{self.timeframes}")
        logger.info(f"回测天数：{self.days}")

        # 2. 初始化交易所（直接使用 ccxt，不经过 ExchangeGateway，不使用 API Key）
        # 注意：历史 K 线是公开数据，不需要 API Key
        logger.info("初始化交易所连接...")
        options = {
            'defaultType': 'swap',
            'recvWindow': 30000,
            'timeout': 60000,  # 增加超时时间
        }
        if self.testnet:
            options['sandboxMode'] = True

        # 不使用 API Key 初始化（避免权限问题）
        self.rest_exchange = getattr(ccxt_async, self.exchange_name)({
            'enableRateLimit': True,
            'options': options,
        })

        # 只加载 markets，不加载需要权限的数据
        await self.rest_exchange.load_markets()
        logger.info("交易所连接成功")

        # 3. 初始化策略引擎
        logger.info("初始化策略引擎...")
        core = config_manager.core_config
        user = config_manager.user_config

        pinbar_config = PinbarConfig(
            min_wick_ratio=core.pinbar_defaults.min_wick_ratio,
            max_body_ratio=core.pinbar_defaults.max_body_ratio,
            body_position_tolerance=core.pinbar_defaults.body_position_tolerance,
        )

        strategy_config = StrategyConfig(
            pinbar_config=pinbar_config,
            ema_period=core.ema.period,
            trend_filter_enabled=user.strategy.trend_filter_enabled,
            mtf_validation_enabled=user.strategy.mtf_validation_enabled,
        )

        # 手动创建策略引擎并注入 EngulfingStrategy
        self.strategy_engine = StrategyEngine.__new__(StrategyEngine)
        self.strategy_engine.config = strategy_config
        self.strategy_engine._pinbar_strategy = type('PinbarStrategy', (), {})()  # 占位
        from src.domain.strategy_engine import PinbarStrategy, EmaTrendFilter, MtfFilter, StrategyRunner
        self.strategy_engine._pinbar_strategy = PinbarStrategy(pinbar_config)
        self.strategy_engine._engulfing_strategy = EngulfingStrategy()
        self.strategy_engine._ema_filter = EmaTrendFilter(
            period=strategy_config.ema_period,
            enabled=strategy_config.trend_filter_enabled
        )
        self.strategy_engine._mtf_filter = MtfFilter(
            enabled=strategy_config.mtf_validation_enabled
        )
        self.strategy_engine._runner = StrategyRunner(
            strategies=[self.strategy_engine._pinbar_strategy, self.strategy_engine._engulfing_strategy],
            filters=[self.strategy_engine._ema_filter],
            mtf_filter=self.strategy_engine._mtf_filter,
        )

        logger.info("策略引擎初始化成功 (Pinbar + Engulfing)")

        # 4. 初始化风险计算器
        risk_config = RiskConfig(
            max_loss_percent=user.risk.max_loss_percent,
            max_leverage=user.risk.max_leverage,
        )
        self.risk_calculator = RiskCalculator(risk_config)
        logger.info("风险计算器初始化成功")

        # 5. 初始化信号仓库
        self.repository = SignalRepository()
        await self.repository.initialize()
        logger.info("信号数据库初始化成功")

        logger.info("=" * 60)
        logger.info("初始化完成")
        logger.info("=" * 60)

    async def close(self):
        """关闭资源"""
        if self.rest_exchange:
            await self.rest_exchange.close()
        if self.repository:
            await self.repository.close()
        logger.info("资源已释放")

    async def backfill(self):
        """执行回测"""
        start_time = datetime.now(timezone.utc) - timedelta(days=self.days)
        since_timestamp = int(start_time.timestamp() * 1000)

        logger.info(f"开始回测，起始时间：{start_time.isoformat()}")
        logger.info(f"起始时间戳：{since_timestamp}")

        total_to_process = len(self.symbols) * len(self.timeframes)
        processed = 0

        for symbol in self.symbols:
            for timeframe in self.timeframes:
                processed += 1
                logger.info(f"[{processed}/{total_to_process}] 处理：{symbol} {timeframe}")

                try:
                    await self._process_symbol_timeframe(symbol, timeframe, since_timestamp)
                except Exception as e:
                    self.stats["errors"] += 1
                    logger.error(f"处理 {symbol} {timeframe} 失败：{e}", exc_info=True)

        logger.info("=" * 60)
        logger.info("回测完成")
        logger.info(f"统计:")
        logger.info(f"  总 K 线数：{self.stats['total_klines']}")
        logger.info(f"  触发信号：{self.stats['signals_fired']}")
        logger.info(f"  保存信号：{self.stats['signals_saved']}")
        logger.info(f"  错误数：{self.stats['errors']}")
        logger.info("=" * 60)

    async def _process_symbol_timeframe(
        self,
        symbol: str,
        timeframe: str,
        since_timestamp: int,
    ):
        """
        处理单个币对和时间周期

        Args:
            symbol: 币对
            timeframe: 时间周期
            since_timestamp: 起始时间戳
        """
        # 1. 获取历史 K 线数据
        klines = await self._fetch_historical_klines(symbol, timeframe, since_timestamp)

        if not klines:
            logger.warning(f"未获取到 K 线数据：{symbol} {timeframe}")
            return

        logger.debug(f"获取到 {len(klines)} 条 K 线")
        self.stats["total_klines"] += len(klines)

        # 2. 初始化 EMA 缓存
        higher_tf_trends: Dict[str, TrendDirection] = {}

        # 3. 逐条处理 K 线
        kline_history: List[KlineData] = []
        saved_signal_timestamps = set()  # 防止重复保存

        for i, kline in enumerate(klines):
            # 更新 EMA 状态
            self.strategy_engine._ema_filter.update(kline, kline.symbol, kline.timeframe)
            current_trend = self.strategy_engine._ema_filter.get_trend(
                kline, kline.symbol, kline.timeframe
            )
            if current_trend:
                higher_tf_trends[timeframe] = current_trend

            # 运行策略
            attempts = self.strategy_engine._runner.run_all(
                kline=kline,
                higher_tf_trends=higher_tf_trends,
                current_trend=current_trend,
                kline_history=kline_history.copy(),
            )

            # 处理触发的信号
            for attempt in attempts:
                if attempt.final_result == "SIGNAL_FIRED" and attempt.pattern:
                    self.stats["signals_fired"] += 1

                    # 去重：同一策略在同一 K 线不重复保存
                    dedup_key = f"{kline.timestamp}:{attempt.strategy_name}:{attempt.pattern.direction.value}"
                    if dedup_key in saved_signal_timestamps:
                        continue

                    # 计算完整信号
                    account = AccountSnapshot(
                        total_balance=Decimal("10000"),
                        available_balance=Decimal("10000"),
                        unrealized_pnl=Decimal("0"),
                        positions=[],
                        timestamp=kline.timestamp,
                    )

                    signal = self.risk_calculator.calculate_signal_result(
                        kline=kline,
                        account=account,
                        direction=attempt.pattern.direction,
                        ema_trend=current_trend or TrendDirection.BULLISH,
                        mtf_status=MtfStatus.CONFIRMED,
                        kline_timestamp=kline.timestamp,
                        strategy_name=attempt.strategy_name,
                        score=attempt.pattern.score,
                    )

                    # 保存信号
                    try:
                        await self.repository.save_signal(signal)
                        self.stats["signals_saved"] += 1
                        saved_signal_timestamps.add(dedup_key)
                        logger.debug(
                            f"保存信号：{symbol} {timeframe} {attempt.pattern.direction.value} "
                            f"[{attempt.strategy_name}] @ {kline.timestamp}"
                        )
                    except Exception as e:
                        logger.error(f"保存信号失败：{e}")

            # 保存 K 线历史（用于 Engulfing 策略）
            kline_history.append(kline)
            if len(kline_history) > 200:
                kline_history = kline_history[-200:]

            # 每 100 条打印进度
            if (i + 1) % 100 == 0:
                logger.debug(f"进度：{i + 1}/{len(klines)}")

        logger.info(f"完成：{symbol} {timeframe} - {len(klines)} 条 K 线")

    async def _fetch_historical_klines(
        self,
        symbol: str,
        timeframe: str,
        since_timestamp: int,
    ) -> List[KlineData]:
        """
        获取历史 K 线数据

        Args:
            symbol: 币对
            timeframe: 时间周期
            since_timestamp: 起始时间戳

        Returns:
            KlineData 列表
        """
        all_klines = []
        current_since = since_timestamp
        limit = 1000  # Binance 每次最多 1000 条

        while True:
            try:
                klines = await self.rest_exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_since,
                    limit=limit,
                )

                if not klines:
                    break

                for candle in klines:
                    kline = self._parse_ohlcv(candle, symbol, timeframe)
                    if kline:
                        all_klines.append(kline)

                # 如果返回数量不足 limit，说明已经是最新数据
                if len(klines) < limit:
                    break

                # 更新 since 为最后一条 K 线的时间戳 + 1
                current_since = klines[-1][0] + 1

                # 速率限制
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"获取 K 线失败 {symbol} {timeframe}: {e}")
                break

        return all_klines

    def _parse_ohlcv(self, candle: List, symbol: str, timeframe: str) -> Optional[KlineData]:
        """Parse OHLCV candle to KlineData"""
        try:
            timestamp = int(candle[0])
            open_price = Decimal(str(candle[1]))
            high_price = Decimal(str(candle[2]))
            low_price = Decimal(str(candle[3]))
            close_price = Decimal(str(candle[4]))
            volume = Decimal(str(candle[5]))

            # 基本验证
            if high_price < low_price:
                return None
            if high_price < open_price or high_price < close_price:
                return None
            if low_price > open_price or low_price > close_price:
                return None

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
        except Exception as e:
            logger.debug(f"解析 K 线失败：{e}")
            return None


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="历史信号回测脚本")
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="回测天数 (默认：7)"
    )
    parser.add_argument(
        "--symbols", "-s",
        nargs="+",
        help="币对列表 (默认：使用配置文件)"
    )
    parser.add_argument(
        "--timeframes", "-t",
        nargs="+",
        help="时间周期列表 (默认：使用配置文件)"
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="使用测试网"
    )

    args = parser.parse_args()

    backfiller = HistoricalBackfiller(
        days=args.days,
        symbols=args.symbols,
        timeframes=args.timeframes,
        testnet=args.testnet,
    )

    try:
        await backfiller.initialize()
        await backfiller.backfill()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"错误：{e}", exc_info=True)
        sys.exit(1)
    finally:
        await backfiller.close()


if __name__ == "__main__":
    asyncio.run(main())
