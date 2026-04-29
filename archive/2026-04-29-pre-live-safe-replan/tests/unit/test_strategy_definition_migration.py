"""
单元测试：StrategyDefinition 迁移逻辑

测试场景：
1. 单 Trigger 迁移
2. 多 Trigger OR 迁移
3. 带 Filter 迁移
4. logic_tree 优先于旧字段
5. 无 warning 测试（使用 logic_tree 时）
"""
import pytest
import warnings
from decimal import Decimal

from src.domain.models import (
    StrategyDefinition,
    TriggerConfig,
    FilterConfig,
)
from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf


class TestSingleTriggerMigration:
    """测试单 Trigger 迁移"""

    def test_migrate_single_trigger(self):
        """测试单 Trigger 迁移到 logic_tree"""
        trigger = TriggerConfig(
            id="pinbar-1",
            type="pinbar",
            enabled=True,
            params={"min_wick_ratio": 0.6}
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_single_trigger",
                triggers=[trigger]
            )

            # 应该触发 DeprecationWarning
            assert len(w) == 1
            assert issubclass(w[-1].category, DeprecationWarning)
            assert "triggers/filters" in str(w[-1].message)

        # 验证 logic_tree 已构建
        assert strat.logic_tree is not None
        assert isinstance(strat.logic_tree, TriggerLeaf)
        assert strat.logic_tree.type == "trigger"
        assert strat.logic_tree.id == "pinbar-1"
        assert strat.logic_tree.config.type == "pinbar"

    def test_migrate_single_trigger_with_params(self):
        """测试单 Trigger 迁移保留参数"""
        trigger = TriggerConfig(
            id="engulfing-1",
            type="engulfing",
            enabled=True,
            params={"min_body_ratio": 0.8}
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_engulfing",
                triggers=[trigger]
            )

        assert strat.logic_tree is not None
        assert strat.logic_tree.config.params == {"min_body_ratio": 0.8}


class TestMultipleTriggersMigration:
    """测试多 Trigger 迁移"""

    def test_migrate_multiple_triggers_or(self):
        """测试多 Trigger OR 迁移"""
        trigger1 = TriggerConfig(
            id="pinbar-1",
            type="pinbar",
            enabled=True,
            params={"min_wick_ratio": 0.6}
        )
        trigger2 = TriggerConfig(
            id="engulfing-1",
            type="engulfing",
            enabled=True,
            params={}
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_multi_trigger",
                triggers=[trigger1, trigger2],
                trigger_logic="OR"
            )

            # 应该触发 DeprecationWarning
            assert len(w) == 1
            assert issubclass(w[-1].category, DeprecationWarning)

        # 验证 logic_tree 结构
        assert strat.logic_tree is not None
        assert isinstance(strat.logic_tree, LogicNode)
        assert strat.logic_tree.gate == "OR"
        assert len(strat.logic_tree.children) == 2

        # 验证子节点类型
        assert isinstance(strat.logic_tree.children[0], TriggerLeaf)
        assert isinstance(strat.logic_tree.children[1], TriggerLeaf)
        assert strat.logic_tree.children[0].config.type == "pinbar"
        assert strat.logic_tree.children[1].config.type == "engulfing"

    def test_migrate_multiple_triggers_and(self):
        """测试多 Trigger AND 迁移"""
        trigger1 = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        trigger2 = TriggerConfig(id="t2", type="engulfing", enabled=True, params={})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_and_triggers",
                triggers=[trigger1, trigger2],
                trigger_logic="AND"
            )

        assert strat.logic_tree.gate == "AND"
        assert len(strat.logic_tree.children) == 2


class TestFilterMigration:
    """测试带 Filter 迁移"""

    def test_migrate_single_trigger_single_filter(self):
        """测试单 Trigger + 单 Filter 迁移"""
        trigger = TriggerConfig(id="pinbar-1", type="pinbar", enabled=True, params={})
        filter_cfg = FilterConfig(id="ema-1", type="ema_trend", enabled=True, params={})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_trigger_filter",
                triggers=[trigger],
                filters=[filter_cfg]
            )

            assert len(w) == 1

        # 验证 structure: AND(trigger, filter)
        assert strat.logic_tree is not None
        assert isinstance(strat.logic_tree, LogicNode)
        assert strat.logic_tree.gate == "AND"
        assert len(strat.logic_tree.children) == 2

        # 第一个子节点是 TriggerLeaf
        assert isinstance(strat.logic_tree.children[0], TriggerLeaf)
        assert strat.logic_tree.children[0].config.type == "pinbar"

        # 第二个子节点是 FilterLeaf
        assert isinstance(strat.logic_tree.children[1], FilterLeaf)
        assert strat.logic_tree.children[1].config.type == "ema_trend"

    def test_migrate_with_multiple_filters(self):
        """测试带多个 Filter 迁移"""
        trigger = TriggerConfig(id="pinbar-1", type="pinbar", enabled=True, params={})
        filter1 = FilterConfig(id="ema-1", type="ema_trend", enabled=True, params={})
        filter2 = FilterConfig(id="mtf-1", type="mtf", enabled=True, params={})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_multi_filter",
                triggers=[trigger],
                filters=[filter1, filter2],
                filter_logic="AND"
            )

        # 验证 structure: AND(trigger, AND(filter1, filter2))
        assert strat.logic_tree.gate == "AND"
        assert len(strat.logic_tree.children) == 2

        # 第一个子节点是 TriggerLeaf
        assert isinstance(strat.logic_tree.children[0], TriggerLeaf)

        # 第二个子节点是 LogicNode (AND of filters)
        assert isinstance(strat.logic_tree.children[1], LogicNode)
        assert strat.logic_tree.children[1].gate == "AND"
        assert len(strat.logic_tree.children[1].children) == 2

    def test_migrate_with_or_filter_logic(self):
        """测试带 OR Filter 逻辑迁移"""
        trigger = TriggerConfig(id="pinbar-1", type="pinbar", enabled=True, params={})
        filter1 = FilterConfig(id="ema-1", type="ema_trend", enabled=True, params={})
        filter2 = FilterConfig(id="atr-1", type="atr", enabled=True, params={})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_or_filters",
                triggers=[trigger],
                filters=[filter1, filter2],
                filter_logic="OR"
            )

        # 验证 filter 部分使用 OR 逻辑
        filter_node = strat.logic_tree.children[1]
        assert isinstance(filter_node, LogicNode)
        assert filter_node.gate == "OR"


class TestLogicTreePriority:
    """测试 logic_tree 优先于旧字段"""

    def test_logic_tree_priority_over_triggers(self):
        """测试 logic_tree 优先于 triggers 字段"""
        # 自定义 logic_tree
        custom_tree = LogicNode(
            gate="OR",
            children=[
                TriggerLeaf(
                    type="trigger",
                    id="custom-trigger",
                    config=TriggerConfig(id="custom-trigger", type="pinbar", enabled=True, params={})
                )
            ]
        )

        # 同时提供 logic_tree 和 triggers
        old_trigger = TriggerConfig(id="old-trigger", type="engulfing", enabled=True, params={})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_priority",
                logic_tree=custom_tree,
                triggers=[old_trigger]  # 这个应该被忽略
            )

            # 使用 logic_tree 时不应该触发 warning
            assert len(w) == 0

        # 验证使用的是自定义 logic_tree，不是从旧字段迁移的
        assert strat.logic_tree == custom_tree
        assert strat.logic_tree.gate == "OR"
        assert strat.logic_tree.children[0].id == "custom-trigger"
        assert strat.logic_tree.children[0].config.type == "pinbar"

    def test_logic_tree_no_migration_warning(self):
        """测试使用 logic_tree 时不触发 migration warning"""
        tree = LogicNode(
            gate="AND",
            children=[
                TriggerLeaf(
                    type="trigger",
                    id="t1",
                    config=TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
                )
            ]
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_no_warning",
                logic_tree=tree
            )

            # 不应该有任何 DeprecationWarning
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 0


class TestHelperMethods:
    """测试辅助方法"""

    def test_get_triggers_from_logic_tree(self):
        """测试从 logic_tree 提取 triggers"""
        trigger1 = TriggerConfig(id="pinbar-1", type="pinbar", enabled=True, params={"min_wick": 0.6})
        trigger2 = TriggerConfig(id="engulfing-1", type="engulfing", enabled=True, params={})

        tree = LogicNode(
            gate="OR",
            children=[
                TriggerLeaf(type="trigger", id="pinbar-1", config=trigger1),
                TriggerLeaf(type="trigger", id="engulfing-1", config=trigger2),
            ]
        )

        strat = StrategyDefinition(name="test", logic_tree=tree)
        triggers = strat.get_triggers_from_logic_tree()

        assert len(triggers) == 2
        assert triggers[0].type == "pinbar"
        assert triggers[1].type == "engulfing"

    def test_get_filters_from_logic_tree(self):
        """测试从 logic_tree 提取 filters"""
        filter1 = FilterConfig(id="ema-1", type="ema_trend", enabled=True, params={})
        filter2 = FilterConfig(id="mtf-1", type="mtf", enabled=True, params={})

        tree = LogicNode(
            gate="AND",
            children=[
                TriggerLeaf(type="trigger", id="t1", config=TriggerConfig(id="t1", type="pinbar", enabled=True, params={})),
                LogicNode(
                    gate="AND",
                    children=[
                        FilterLeaf(type="filter", id="ema-1", config=filter1),
                        FilterLeaf(type="filter", id="mtf-1", config=filter2),
                    ]
                ),
            ]
        )

        strat = StrategyDefinition(name="test", logic_tree=tree)
        filters = strat.get_filters_from_logic_tree()

        assert len(filters) == 2
        assert filters[0].type == "ema_trend"
        assert filters[1].type == "mtf"

    def test_get_triggers_empty(self):
        """测试没有 trigger 时返回空列表"""
        tree = LogicNode(
            gate="AND",
            children=[
                FilterLeaf(type="filter", id="f1", config=FilterConfig(id="f1", type="ema", enabled=True, params={}))
            ]
        )

        strat = StrategyDefinition(name="test", logic_tree=tree)
        triggers = strat.get_triggers_from_logic_tree()

        assert len(triggers) == 0

    def test_get_filters_empty(self):
        """测试没有 filter 时返回空列表"""
        tree = LogicNode(
            gate="AND",
            children=[
                TriggerLeaf(type="trigger", id="t1", config=TriggerConfig(id="t1", type="pinbar", enabled=True, params={}))
            ]
        )

        strat = StrategyDefinition(name="test", logic_tree=tree)
        filters = strat.get_filters_from_logic_tree()

        assert len(filters) == 0


class TestEdgeCases:
    """测试边界情况"""

    def test_migrate_legacy_trigger_field(self):
        """测试迁移 legacy trigger 字段到 triggers 列表"""
        legacy_trigger = TriggerConfig(id="legacy-1", type="pinbar", enabled=True, params={})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test_legacy",
                trigger=legacy_trigger  # 使用旧字段
            )

            assert len(w) == 1

        assert strat.logic_tree is not None
        assert isinstance(strat.logic_tree, TriggerLeaf)
        assert strat.logic_tree.id == "legacy-1"

    def test_migrate_no_trigger_raises(self):
        """测试没有 trigger 和 filter 时 logic_tree 为 None"""
        # 当没有 triggers 时，迁移逻辑不会触发，logic_tree 保持为 None
        # 这是允许的，因为 logic_tree 是 Optional 字段
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(name="empty", triggers=[], filters=[])

        # 不应该有 warning，因为没有 triggers 需要迁移
        assert len(w) == 0
        # logic_tree 应该为 None
        assert strat.logic_tree is None

    def test_auto_generated_id(self):
        """测试自动生成的 ID"""
        trigger = TriggerConfig(type="pinbar", enabled=True, params={})  # 没有提供 id

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            strat = StrategyDefinition(name="test", triggers=[trigger])

        # 应该生成默认的 id
        assert strat.logic_tree.id != ""

    def test_complex_nested_structure(self):
        """测试复杂嵌套结构迁移"""
        trigger1 = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        trigger2 = TriggerConfig(id="t2", type="engulfing", enabled=True, params={})
        filter1 = FilterConfig(id="f1", type="ema", enabled=True, params={})
        filter2 = FilterConfig(id="f2", type="mtf", enabled=True, params={})

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="complex",
                triggers=[trigger1, trigger2],
                trigger_logic="OR",
                filters=[filter1, filter2],
                filter_logic="AND"
            )

        # 预期结构：AND(OR(t1, t2), AND(f1, f2))
        assert strat.logic_tree.gate == "AND"
        assert len(strat.logic_tree.children) == 2

        # trigger 节点
        trigger_node = strat.logic_tree.children[0]
        assert isinstance(trigger_node, LogicNode)
        assert trigger_node.gate == "OR"
        assert len(trigger_node.children) == 2

        # filter 节点
        filter_node = strat.logic_tree.children[1]
        assert isinstance(filter_node, LogicNode)
        assert filter_node.gate == "AND"
        assert len(filter_node.children) == 2


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_old_fields_preserved(self):
        """测试旧字段在迁移后仍然保留"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        filter_cfg = FilterConfig(id="f1", type="ema", enabled=True, params={})

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test",
                triggers=[trigger],
                filters=[filter_cfg],
                trigger_logic="OR",
                filter_logic="AND"
            )

        # 旧字段应该仍然可访问
        assert len(strat.triggers) == 1
        assert len(strat.filters) == 1
        assert strat.trigger_logic == "OR"
        assert strat.filter_logic == "AND"

    def test_is_global_and_apply_to_preserved(self):
        """测试环境作用域字段保留"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test",
                triggers=[trigger],
                is_global=False,
                apply_to=["BTC/USDT:USDT:15m", "ETH/USDT:USDT:1h"]
            )

        assert strat.is_global is False
        assert len(strat.apply_to) == 2
        assert "BTC/USDT:USDT:15m" in strat.apply_to


class TestCreateDynamicRunnerIntegration:
    """测试 create_dynamic_runner() 与 logic_tree 的集成"""

    def test_create_dynamic_runner_with_logic_tree(self):
        """测试 create_dynamic_runner() 使用 logic_tree 字段"""
        from src.domain.strategy_engine import create_dynamic_runner
        from src.domain.logic_tree import LogicNode, TriggerLeaf

        # 创建带 logic_tree 的策略定义
        tree = LogicNode(
            gate="AND",
            children=[
                TriggerLeaf(
                    type="trigger",
                    id="pinbar-1",
                    config=TriggerConfig(
                        id="pinbar-1",
                        type="pinbar",
                        enabled=True,
                        params={"min_wick_ratio": 0.6}
                    )
                ),
                FilterLeaf(
                    type="filter",
                    id="ema-1",
                    config=FilterConfig(
                        id="ema-1",
                        type="ema_trend",
                        enabled=True,
                        params={}
                    )
                )
            ]
        )

        strat_def = StrategyDefinition(
            name="test_logic_tree",
            logic_tree=tree,
            is_global=True
        )

        # 创建 runner
        runner = create_dynamic_runner([strat_def])

        # 验证 runner 已创建
        assert runner is not None
        assert len(runner._strategies) == 1
        assert runner._strategies[0].name == "test_logic_tree"

    def test_create_dynamic_runner_with_legacy_format(self):
        """测试 create_dynamic_runner() 向后兼容旧格式"""
        from src.domain.strategy_engine import create_dynamic_runner

        # 创建旧格式的策略定义
        strat_def = StrategyDefinition(
            name="test_legacy",
            triggers=[
                TriggerConfig(
                    id="pinbar-1",
                    type="pinbar",
                    enabled=True,
                    params={"min_wick_ratio": 0.6}
                )
            ],
            filters=[
                FilterConfig(
                    id="ema-1",
                    type="ema_trend",
                    enabled=True,
                    params={}
                )
            ]
        )

        # 创建 runner（应该自动迁移）
        runner = create_dynamic_runner([strat_def])

        # 验证 runner 已创建
        assert runner is not None
        assert len(runner._strategies) == 1

    def test_create_dynamic_runner_multiple_triggers(self):
        """测试 create_dynamic_runner() 处理多个 triggers"""
        from src.domain.strategy_engine import create_dynamic_runner
        from src.domain.logic_tree import LogicNode, TriggerLeaf

        # 创建带多个 triggers 的 logic_tree
        tree = LogicNode(
            gate="OR",
            children=[
                TriggerLeaf(
                    type="trigger",
                    id="pinbar-1",
                    config=TriggerConfig(id="pinbar-1", type="pinbar", enabled=True, params={})
                ),
                TriggerLeaf(
                    type="trigger",
                    id="engulfing-1",
                    config=TriggerConfig(id="engulfing-1", type="engulfing", enabled=True, params={})
                )
            ]
        )

        strat_def = StrategyDefinition(
            name="test_multi_trigger",
            logic_tree=tree
        )

        runner = create_dynamic_runner([strat_def])

        # 验证两个 trigger 都被创建为独立的策略
        assert len(runner._strategies) == 2
        strategy_names = [s.name for s in runner._strategies]
        assert "test_multi_trigger_pinbar" in strategy_names
        assert "test_multi_trigger_engulfing" in strategy_names
