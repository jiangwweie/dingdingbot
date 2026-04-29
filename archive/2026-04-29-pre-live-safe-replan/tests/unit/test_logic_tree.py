"""
单元测试：递归 LogicNode 类型定义

验收标准:
- 支持 AND/OR/NOT 逻辑门
- 支持 Trigger 和 Filter 叶子节点
- 使用 Discriminator Union
- 限制嵌套深度 ≤ 3
"""
import pytest
from decimal import Decimal
from pydantic import ValidationError

from src.domain.logic_tree import (
    LogicNode,
    TriggerLeaf,
    FilterLeaf,
    LeafNode,
    GateType,
)
from src.domain.models import TriggerConfig, FilterConfig


class TestTriggerLeaf:
    """测试 Trigger 叶子节点"""

    def test_create_trigger_leaf(self):
        """创建基本的 TriggerLeaf"""
        trigger = TriggerConfig(
            id="pinbar-1",
            type="pinbar",
            enabled=True,
            params={"min_wick_ratio": 0.6}
        )
        leaf = TriggerLeaf(
            type="trigger",
            id="pinbar-1",
            config=trigger
        )
        assert leaf.type == "trigger"
        assert leaf.id == "pinbar-1"
        assert leaf.config.type == "pinbar"

    def test_trigger_leaf_with_filter_config(self):
        """TriggerLeaf 使用 FilterConfig"""
        filter_cfg = FilterConfig(
            id="ema-1",
            type="ema_trend",
            enabled=True,
            params={"timeframe": "1h"}
        )
        leaf = FilterLeaf(
            type="filter",
            id="ema-1",
            config=filter_cfg
        )
        assert leaf.type == "filter"
        assert leaf.config.type == "ema_trend"


class TestFilterLeaf:
    """测试 Filter 叶子节点"""

    def test_create_filter_leaf(self):
        """创建基本的 FilterLeaf"""
        filter_cfg = FilterConfig(
            id="mtf-1",
            type="mtf",
            enabled=True,
            params={"validation_timeframe": "4h"}
        )
        leaf = FilterLeaf(
            type="filter",
            id="mtf-1",
            config=filter_cfg
        )
        assert leaf.type == "filter"
        assert leaf.id == "mtf-1"
        assert leaf.config.enabled is True


class TestLogicNode:
    """测试 LogicNode 递归结构"""

    def test_create_and_node(self):
        """创建 AND 逻辑门节点"""
        node = LogicNode(
            gate="AND",
            children=[]
        )
        assert node.gate == "AND"
        assert node.children == []

    def test_create_or_node(self):
        """创建 OR 逻辑门节点"""
        node = LogicNode(
            gate="OR",
            children=[]
        )
        assert node.gate == "OR"

    def test_create_not_node(self):
        """创建 NOT 逻辑门节点"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)

        node = LogicNode(
            gate="NOT",
            children=[leaf]
        )
        assert node.gate == "NOT"
        assert len(node.children) == 1

    def test_nested_logic_node(self):
        """创建嵌套的逻辑节点"""
        trigger1 = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        trigger2 = TriggerConfig(id="t2", type="engulfing", enabled=True, params={})

        leaf1 = TriggerLeaf(type="trigger", id="t1", config=trigger1)
        leaf2 = TriggerLeaf(type="trigger", id="t2", config=trigger2)

        # 创建 OR 节点
        or_node = LogicNode(gate="OR", children=[leaf1, leaf2])

        # 创建 AND 节点，包含 OR 节点
        filter_cfg = FilterConfig(id="f1", type="ema", enabled=True, params={})
        filter_leaf = FilterLeaf(type="filter", id="f1", config=filter_cfg)

        and_node = LogicNode(
            gate="AND",
            children=[or_node, filter_leaf]
        )

        assert and_node.gate == "AND"
        assert len(and_node.children) == 2
        # 检查第一个子节点是 LogicNode 且 gate 为 OR
        first_child = and_node.children[0]
        assert isinstance(first_child, LogicNode)
        assert first_child.gate == "OR"

    def test_discriminator_union_trigger_leaf(self):
        """测试 Discriminator Union - TriggerLeaf"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})

        # 使用 Discriminator 自动识别类型
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)
        assert isinstance(leaf, TriggerLeaf)

    def test_discriminator_union_filter_leaf(self):
        """测试 Discriminator Union - FilterLeaf"""
        filter_cfg = FilterConfig(id="f1", type="ema", enabled=True, params={})

        leaf = FilterLeaf(type="filter", id="f1", config=filter_cfg)
        assert isinstance(leaf, FilterLeaf)


class TestDepthValidation:
    """测试嵌套深度限制"""

    def test_depth_1_valid(self):
        """深度 1 有效"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)

        node = LogicNode(gate="AND", children=[leaf])
        assert node.model_dump()  # 不应抛出异常

    def test_depth_2_valid(self):
        """深度 2 有效"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)
        inner_node = LogicNode(gate="OR", children=[leaf])

        node = LogicNode(gate="AND", children=[inner_node])
        assert node.model_dump()

    def test_depth_3_valid(self):
        """深度 3 有效（最大允许深度）"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)

        # 深度 1
        node1 = LogicNode(gate="OR", children=[leaf])
        # 深度 2
        node2 = LogicNode(gate="AND", children=[node1])
        # 深度 3
        node3 = LogicNode(gate="OR", children=[node2])

        assert node3.model_dump()

    def test_depth_4_invalid(self):
        """深度 4 无效（应抛出 ValueError）"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)

        # 深度 1
        node1 = LogicNode(gate="OR", children=[leaf])
        # 深度 2
        node2 = LogicNode(gate="AND", children=[node1])
        # 深度 3
        node3 = LogicNode(gate="OR", children=[node2])
        # 深度 4 - 应失败
        with pytest.raises(ValueError) as exc_info:
            LogicNode(gate="AND", children=[node3])

        assert "depth" in str(exc_info.value).lower() or "嵌套" in str(exc_info.value)

    def test_depth_validation_with_mixed_gates(self):
        """测试混合逻辑门的深度验证"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        filter_cfg = FilterConfig(id="f1", type="ema", enabled=True, params={})

        t_leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)
        f_leaf = FilterLeaf(type="filter", id="f1", config=filter_cfg)

        # 深度 1: NOT 节点
        not_node = LogicNode(gate="NOT", children=[t_leaf])
        # 深度 2: AND 节点
        and_node = LogicNode(gate="AND", children=[not_node, f_leaf])
        # 深度 3: OR 节点（最大深度）
        or_node = LogicNode(gate="OR", children=[and_node])

        assert or_node.model_dump()


class TestLeafNodeUnion:
    """测试 LeafNode 联合类型"""

    def test_leaf_node_can_be_trigger(self):
        """LeafNode 可以是 TriggerLeaf"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf: LeafNode = TriggerLeaf(type="trigger", id="t1", config=trigger)
        assert leaf.type == "trigger"

    def test_leaf_node_can_be_filter(self):
        """LeafNode 可以是 FilterLeaf"""
        filter_cfg = FilterConfig(id="f1", type="ema", enabled=True, params={})
        leaf: LeafNode = FilterLeaf(type="filter", id="f1", config=filter_cfg)
        assert leaf.type == "filter"


class TestGateType:
    """测试 GateType 枚举"""

    def test_gate_type_values(self):
        """测试 GateType 枚举值"""
        assert GateType.AND == "AND"
        assert GateType.OR == "OR"
        assert GateType.NOT == "NOT"

    def test_logic_node_gate_validation(self):
        """测试 LogicNode gate 字段验证"""
        trigger = TriggerConfig(id="t1", type="pinbar", enabled=True, params={})
        leaf = TriggerLeaf(type="trigger", id="t1", config=trigger)

        # 有效的 gate 值
        for gate in ["AND", "OR", "NOT"]:
            node = LogicNode(gate=gate, children=[leaf])
            assert node.gate == gate

        # 无效的 gate 值
        with pytest.raises(ValueError):
            LogicNode(gate="XOR", children=[leaf])


class TestComplexLogicTree:
    """测试复杂逻辑树场景"""

    def test_pinbar_with_ema_and_mtf(self):
        """Pinbar + EMA 趋势过滤 + MTF 验证"""
        # Trigger
        pinbar = TriggerConfig(
            id="pinbar-main",
            type="pinbar",
            enabled=True,
            params={"min_wick_ratio": 0.6, "max_body_ratio": 0.3}
        )
        pinbar_leaf = TriggerLeaf(type="trigger", id="pinbar-main", config=pinbar)

        # Filter 1: EMA
        ema = FilterConfig(
            id="ema-trend",
            type="ema_trend",
            enabled=True,
            params={"timeframe": "1h"}
        )
        ema_leaf = FilterLeaf(type="filter", id="ema-trend", config=ema)

        # Filter 2: MTF
        mtf = FilterConfig(
            id="mtf-validation",
            type="mtf",
            enabled=True,
            params={"validation_timeframe": "4h"}
        )
        mtf_leaf = FilterLeaf(type="filter", id="mtf-validation", config=mtf)

        # 构建逻辑树：Pinbar AND (EMA AND MTF)
        ema_mtf_and = LogicNode(gate="AND", children=[ema_leaf, mtf_leaf])
        root = LogicNode(gate="AND", children=[pinbar_leaf, ema_mtf_and])

        assert root.gate == "AND"
        assert len(root.children) == 2
        assert root.children[0].type == "trigger"
        assert root.children[1].gate == "AND"

    def test_multi_trigger_or_pattern(self):
        """多 Trigger OR 模式：Pinbar OR Engulfing"""
        pinbar = TriggerConfig(id="pinbar", type="pinbar", enabled=True, params={})
        engulfing = TriggerConfig(id="engulfing", type="engulfing", enabled=True, params={})

        pinbar_leaf = TriggerLeaf(type="trigger", id="pinbar", config=pinbar)
        engulfing_leaf = TriggerLeaf(type="trigger", id="engulfing", config=engulfing)

        # OR 节点：任意一个 trigger 即可
        or_node = LogicNode(gate="OR", children=[pinbar_leaf, engulfing_leaf])

        assert or_node.gate == "OR"
        assert len(or_node.children) == 2
