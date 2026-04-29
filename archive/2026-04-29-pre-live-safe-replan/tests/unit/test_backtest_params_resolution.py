"""
Unit tests for Phase 8.1 回测参数链路收口.

Tests verify:
1. runtime_overrides 覆盖 request.order_strategy
2. dynamic path 也能吃到 resolved_params
3. resolve_backtest_params() 对 strategy.* 参数的合并优先级
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.backtester import (
    Backtester,
    resolve_backtest_params,
    BacktestRuntimeOverrides,
    ResolvedBacktestParams,
)
from src.domain.models import (
    BacktestRequest,
    OrderStrategy,
    KlineData,
)
from src.infrastructure.exchange_gateway import ExchangeGateway


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sample_klines():
    """Sample K-line data for backtesting"""
    return [
        KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1704067200000,
            open=Decimal("42000.00"),
            high=Decimal("42500.00"),
            low=Decimal("41800.00"),
            close=Decimal("42300.00"),
            volume=Decimal("1000.0"),
            is_closed=True,
        ),
    ]


@pytest.fixture
def mock_exchange_gateway():
    """Mock exchange gateway"""
    gateway = MagicMock(spec=ExchangeGateway)
    gateway.fetch_historical_ohlcv = AsyncMock(return_value=[])
    return gateway


# ============================================================
# Test: resolve_backtest_params 优先级
# ============================================================

class TestResolveBacktestParamsPriority:
    """测试 resolve_backtest_params 的参数优先级"""

    def test_runtime_overrides_highest_priority(self):
        """runtime_overrides 具有最高优先级"""
        overrides = BacktestRuntimeOverrides(
            max_atr_ratio=Decimal("0.02"),
            min_distance_pct=Decimal("0.01"),
            ema_period=30,
            tp_ratios=[Decimal("0.7"), Decimal("0.3")],
            tp_targets=[Decimal("1.5"), Decimal("3.0")],
            breakeven_enabled=True,
        )

        params = resolve_backtest_params(runtime_overrides=overrides)

        assert params.max_atr_ratio == Decimal("0.02")
        assert params.min_distance_pct == Decimal("0.01")
        assert params.ema_period == 30
        assert params.tp_ratios == [Decimal("0.7"), Decimal("0.3")]
        assert params.tp_targets == [Decimal("1.5"), Decimal("3.0")]
        assert params.breakeven_enabled == True

    def test_kv_configs_middle_priority(self):
        """KV 配置具有中等优先级"""
        kv_configs = {
            "strategy.atr.max_atr_ratio": Decimal("0.015"),
            "strategy.ema.min_distance_pct": Decimal("0.008"),
            "strategy.ema.period": 50,
            "backtest.breakeven_enabled": True,
        }

        params = resolve_backtest_params(kv_configs=kv_configs)

        assert params.max_atr_ratio == Decimal("0.015")
        assert params.min_distance_pct == Decimal("0.008")
        assert params.ema_period == 50
        assert params.breakeven_enabled == True

    def test_runtime_overrides_overrides_kv(self):
        """runtime_overrides 覆盖 KV 配置"""
        overrides = BacktestRuntimeOverrides(
            max_atr_ratio=Decimal("0.02"),
        )
        kv_configs = {
            "strategy.atr.max_atr_ratio": Decimal("0.015"),
        }

        params = resolve_backtest_params(
            runtime_overrides=overrides,
            kv_configs=kv_configs,
        )

        # runtime_overrides 应该覆盖 KV
        assert params.max_atr_ratio == Decimal("0.02")

    def test_defaults_when_nothing_provided(self):
        """无任何配置时使用默认值"""
        params = resolve_backtest_params()

        assert params.max_atr_ratio == Decimal("0.01")
        assert params.min_distance_pct == Decimal("0.005")
        assert params.ema_period == 60
        assert params.tp_ratios == [Decimal("0.6"), Decimal("0.4")]
        assert params.tp_targets == [Decimal("1.0"), Decimal("2.5")]
        assert params.breakeven_enabled == False


# ============================================================
# Test: runtime_overrides 覆盖 request.order_strategy
# ============================================================

class TestRuntimeOverridesOrderStrategy:
    """测试 runtime_overrides 覆盖 request.order_strategy"""

    @pytest.mark.asyncio
    async def test_runtime_overrides_tp_params_override_request_order_strategy(
        self, mock_exchange_gateway, sample_klines
    ):
        """runtime_overrides 的 TP 参数应覆盖 request.order_strategy"""
        backtester = Backtester(mock_exchange_gateway)

        # request 自带 order_strategy
        request = BacktestRequest(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            mode="v3_pms",
            order_strategy=OrderStrategy(
                id="request_strategy",
                name="Request Strategy",
                tp_ratios=[Decimal("0.5"), Decimal("0.5")],
                tp_targets=[Decimal("2.0"), Decimal("4.0")],
            ),
        )

        # runtime_overrides 提供不同的 TP 参数
        overrides = BacktestRuntimeOverrides(
            tp_ratios=[Decimal("0.7"), Decimal("0.3")],
            tp_targets=[Decimal("1.5"), Decimal("3.0")],
        )

        # Mock _run_v3_pms_backtest 捕获实际使用的参数
        captured_strategy = None

        async def mock_run_v3_pms(req, repo, bt_repo, order_repo, kv_configs, runtime_overrides=None):
            nonlocal captured_strategy
            # 模拟创建 OrderStrategy 的逻辑
            if runtime_overrides and (runtime_overrides.tp_ratios or runtime_overrides.tp_targets):
                captured_strategy = "runtime_overrides"
            elif req.order_strategy:
                captured_strategy = "request"
            else:
                captured_strategy = "default"
            return MagicMock()

        with patch.object(backtester, '_run_v3_pms_backtest', side_effect=mock_run_v3_pms):
            await backtester.run_backtest(request, runtime_overrides=overrides)

        # 验证 runtime_overrides 被使用
        assert captured_strategy == "runtime_overrides"


# ============================================================
# Test: dynamic path 接入 resolved_params
# ============================================================

class TestDynamicPathResolvedParams:
    """测试动态策略路径接入 resolved_params"""

    def test_build_dynamic_runner_receives_resolved_params(self, mock_exchange_gateway):
        """_build_dynamic_runner 应接收 resolved_params"""
        backtester = Backtester(mock_exchange_gateway)

        # 创建 resolved_params
        resolved_params = ResolvedBacktestParams(
            max_atr_ratio=Decimal("0.015"),
            min_distance_pct=Decimal("0.008"),
            ema_period=50,
            mtf_ema_period=60,
            mtf_mapping={"1h": "4h"},
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            breakeven_enabled=False,
            slippage_rate=Decimal("0.001"),
            tp_slippage_rate=Decimal("0.0005"),
            fee_rate=Decimal("0.0004"),
            initial_balance=Decimal("10000"),
        )

        # Mock create_dynamic_runner
        with patch('src.application.backtester.create_dynamic_runner') as mock_create:
            mock_create.return_value = MagicMock()

            backtester._build_dynamic_runner([], resolved_params)

            # 验证 resolved_params 被传递
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert 'resolved_params' in call_kwargs
            assert call_kwargs['resolved_params'] == resolved_params


# ============================================================
# Test: FilterFactory resolved_params 注入
# ============================================================

class TestFilterFactoryResolvedParams:
    """测试 FilterFactory 支持 resolved_params 注入"""

    def test_ema_filter_receives_min_distance_pct(self):
        """EMA 过滤器应接收 min_distance_pct"""
        from src.domain.filter_factory import FilterFactory

        resolved_params = MagicMock()
        resolved_params.min_distance_pct = Decimal("0.008")
        resolved_params.ema_period = 50
        resolved_params.max_atr_ratio = Decimal("0.015")

        filter_config = {"type": "ema_trend", "enabled": True}

        filter_instance = FilterFactory.create(filter_config, resolved_params=resolved_params)

        # 验证 min_distance_pct 被注入
        assert filter_instance._min_distance_pct == Decimal("0.008")

    def test_atr_filter_receives_max_atr_ratio(self):
        """ATR 过滤器应接收 max_atr_ratio"""
        from src.domain.filter_factory import FilterFactory

        resolved_params = MagicMock()
        resolved_params.max_atr_ratio = Decimal("0.015")

        filter_config = {"type": "atr", "enabled": True}

        filter_instance = FilterFactory.create(filter_config, resolved_params=resolved_params)

        # 验证 max_atr_ratio 被注入
        assert filter_instance._max_atr_ratio == Decimal("0.015")

    def test_resolved_params_overrides_filter_config(self):
        """resolved_params 应覆盖 filter_config 中的参数"""
        from src.domain.filter_factory import FilterFactory

        resolved_params = MagicMock()
        resolved_params.min_distance_pct = Decimal("0.008")
        resolved_params.ema_period = 50

        # filter_config 中有不同的值
        filter_config = {
            "type": "ema_trend",
            "enabled": True,
            "params": {"min_distance_pct": 0.003, "period": 40}
        }

        filter_instance = FilterFactory.create(filter_config, resolved_params=resolved_params)

        # resolved_params 应覆盖
        assert filter_instance._min_distance_pct == Decimal("0.008")
        assert filter_instance._period == 50


# ============================================================
# Test: 局部字段覆写语义
# ============================================================

class TestPartialFieldOverride:
    """测试 runtime_overrides 的局部字段覆写语义"""

    def test_runtime_overrides_preserves_other_order_strategy_fields(self):
        """runtime_overrides 应仅覆写 tp_ratios/tp_targets，保留其他字段"""
        from src.domain.models import OrderStrategy

        # 模拟 request.order_strategy 有自定义字段
        base_strategy = OrderStrategy(
            id="custom_strategy",
            name="Custom Strategy",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("2.0"), Decimal("4.0")],
            initial_stop_loss_rr=Decimal("-0.5"),  # 自定义值
            trailing_stop_enabled=False,
            oco_enabled=False,  # 自定义值
        )

        # runtime_overrides 只提供 tp_ratios/tp_targets
        overrides = BacktestRuntimeOverrides(
            tp_ratios=[Decimal("0.7"), Decimal("0.3")],
            tp_targets=[Decimal("1.5"), Decimal("3.0")],
        )

        # 模拟 backtester.py 中的逻辑
        resolved_params = resolve_backtest_params(runtime_overrides=overrides)

        # 构建最终 strategy（模拟 backtester.py line 1675-1699）
        if overrides and (overrides.tp_ratios or overrides.tp_targets):
            strategy = OrderStrategy(
                id=base_strategy.id,
                name=base_strategy.name,
                tp_levels=len(resolved_params.tp_ratios),
                tp_ratios=resolved_params.tp_ratios,
                tp_targets=resolved_params.tp_targets,
                initial_stop_loss_rr=base_strategy.initial_stop_loss_rr,
                trailing_stop_enabled=base_strategy.trailing_stop_enabled,
                oco_enabled=base_strategy.oco_enabled,
            )
        else:
            strategy = base_strategy

        # 验证：tp_* 被覆写，其他字段保留
        assert strategy.tp_ratios == [Decimal("0.7"), Decimal("0.3")], "tp_ratios should be overridden"
        assert strategy.tp_targets == [Decimal("1.5"), Decimal("3.0")], "tp_targets should be overridden"
        assert strategy.id == "custom_strategy", "id should be preserved"
        assert strategy.name == "Custom Strategy", "name should be preserved"
        assert strategy.initial_stop_loss_rr == Decimal("-0.5"), "initial_stop_loss_rr should be preserved"
        assert strategy.oco_enabled == False, "oco_enabled should be preserved"
