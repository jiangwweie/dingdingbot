"""
Provider 层测试环境验证测试

本模块用于验证 Provider 层测试环境是否正确配置。

测试内容:
- Mock Provider 导入验证
- Fixture 数据验证
- MockClock 时间控制验证
"""

import pytest
from decimal import Decimal
from datetime import datetime

from tests.unit.application.config.providers.conftest import (
    MockConfigProvider,
    FaultyConfigProvider,
    SlowConfigProvider,
    MockClock,
)


class TestMockConfigProvider:
    """MockConfigProvider 验证测试"""

    def test_init_with_data(self):
        """测试初始化时设置数据"""
        provider = MockConfigProvider({'key': 'value'})
        assert provider._data == {'key': 'value'}
        assert provider.cache_ttl == 300

    def test_get_all_data(self):
        """测试获取全部数据"""
        provider = MockConfigProvider({'a': 1, 'b': 2})
        assert provider._data == {'a': 1, 'b': 2}

    def test_get_specific_key(self):
        """测试获取特定键"""
        provider = MockConfigProvider({'key': 'value'})
        assert provider._data.get('key') == 'value'

    def test_update_tracks_count(self):
        """测试更新操作追踪调用次数"""
        provider = MockConfigProvider()
        provider.update_call_count = 0
        import asyncio
        asyncio.run(provider.update('new_key', 'new_value'))
        assert provider.update_call_count == 1
        assert provider._data['new_key'] == 'new_value'

    def test_refresh_tracks_count(self):
        """测试刷新操作追踪调用次数"""
        provider = MockConfigProvider()
        import asyncio
        asyncio.run(provider.refresh())
        assert provider.refresh_call_count == 1

    def test_helper_methods(self):
        """测试辅助方法"""
        provider = MockConfigProvider()
        provider.set_data('test', 123)
        assert provider._data['test'] == 123
        provider.clear_data()
        assert provider._data == {}


class TestFaultyConfigProvider:
    """FaultyConfigProvider 验证测试"""

    def test_faulty_on_get(self):
        """测试 get 时抛出异常"""
        provider = FaultyConfigProvider(raise_on_get=True)
        import asyncio
        with pytest.raises(RuntimeError, match="Simulated error"):
            asyncio.run(provider.get())

    def test_faulty_on_update(self):
        """测试 update 时抛出异常"""
        provider = FaultyConfigProvider(raise_on_update=True)
        import asyncio
        with pytest.raises(RuntimeError, match="Simulated error"):
            asyncio.run(provider.update('key', 'value'))

    def test_faulty_on_refresh(self):
        """测试 refresh 时抛出异常"""
        provider = FaultyConfigProvider(raise_on_refresh=True)
        import asyncio
        with pytest.raises(RuntimeError, match="Simulated error"):
            asyncio.run(provider.refresh())

    def test_custom_error_message(self):
        """测试自定义错误消息"""
        provider = FaultyConfigProvider(raise_on_get=True, error_message="Custom error")
        import asyncio
        with pytest.raises(RuntimeError, match="Custom error"):
            asyncio.run(provider.get())

    def test_normal_operation_without_faults(self):
        """测试无故障时正常工作"""
        provider = FaultyConfigProvider()
        import asyncio
        asyncio.run(provider.update('key', 'value'))
        result = asyncio.run(provider.get('key'))
        assert result == 'value'


class TestSlowConfigProvider:
    """SlowConfigProvider 验证测试"""

    def test_delay_is_applied(self):
        """测试延迟生效"""
        import time
        provider = SlowConfigProvider(delay_seconds=0.1)
        start = time.time()
        import asyncio
        asyncio.run(provider.get())
        elapsed = time.time() - start
        assert elapsed >= 0.09  # 允许少量误差

    def test_custom_delay(self):
        """测试自定义延迟"""
        provider = SlowConfigProvider(delay_seconds=0.05)
        assert provider.delay_seconds == 0.05

    def test_with_initial_data(self):
        """测试带初始数据"""
        provider = SlowConfigProvider(delay_seconds=0.01, initial_data={'key': 'value'})
        import asyncio
        result = asyncio.run(provider.get('key'))
        assert result == 'value'


class TestMockClock:
    """MockClock 验证测试"""

    def test_fixed_time_initialization(self):
        """测试固定时间初始化"""
        fixed_time = datetime(2026, 4, 7, 10, 0, 0)
        clock = MockClock(fixed_time)
        assert clock.now() == fixed_time

    def test_default_initialization(self):
        """测试默认初始化使用当前时间"""
        before = datetime.now()
        clock = MockClock()
        after = datetime.now()
        assert before <= clock.now() <= after

    def test_advance_seconds(self):
        """测试推进时间"""
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        clock.advance(300)  # 推进 5 分钟
        assert clock.now() == datetime(2026, 4, 7, 10, 5, 0)

    def test_advance_multiple_times(self):
        """测试多次推进时间"""
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        clock.advance(60)
        clock.advance(60)
        clock.advance(60)
        assert clock.now() == datetime(2026, 4, 7, 10, 3, 0)

    def test_set_time(self):
        """测试设置时间"""
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        clock.set_time(datetime(2026, 4, 8, 15, 30, 0))
        assert clock.now() == datetime(2026, 4, 8, 15, 30, 0)

    def test_ttl_expiration_simulation(self):
        """测试 TTL 过期模拟"""
        # 这是 MockClock 的核心使用场景
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))

        # 模拟设置缓存，TTL=300 秒
        from datetime import timedelta
        cache_ttl = 300
        expires_at = clock.now() + timedelta(seconds=cache_ttl)

        # 5 分钟后（299 秒），缓存应有效（还未到过期时间）
        clock.advance(299)
        assert clock.now() <= expires_at  # 未过期

        # 再过 2 秒（总共 301 秒），缓存应过期
        clock.advance(2)
        assert clock.now() > expires_at  # 已过期


class TestFixtureData:
    """Fixture 数据验证测试"""

    def test_sample_core_config_structure(self, sample_core_config):
        """测试核心配置样例数据结构"""
        assert 'core_symbols' in sample_core_config
        assert 'core_timeframes' in sample_core_config
        assert 'exchange' in sample_core_config
        assert 'testnet' in sample_core_config
        assert len(sample_core_config['core_symbols']) >= 3

    def test_sample_user_config_structure(self, sample_user_config):
        """测试用户配置样例数据结构"""
        assert 'api_key' in sample_user_config
        assert 'api_secret' in sample_user_config
        assert 'testnet' in sample_user_config
        assert 'notification_webhook' in sample_user_config

    def test_sample_risk_config_decimal_types(self, sample_risk_config):
        """测试风控配置使用 Decimal 类型"""
        assert isinstance(sample_risk_config['max_loss_percent'], Decimal)
        assert isinstance(sample_risk_config['max_daily_loss_percent'], Decimal)
        assert sample_risk_config['max_loss_percent'] == Decimal('0.01')

    def test_sample_account_config_structure(self, sample_account_config):
        """测试账户配置样例数据结构"""
        assert 'total_balance' in sample_account_config
        assert 'available_balance' in sample_account_config
        assert 'positions' in sample_account_config
        assert isinstance(sample_account_config['total_balance'], Decimal)

    def test_sample_account_snapshot_structure(self, sample_account_snapshot):
        """测试账户快照样例数据结构"""
        assert 'total_balance' in sample_account_snapshot
        assert 'positions' in sample_account_snapshot
        assert 'timestamp' in sample_account_snapshot
        assert len(sample_account_snapshot['positions']) >= 1

    def test_sample_kline_data_structure(self, sample_kline_data):
        """测试 K 线数据样例结构"""
        assert 'symbol' in sample_kline_data
        assert 'timeframe' in sample_kline_data
        assert 'open' in sample_kline_data
        assert 'high' in sample_kline_data
        assert 'low' in sample_kline_data
        assert 'close' in sample_kline_data
        assert 'is_closed' in sample_kline_data
        assert isinstance(sample_kline_data['close'], Decimal)

    def test_sample_signal_data_structure(self, sample_signal_data):
        """测试交易信号样例数据结构"""
        assert 'symbol' in sample_signal_data
        assert 'direction' in sample_signal_data
        assert 'entry_price' in sample_signal_data
        assert 'suggested_stop_loss' in sample_signal_data
        assert 'tags' in sample_signal_data
        assert isinstance(sample_signal_data['tags'], list)

    def test_empty_config(self, empty_config):
        """测试空配置"""
        assert empty_config == {}

    def test_minimal_core_config(self, minimal_core_config):
        """测试最小核心配置"""
        assert len(minimal_core_config['core_symbols']) == 1
        assert len(minimal_core_config['core_timeframes']) == 1

    def test_large_config(self, large_config):
        """测试大型配置"""
        assert len(large_config['core_symbols']) > 10
        assert len(large_config['core_timeframes']) > 5
