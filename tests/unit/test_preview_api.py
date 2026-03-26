"""
单元测试：F-4 热预览接口
"""
import pytest
from decimal import Decimal
from src.interfaces.api import StrategyPreviewRequest, StrategyPreviewResponse
from src.domain.models import StrategyDefinition
from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf
from src.domain.models import TriggerConfig, FilterConfig


class TestStrategyPreviewRequest:
    """测试预览请求模型"""

    def test_create_preview_request(self):
        """测试创建基本的预览请求"""
        logic_tree = {
            "gate": "AND",
            "children": [
                {
                    "type": "trigger",
                    "id": "pinbar-1",
                    "config": {
                        "type": "pinbar",
                        "id": "pinbar-1",
                        "enabled": True,
                        "params": {"min_wick_ratio": 0.6}
                    }
                }
            ]
        }

        request = StrategyPreviewRequest(
            logic_tree=logic_tree,
            symbol="BTC/USDT:USDT",
            timeframe="15m"
        )

        assert request.logic_tree == logic_tree
        assert request.symbol == "BTC/USDT:USDT"
        assert request.timeframe == "15m"

    def test_preview_request_required_fields(self):
        """测试必填字段验证"""
        from pydantic import ValidationError

        # 缺少必填字段应失败
        with pytest.raises(ValidationError):
            StrategyPreviewRequest(
                logic_tree={},
                # symbol 和 timeframe 缺失
            )


class TestStrategyPreviewResponse:
    """测试预览响应模型"""

    def test_create_preview_response_signal_fired(self):
        """测试信号触发时的响应"""
        trace_tree = {
            "node_id": "root",
            "node_type": "AND",
            "passed": True,
            "reason": "all_children_passed",
            "children": []
        }

        response = StrategyPreviewResponse(
            signal_fired=True,
            trace_tree=trace_tree,
            details={"trigger": "pinbar", "direction": "long"}
        )

        assert response.signal_fired is True
        assert response.trace_tree == trace_tree
        assert response.details["trigger"] == "pinbar"

    def test_create_preview_response_no_signal(self):
        """测试信号未触发时的响应"""
        trace_tree = {
            "node_id": "root",
            "node_type": "AND",
            "passed": False,
            "reason": "child_failed",
            "children": []
        }

        response = StrategyPreviewResponse(
            signal_fired=False,
            trace_tree=trace_tree
        )

        assert response.signal_fired is False
        assert response.details is None


class TestLogicTreeConversion:
    """测试 logic_tree 转换"""

    def test_dict_to_strategy_definition(self):
        """测试将 dict 转换为 StrategyDefinition"""
        logic_tree_dict = {
            "gate": "AND",
            "children": [
                {
                    "type": "trigger",
                    "id": "pinbar-1",
                    "config": {
                        "type": "pinbar",
                        "id": "pinbar-1",
                        "enabled": True,
                        "params": {"min_wick_ratio": 0.6}
                    }
                }
            ]
        }

        strategy_def = StrategyDefinition(
            name="test",
            logic_tree=logic_tree_dict
        )

        assert strategy_def.logic_tree is not None
        assert strategy_def.logic_tree.gate == "AND"

    def test_complex_logic_tree(self):
        """测试复杂逻辑树转换"""
        logic_tree_dict = {
            "gate": "AND",
            "children": [
                {
                    "gate": "OR",
                    "children": [
                        {
                            "type": "trigger",
                            "id": "pinbar-1",
                            "config": {"type": "pinbar", "id": "pinbar-1", "enabled": True, "params": {}}
                        },
                        {
                            "type": "trigger",
                            "id": "engulfing-1",
                            "config": {"type": "engulfing", "id": "engulfing-1", "enabled": True, "params": {}}
                        }
                    ]
                },
                {
                    "type": "filter",
                    "id": "ema-1",
                    "config": {"type": "ema_trend", "id": "ema-1", "enabled": True, "params": {"period": 60}}
                }
            ]
        }

        strategy_def = StrategyDefinition(
            name="test",
            logic_tree=logic_tree_dict
        )

        # 验证结构
        assert strategy_def.logic_tree.gate == "AND"
        assert len(strategy_def.logic_tree.children) == 2

        # 第一个子节点是 OR 节点
        or_node = strategy_def.logic_tree.children[0]
        assert isinstance(or_node, LogicNode)
        assert or_node.gate == "OR"
        assert len(or_node.children) == 2

        # 第二个子节点是 Filter Leaf
        filter_leaf = strategy_def.logic_tree.children[1]
        assert isinstance(filter_leaf, FilterLeaf)
        assert filter_leaf.config.type == "ema_trend"


class TestTraceTreeConversion:
    """测试 TraceTree 转换"""

    def test_trace_node_to_dict(self):
        """测试 TraceNode 转换为 dict"""
        from src.domain.recursive_engine import TraceNode

        trace_node = TraceNode(
            node_id="root",
            node_type="AND",
            passed=True,
            reason="all_passed",
            children=[
                TraceNode(
                    node_id="child1",
                    node_type="trigger",
                    passed=True,
                    reason="pattern_detected",
                    metadata={"wick_ratio": 0.7}
                )
            ]
        )

        def trace_to_dict(node):
            return {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "passed": node.passed,
                "reason": node.reason,
                "metadata": node.metadata,
                "children": [trace_to_dict(child) for child in node.children]
            }

        result = trace_to_dict(trace_node)

        assert result["node_id"] == "root"
        assert result["node_type"] == "AND"
        assert result["passed"] is True
        assert len(result["children"]) == 1
        assert result["children"][0]["metadata"]["wick_ratio"] == 0.7
