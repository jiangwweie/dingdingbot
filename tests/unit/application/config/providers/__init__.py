"""
Provider 层测试夹具和 Mock 实现

本模块提供测试 Provider 层所需的 Mock Provider 和测试数据。

包含:
- MockConfigProvider: 通用 Mock Provider(实现 Protocol 接口)
- FaultyConfigProvider: 故障注入 Provider(模拟异常)
- SlowConfigProvider: 慢速 Provider(模拟延迟)
- MockClock: 时钟 Mock(控制 TTL 过期)
- 配置数据 Fixture

设计参考：
- docs/reviews/p1_5_provider_design_qa_review.md#61-fixture-provider-实现
- docs/arch/P1-5-provider-registration-design.md#23-缓存策略

使用示例:
    # 方式 1: 从 conftest 导入 Mock 类
    from tests.unit.application.config.providers.conftest import MockConfigProvider, MockClock

    # 方式 2: 使用 pytest fixture
    def test_something(mock_core_provider, sample_core_config):
        # mock_core_provider: MockConfigProvider 实例
        # sample_core_config: 配置数据字典
        ...

    # 方式 3: MockClock 控制 TTL 过期
    def test_cache_expiration(mock_clock):
        provider = TestProvider(clock=mock_clock)
        mock_clock.advance(300)  # 推进 5 分钟
        ...
"""

# 从 conftest 导入 Mock 类，方便测试使用
from tests.unit.application.config.providers.conftest import (
    MockConfigProvider,
    FaultyConfigProvider,
    SlowConfigProvider,
    MockClock,
)

__all__ = [
    'MockConfigProvider',
    'FaultyConfigProvider',
    'SlowConfigProvider',
    'MockClock',
]
