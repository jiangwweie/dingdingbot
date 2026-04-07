"""
Provider 层测试 Fixture - Mock Provider 实现

本模块提供测试 Provider 层所需的 Mock Provider 实现。

包含:
- MockConfigProvider: 通用 Mock Provider(实现 Protocol 接口)
- FaultyConfigProvider: 故障注入 Provider(模拟异常)
- SlowConfigProvider: 慢速 Provider(模拟延迟)
- MockClock: 时钟 Mock(控制 TTL 过期)

设计参考：docs/reviews/p1_5_provider_design_qa_review.md#61-fixture-provider-实现
"""

import asyncio
from typing import Any, Optional, Dict, Callable
from datetime import datetime, timedelta


class MockConfigProvider:
    """
    通用 Mock Provider - 用于测试 ProviderRegistry 和 ConfigManager

    特性:
    - 实现 ConfigProvider Protocol 接口
    - 可追踪调用次数
    - 支持初始数据注入
    - 可配置缓存 TTL

    使用场景:
    - 测试 ProviderRegistry 注册/注销逻辑
    - 测试 ConfigManager 委托逻辑
    - 验证调用次数和状态
    """

    def __init__(self, initial_data: Optional[Dict[str, Any]] = None, cache_ttl: int = 300):
        """
        Args:
            initial_data: 初始测试数据
            cache_ttl: 缓存 TTL(秒)
        """
        self._data = initial_data or {}
        self._cache_ttl = cache_ttl
        self.get_call_count = 0
        self.update_call_count = 0
        self.refresh_call_count = 0

    async def get(self, key: Optional[str] = None) -> Any:
        """获取配置数据，追踪调用次数"""
        self.get_call_count += 1
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: Any) -> None:
        """更新配置数据，追踪调用次数"""
        self.update_call_count += 1
        self._data[key] = value

    async def refresh(self) -> None:
        """刷新缓存，追踪调用次数"""
        self.refresh_call_count += 1
        # 模拟刷新逻辑：重置调用计数
        self.get_call_count = 0
        self.update_call_count = 0

    @property
    def cache_ttl(self) -> int:
        """返回缓存 TTL"""
        return self._cache_ttl

    def set_data(self, key: str, value: Any) -> None:
        """测试辅助方法：设置数据"""
        self._data[key] = value

    def clear_data(self) -> None:
        """测试辅助方法：清空数据"""
        self._data.clear()


class FaultyConfigProvider:
    """
    故障注入 Provider - 用于测试异常处理

    特性:
    - 可配置在 get/update 时抛出异常
    - 模拟各种故障场景

    使用场景:
    - 测试 Provider 异常传播
    - 测试错误处理逻辑
    - 测试降级策略
    """

    def __init__(
        self,
        raise_on_get: bool = False,
        raise_on_update: bool = False,
        raise_on_refresh: bool = False,
        error_message: str = "Simulated error"
    ):
        """
        Args:
            raise_on_get: get() 方法是否抛出异常
            raise_on_update: update() 方法是否抛出异常
            raise_on_refresh: refresh() 方法是否抛出异常
            error_message: 异常消息
        """
        self.raise_on_get = raise_on_get
        self.raise_on_update = raise_on_update
        self.raise_on_refresh = raise_on_refresh
        self.error_message = error_message
        self._data: Dict[str, Any] = {}

    async def get(self, key: Optional[str] = None) -> Any:
        """获取配置，可选择性地抛出异常"""
        if self.raise_on_get:
            raise RuntimeError(self.error_message)
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: Any) -> None:
        """更新配置，可选择性地抛出异常"""
        if self.raise_on_update:
            raise RuntimeError(self.error_message)
        self._data[key] = value

    async def refresh(self) -> None:
        """刷新，可选择性地抛出异常"""
        if self.raise_on_refresh:
            raise RuntimeError(self.error_message)

    @property
    def cache_ttl(self) -> int:
        return 300


class SlowConfigProvider:
    """
    慢速 Provider - 用于测试超时/并发场景

    特性:
    - 模拟网络延迟
    - 可配置延迟时间

    使用场景:
    - 测试超时处理
    - 测试并发场景下的性能
    - 测试异步队列缓冲
    """

    def __init__(self, delay_seconds: float = 0.1, initial_data: Optional[Dict[str, Any]] = None):
        """
        Args:
            delay_seconds: 模拟延迟秒数
            initial_data: 初始数据
        """
        self.delay_seconds = delay_seconds
        self._data = initial_data or {}

    async def get(self, key: Optional[str] = None) -> Any:
        """获取配置，模拟延迟"""
        await asyncio.sleep(self.delay_seconds)
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: Any) -> None:
        """更新配置，模拟延迟"""
        await asyncio.sleep(self.delay_seconds)
        self._data[key] = value

    async def refresh(self) -> None:
        """刷新，模拟延迟"""
        await asyncio.sleep(self.delay_seconds)

    @property
    def cache_ttl(self) -> int:
        return 300


class MockClock:
    """
    模拟时钟 - 用于测试 CachedProvider 的 TTL 过期逻辑

    设计参考：docs/arch/P1-5-provider-registration-design.md#23-缓存策略
    QA 审查修复：P1 风险 - 时钟抽象注入

    特性:
    - 可固定时间
    - 可推进时间 (模拟 TTL 过期)
    - 实现 ClockProtocol 接口

    使用场景:
    - 测试 TTL 缓存过期
    - 测试时间相关的边界条件
    - 避免真实等待

    示例:
        # 固定在 10:00:00
        mock_clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = TestProvider(clock=mock_clock)

        # 设置缓存
        provider._set_cached('key', 'value')

        # 推进 5 分钟，缓存应有效
        mock_clock.advance(300)
        assert provider._get_cached('key') == 'value'

        # 再推进 1 分钟，缓存应过期
        mock_clock.advance(61)
        assert provider._get_cached('key') is None
    """

    def __init__(self, fixed_time: Optional[datetime] = None):
        """
        Args:
            fixed_time: 固定的模拟时间，None 表示使用当前时间
        """
        self._fixed_time = fixed_time or datetime.now()

    def now(self) -> datetime:
        """返回当前时间"""
        return self._fixed_time

    def advance(self, seconds: int) -> None:
        """
        推进时间 (用于测试 TTL 过期)

        Args:
            seconds: 推进的秒数
        """
        self._fixed_time += timedelta(seconds=seconds)

    def set_time(self, new_time: datetime) -> None:
        """
        设置时间

        Args:
            new_time: 新的时间点
        """
        self._fixed_time = new_time


# ============================================================================
# Pytest Fixtures
# ============================================================================

import pytest


@pytest.fixture
def mock_core_provider() -> MockConfigProvider:
    """
    核心配置 Mock Provider

    Returns:
        包含核心配置数据的 Mock Provider
    """
    return MockConfigProvider({
        'core_symbols': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT'],
        'core_timeframes': ['15m', '1h', '4h', '1d'],
        'exchange': 'binance',
        'testnet': True,
    })


@pytest.fixture
def mock_user_provider() -> MockConfigProvider:
    """
    用户配置 Mock Provider

    Returns:
        包含用户配置数据的 Mock Provider
    """
    return MockConfigProvider({
        'api_key': 'test_api_key_123456',
        'api_secret': 'test_api_secret_789012',
        'testnet': True,
        'notification_webhook': 'https://example.com/webhook',
    })


@pytest.fixture
def mock_risk_provider() -> MockConfigProvider:
    """
    风控配置 Mock Provider

    Returns:
        包含风控配置数据的 Mock Provider
    """
    from decimal import Decimal
    return MockConfigProvider({
        'max_loss_percent': Decimal('0.01'),  # 1%
        'max_leverage': 20,
        'default_leverage': 10,
        'cool_down_minutes': 30,
    })


@pytest.fixture
def faulty_provider() -> FaultyConfigProvider:
    """
    故障注入 Provider (默认在 get 时抛出异常)

    Returns:
        配置为 get() 抛出异常的 Provider
    """
    return FaultyConfigProvider(raise_on_get=True)


@pytest.fixture
def faulty_update_provider() -> FaultyConfigProvider:
    """
    故障注入 Provider (在 update 时抛出异常)

    Returns:
        配置为 update() 抛出异常的 Provider
    """
    return FaultyConfigProvider(raise_on_update=True)


@pytest.fixture
def slow_provider() -> SlowConfigProvider:
    """
    慢速 Provider(延迟 0.5 秒)

    Returns:
        配置为延迟 0.5 秒的 Provider
    """
    return SlowConfigProvider(delay_seconds=0.5)


@pytest.fixture
def mock_clock() -> MockClock:
    """
    模拟时钟 (固定在 2026-04-07 10:00:00)

    Returns:
        固定时间的 MockClock
    """
    return MockClock(datetime(2026, 4, 7, 10, 0, 0))


@pytest.fixture
def mock_clock_frozen() -> MockClock:
    """
    模拟时钟 (固定在 2026-04-07 00:00:00)

    Returns:
        固定零点时间的 MockClock
    """
    return MockClock(datetime(2026, 4, 7, 0, 0, 0))


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sample_core_config() -> Dict[str, Any]:
    """
    CoreConfig 样例数据

    包含核心系统配置：
    - 交易对列表
    - 时间周期列表
    - 交易所配置
    - 测试网标志

    Returns:
        核心配置字典
    """
    return {
        'core_symbols': [
            'BTC/USDT:USDT',
            'ETH/USDT:USDT',
            'SOL/USDT:USDT',
            'BNB/USDT:USDT'
        ],
        'core_timeframes': ['15m', '1h', '4h', '1d'],
        'exchange': 'binance',
        'testnet': True,
        'data_source': 'ccxt',
        'kline_buffer_size': 100,
    }


@pytest.fixture
def sample_user_config() -> Dict[str, Any]:
    """
    UserConfig 样例数据

    包含用户配置：
    - API 密钥
    - 通知配置
    - 测试网标志

    Returns:
        用户配置字典
    """
    return {
        'api_key': 'test_api_key_123456',
        'api_secret': 'test_api_secret_789012',
        'testnet': True,
        'notification_webhook': 'https://hook.example.com/v1/notify',
        'notification_enabled': True,
        'notification_channels': ['feishu', 'wechat'],
    }


@pytest.fixture
def sample_risk_config() -> Dict[str, Any]:
    """
    RiskConfig 样例数据

    包含风控配置：
    - 最大损失百分比
    - 杠杆配置
    - 冷却时间

    Returns:
        风控配置字典
    """
    from decimal import Decimal
    return {
        'max_loss_percent': Decimal('0.01'),  # 1% 最大损失
        'max_leverage': 20,  # 最大 20 倍杠杆
        'default_leverage': 10,  # 默认 10 倍杠杆
        'cool_down_minutes': 30,  # 30 分钟冷却时间
        'max_daily_loss_percent': Decimal('0.03'),  # 3% 每日最大损失
        'max_single_trade_loss_percent': Decimal('0.005'),  # 0.5% 单笔最大损失
    }


@pytest.fixture
def sample_account_config() -> Dict[str, Any]:
    """
    AccountConfig 样例数据

    包含账户配置：
    - 账户余额
    - 仓位信息
    - unrealized PnL

    Returns:
        账户配置字典
    """
    from decimal import Decimal
    return {
        'total_balance': Decimal('10000.00'),  # 总余额 10000 USDT
        'available_balance': Decimal('8000.00'),  # 可用余额 8000 USDT
        'unrealized_pnl': Decimal('150.50'),  # 未实现盈亏 150.50 USDT
        'positions': [
            {
                'symbol': 'BTC/USDT:USDT',
                'side': 'LONG',
                'size': Decimal('0.5'),
                'entry_price': Decimal('65000.00'),
                'leverage': 10,
            },
            {
                'symbol': 'ETH/USDT:USDT',
                'side': 'SHORT',
                'size': Decimal('2.0'),
                'entry_price': Decimal('3500.00'),
                'leverage': 5,
            }
        ],
    }


@pytest.fixture
def sample_account_snapshot() -> Dict[str, Any]:
    """
    账户快照样例数据

    包含完整的账户状态：
    - 余额信息
    - 仓位信息
    - 时间戳

    Returns:
        账户快照字典
    """
    from decimal import Decimal
    return {
        'total_balance': Decimal('10000.00'),
        'available_balance': Decimal('8000.00'),
        'unrealized_pnl': Decimal('150.50'),
        'positions': [
            {
                'symbol': 'BTC/USDT:USDT',
                'side': 'LONG',
                'size': Decimal('0.5'),
                'entry_price': Decimal('65000.00'),
                'leverage': 10,
                'liquidation_price': Decimal('58500.00'),
            }
        ],
        'timestamp': 1712473200000,  # 2024-04-07 09:00:00 UTC
    }


@pytest.fixture
def sample_kline_data() -> Dict[str, Any]:
    """
    K 线数据样例

    包含单根 K 线的完整数据：
    - OHLCV
    - 时间戳
    - 收盘标志

    Returns:
        K 线数据字典
    """
    from decimal import Decimal
    return {
        'symbol': 'BTC/USDT:USDT',
        'timeframe': '15m',
        'timestamp': 1712473200000,
        'open': Decimal('65000.00'),
        'high': Decimal('65500.00'),
        'low': Decimal('64800.00'),
        'close': Decimal('65200.00'),
        'volume': Decimal('1234.567'),
        'is_closed': True,
    }


@pytest.fixture
def sample_signal_data() -> Dict[str, Any]:
    """
    交易信号样例数据

    包含完整的信号信息：
    - 币种和周期
    - 方向
    - 入场价和止损
    - 仓位大小
    - 动态标签

    Returns:
        交易信号字典
    """
    from decimal import Decimal
    return {
        'symbol': 'BTC/USDT:USDT',
        'timeframe': '15m',
        'direction': 'LONG',
        'entry_price': Decimal('65200.00'),
        'suggested_stop_loss': Decimal('64350.00'),
        'suggested_position_size': Decimal('0.15'),
        'current_leverage': 10,
        'tags': [
            {'name': 'EMA', 'value': 'Bullish'},
            {'name': 'Pattern', 'value': 'Pinbar'},
            {'name': 'MTF', 'value': 'Aligned'},
        ],
        'risk_reward_info': 'RR 1:2.5',
        'strategy_name': 'pinbar_mtf',
        'score': 0.85,
    }


@pytest.fixture
def empty_config() -> Dict[str, Any]:
    """
    空配置样例

    用于测试空值处理边界条件

    Returns:
        空字典
    """
    return {}


@pytest.fixture
def minimal_core_config() -> Dict[str, Any]:
    """
    最小核心配置

    仅包含必填字段，用于测试最小配置场景

    Returns:
        最小核心配置字典
    """
    return {
        'core_symbols': ['BTC/USDT:USDT'],
        'core_timeframes': ['15m'],
        'exchange': 'binance',
        'testnet': False,
    }


@pytest.fixture
def large_config() -> Dict[str, Any]:
    """
    大型配置样例

    包含大量数据，用于测试性能边界

    Returns:
        大型配置字典
    """
    return {
        'core_symbols': [f'{coin}/USDT:USDT' for coin in [
            'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'MATIC',
            'DOT', 'AVAX', 'LINK', 'UNI', 'ATOM', 'LTC', 'BCH', 'FIL',
            'AAVE', 'EOS', 'XLM', 'TRX', 'ETC', 'XMR', 'ALGO', 'VET',
            'ICP', 'FIL', 'HBAR', 'APT', 'QNT', 'NEAR', 'STX', 'GRT'
        ]],
        'core_timeframes': ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '3d', '1w', '1M'],
        'exchange': 'binance',
        'testnet': True,
        'max_symbols': 50,
        'max_timeframes': 20,
    }
