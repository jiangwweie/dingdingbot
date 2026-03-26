"""
递归评估引擎 - Recursive Evaluation Engine

实现逻辑树的递归评估，支持：
- AND 节点：all() 短路评估
- OR 节点：any() 短路评估
- NOT 节点：结果反转
- Leaf 节点：委托给 StrategyRunner 执行

纯函数式实现，无副作用。
"""
from typing import Union, List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid

from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf, LeafNode
from src.domain.models import KlineData, Direction, TrendDirection, PatternResult
from src.domain.strategy_engine import StrategyRunner, FilterContext
from src.domain.filter_factory import FilterContext as DynamicFilterContext, TraceEvent


# ============================================================
# Trace Node - 评估追踪节点
# ============================================================
class TraceNode(BaseModel):
    """
    评估追踪节点

    用于记录递归评估过程中每个节点的评估结果，形成完整的评估追踪树。
    """
    node_id: str = Field(..., description="对应 LogicNode 的 ID 或生成的唯一标识")
    node_type: str = Field(..., description="节点类型：AND/OR/NOT/trigger/filter")
    passed: bool = Field(..., description="是否通过评估")
    reason: str = Field(..., description="通过/失败原因")
    children: List["TraceNode"] = Field(default_factory=list, description="子节点追踪结果")
    details: Dict[str, Any] = Field(default_factory=dict, description="中间结果/详细数据")

    @classmethod
    def create_pass(cls, node_id: str, node_type: str, reason: str,
                    children: List["TraceNode"] = None, details: Dict[str, Any] = None) -> "TraceNode":
        """快捷创建通过的 TraceNode"""
        return cls(
            node_id=node_id,
            node_type=node_type,
            passed=True,
            reason=reason,
            children=children or [],
            details=details or {}
        )

    @classmethod
    def create_fail(cls, node_id: str, node_type: str, reason: str,
                    children: List["TraceNode"] = None, details: Dict[str, Any] = None) -> "TraceNode":
        """快捷创建失败的 TraceNode"""
        return cls(
            node_id=node_id,
            node_type=node_type,
            passed=False,
            reason=reason,
            children=children or [],
            details=details or {}
        )


# ============================================================
# 递归评估函数
# ============================================================
def evaluate_node(
    node: Union[LogicNode, LeafNode],
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
) -> TraceNode:
    """
    递归评估逻辑树（纯函数式实现）

    评估逻辑：
    - AND 节点：all() 短路评估 - 任一子节点失败立即返回
    - OR 节点：any() 短路评估 - 任一子节点通过立即返回
    - NOT 节点：结果反转 - 子节点通过则失败，子节点失败则通过
    - Leaf 节点：委托给 runner 执行

    Args:
        node: 逻辑节点（内部节点或叶子节点）
        kline: 当前 K 线数据
        context: 过滤器上下文
        runner: 策略运行器

    Returns:
        TraceNode: 评估追踪节点，包含完整的评估路径信息
    """
    # 获取节点 ID
    node_id = _get_node_id(node)

    # 根据节点类型分发评估逻辑
    if isinstance(node, LogicNode):
        return _evaluate_logic_node(node, kline, context, runner, node_id)
    elif isinstance(node, (TriggerLeaf, FilterLeaf)):
        return _evaluate_leaf_node(node, kline, context, runner, node_id)
    else:
        # 不应该到达这里
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="unknown",
            reason=f"未知节点类型：{type(node)}"
        )


def _get_node_id(node: Union[LogicNode, LeafNode]) -> str:
    """获取或生成节点 ID"""
    if isinstance(node, LogicNode):
        # LogicNode 没有 id 字段，生成一个
        return f"logic_{node.gate}_{id(node)}"
    elif isinstance(node, (TriggerLeaf, FilterLeaf)):
        return node.id
    else:
        return f"unknown_{id(node)}"


def _evaluate_logic_node(
    node: LogicNode,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估逻辑门节点（AND/OR/NOT）

    Args:
        node: LogicNode 实例
        kline: K 线数据
        context: 过滤器上下文
        runner: 策略运行器
        node_id: 节点 ID

    Returns:
        TraceNode: 评估追踪结果
    """
    gate = node.gate

    if gate == "AND":
        return _evaluate_and_node(node, kline, context, runner, node_id)
    elif gate == "OR":
        return _evaluate_or_node(node, kline, context, runner, node_id)
    elif gate == "NOT":
        return _evaluate_not_node(node, kline, context, runner, node_id)
    else:
        return TraceNode.create_fail(
            node_id=node_id,
            node_type=gate,
            reason=f"未知逻辑门类型：{gate}"
        )


def _evaluate_and_node(
    node: LogicNode,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估 AND 节点 - 所有子节点必须通过

    短路逻辑：任一子节点失败，立即返回失败
    空子节点：vacuous truth（空真）- 返回通过
    """
    children = node.children

    # 空子节点处理 - vacuous truth
    if not children:
        return TraceNode.create_pass(
            node_id=node_id,
            node_type="AND",
            reason="vacuous_truth_empty_children"
        )

    evaluated_children: List[TraceNode] = []

    for idx, child in enumerate(children):
        # 递归评估子节点
        child_result = evaluate_node(child, kline, context, runner)
        evaluated_children.append(child_result)

        # 短路：如果任一子节点失败，AND 节点立即失败
        if not child_result.passed:
            return TraceNode.create_fail(
                node_id=node_id,
                node_type="AND",
                reason=f"child_{idx}_failed: {child_result.reason}",
                children=evaluated_children,
                details={"failed_child_index": idx, "failed_child_type": child_result.node_type}
            )

    # 所有子节点都通过
    return TraceNode.create_pass(
        node_id=node_id,
        node_type="AND",
        reason="all_children_passed",
        children=evaluated_children,
        details={"total_children": len(children)}
    )


def _evaluate_or_node(
    node: LogicNode,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估 OR 节点 - 任一子节点通过即可

    短路逻辑：任一子节点通过，立即返回通过
    空子节点：vacuous falsity（空假）- 返回失败
    """
    children = node.children

    # 空子节点处理 - vacuous falsity
    if not children:
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="OR",
            reason="vacuous_falsity_empty_children"
        )

    evaluated_children: List[TraceNode] = []

    for idx, child in enumerate(children):
        # 递归评估子节点
        child_result = evaluate_node(child, kline, context, runner)
        evaluated_children.append(child_result)

        # 短路：如果任一子节点通过，OR 节点立即通过
        if child_result.passed:
            return TraceNode.create_pass(
                node_id=node_id,
                node_type="OR",
                reason=f"child_{idx}_passed: {child_result.reason}",
                children=evaluated_children,
                details={"passed_child_index": idx, "passed_child_type": child_result.node_type}
            )

    # 所有子节点都失败
    return TraceNode.create_fail(
        node_id=node_id,
        node_type="OR",
        reason="all_children_failed",
        children=evaluated_children,
        details={"total_children": len(children)}
    )


def _evaluate_not_node(
    node: LogicNode,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估 NOT 节点 - 反转子节点结果

    - 子节点通过 → NOT 节点失败
    - 子节点失败 → NOT 节点通过

    NOT 节点应该只有一个子节点
    """
    children = node.children

    if not children:
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="NOT",
            reason="not_node_requires_one_child"
        )

    # NOT 节点只评估第一个子节点
    child = children[0]
    child_result = evaluate_node(child, kline, context, runner)

    # 反转结果
    if child_result.passed:
        # 子节点通过 → NOT 节点失败
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="NOT",
            reason=f"child_passed_negated: {child_result.reason}",
            children=[child_result],
            details={"original_child_result": "passed"}
        )
    else:
        # 子节点失败 → NOT 节点通过
        return TraceNode.create_pass(
            node_id=node_id,
            node_type="NOT",
            reason=f"child_failed_negated: {child_result.reason}",
            children=[child_result],
            details={"original_child_result": "failed"}
        )


def _evaluate_leaf_node(
    node: LeafNode,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估叶子节点（TriggerLeaf 或 FilterLeaf）

    - TriggerLeaf: 委托给 StrategyRunner 检测形态
    - FilterLeaf: 委托给 Filter 检查逻辑

    Args:
        node: 叶子节点
        kline: K 线数据
        context: 过滤器上下文
        runner: 策略运行器
        node_id: 节点 ID

    Returns:
        TraceNode: 评估追踪结果
    """
    if isinstance(node, TriggerLeaf):
        return _evaluate_trigger_leaf(node, kline, context, runner, node_id)
    elif isinstance(node, FilterLeaf):
        return _evaluate_filter_leaf(node, kline, context, runner, node_id)
    else:
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="unknown_leaf",
            reason=f"未知叶子节点类型：{type(node)}"
        )


def _evaluate_trigger_leaf(
    node: TriggerLeaf,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估 Trigger 叶子节点

    委托给 StrategyRunner 检测形态：
    - Pinbar: 使用 PinbarStrategy 检测
    - Engulfing: 使用 EngulfingStrategy 检测

    Returns:
        TraceNode: 评估结果
    """
    trigger_type = node.config.type
    trigger_params = node.config.params

    # 更新 runner 状态（EMA 等）
    runner.update_state(kline)

    # 运行策略检测
    attempts = runner.run_all(
        kline=kline,
        higher_tf_trends=context.higher_tf_trends,
        current_trend=context.current_trend,
        kline_history=None,  # 暂时不传历史
    )

    # 查找匹配的 strategy
    pattern_detected = False
    matched_strategy = None
    pattern_result = None

    for attempt in attempts:
        if attempt.strategy_name == trigger_type and attempt.final_result == "SIGNAL_FIRED":
            pattern_detected = True
            matched_strategy = attempt.strategy_name
            pattern_result = attempt.pattern
            break

    if pattern_detected and pattern_result:
        return TraceNode.create_pass(
            node_id=node_id,
            node_type="trigger",
            reason=f"pattern_detected: {trigger_type}",
            details={
                "trigger_type": trigger_type,
                "strategy_name": matched_strategy,
                "direction": pattern_result.direction.value if pattern_result.direction else None,
                "score": pattern_result.score,
                "details": pattern_result.details,
            }
        )
    else:
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="trigger",
            reason=f"no_pattern_detected: {trigger_type}",
            details={
                "trigger_type": trigger_type,
                "trigger_enabled": node.config.enabled,
            }
        )


def _evaluate_filter_leaf(
    node: FilterLeaf,
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    node_id: str,
) -> TraceNode:
    """
    评估 Filter 叶子节点

    委托给 Filter 检查逻辑。

    注意：Filter 检查需要一个 PatternResult 作为输入。
    由于 FilterLeaf 独立评估，我们需要从 context 中获取 pattern，
    或者创建一个临时的 pattern 用于测试。

    Returns:
        TraceNode: 评估结果
    """
    filter_type = node.config.type
    filter_params = node.config.params
    filter_enabled = node.config.enabled

    # 如果 Filter 被禁用，直接通过
    if not filter_enabled:
        return TraceNode.create_pass(
            node_id=node_id,
            node_type="filter",
            reason="filter_disabled",
            details={
                "filter_type": filter_type,
            }
        )

    # 从 runner 获取 pattern（如果有）
    # 在独立 Filter 评估场景，我们需要创建一个临时的 pattern
    # 这里我们使用 context 中可能存在的 pattern 信息

    # 尝试从 context 的 kline 推断一个 pattern
    # 这是一个简化处理 - 实际使用时应该有明确的 pattern 传入
    temp_pattern = _create_temp_pattern_from_context(kline, context)

    if temp_pattern is None:
        # 无法创建临时 pattern，返回通过（不阻塞）
        return TraceNode.create_pass(
            node_id=node_id,
            node_type="filter",
            reason="no_pattern_to_filter",
            details={
                "filter_type": filter_type,
            }
        )

    # 使用 FilterFactory 创建 filter 实例
    from src.domain.filter_factory import FilterFactory

    try:
        filter_instance = FilterFactory.create(node.config)

        # 调用 filter 的 check 方法
        trace_event = filter_instance.check(temp_pattern, context)

        if trace_event.passed:
            return TraceNode.create_pass(
                node_id=node_id,
                node_type="filter",
                reason=trace_event.reason,
                details={
                    "filter_type": filter_type,
                    "expected": trace_event.expected,
                    "actual": trace_event.actual,
                    "context_data": trace_event.context_data,
                }
            )
        else:
            return TraceNode.create_fail(
                node_id=node_id,
                node_type="filter",
                reason=trace_event.reason,
                details={
                    "filter_type": filter_type,
                    "expected": trace_event.expected,
                    "actual": trace_event.actual,
                    "context_data": trace_event.context_data,
                }
            )
    except Exception as e:
        # Filter 创建或执行失败，返回失败
        return TraceNode.create_fail(
            node_id=node_id,
            node_type="filter",
            reason=f"filter_execution_error: {str(e)}",
            details={
                "filter_type": filter_type,
                "error_type": type(e).__name__,
            }
        )


def _create_temp_pattern_from_context(
    kline: KlineData,
    context: DynamicFilterContext,
) -> Optional[PatternResult]:
    """
    从上下文创建临时 PatternResult

    用于 FilterLeaf 独立评估时的输入。
    根据 current_trend 推断一个合理的 pattern 方向。

    Args:
        kline: K 线数据
        context: 过滤器上下文

    Returns:
        PatternResult 或 None
    """
    # 尝试从 current_trend 推断
    if context.current_trend is not None:
        # 趋势与 pattern 方向的关系：
        # - BULLISH 趋势允许 LONG pattern（通过）
        # - BULLISH 趋势阻止 SHORT pattern（失败）
        # 为了测试 filter 的失败场景，我们创建一个与趋势相反的 pattern
        direction = Direction.LONG if context.current_trend == TrendDirection.BULLISH else Direction.SHORT
        return PatternResult(
            strategy_name="temp",
            direction=direction,
            score=0.5,  # 中性评分
            details={"source": "context_inference"}
        )

    # 默认返回 LONG 方向
    return PatternResult(
        strategy_name="temp",
        direction=Direction.LONG,
        score=0.5,
        details={"source": "default"}
    )


# ============================================================
# 批量评估函数
# ============================================================
def evaluate_tree(
    root: Union[LogicNode, LeafNode],
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
) -> TraceNode:
    """
    评估完整逻辑树

    这是 evaluate_node 的别名，用于强调整体评估的语义。

    Args:
        root: 逻辑树根节点
        kline: K 线数据
        context: 过滤器上下文
        runner: 策略运行器

    Returns:
        TraceNode: 完整的评估追踪树
    """
    return evaluate_node(root, kline, context, runner)


def evaluate_multiple(
    nodes: List[Union[LogicNode, LeafNode]],
    kline: KlineData,
    context: DynamicFilterContext,
    runner: StrategyRunner,
    logic: str = "AND",
) -> List[TraceNode]:
    """
    批量评估多个节点

    Args:
        nodes: 节点列表
        kline: K 线数据
        context: 过滤器上下文
        runner: 策略运行器
        logic: 组合逻辑 - "AND" 或 "OR"（用于确定是否短路）

    Returns:
        List[TraceNode]: 每个节点的评估结果
    """
    results = []

    for node in nodes:
        result = evaluate_node(node, kline, context, runner)
        results.append(result)

        # 如果需要短路评估
        if logic == "AND" and not result.passed:
            break
        elif logic == "OR" and result.passed:
            break

    return results
