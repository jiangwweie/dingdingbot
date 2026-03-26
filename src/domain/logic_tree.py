"""
递归逻辑树类型定义

用于定义动态策略引擎的递归逻辑结构，支持：
- AND/OR/NOT 逻辑门
- Trigger 和 Filter 叶子节点
- Discriminator Union 类型区分
- 嵌套深度限制 ≤ 3
"""
from typing import Union, List, Annotated, Literal, Optional
from pydantic import BaseModel, Field, model_validator, ValidationError
from pydantic import field_validator

from src.domain.models import TriggerConfig, FilterConfig


# ============================================================
# 枚举类型
# ============================================================
class GateType(str):
    """逻辑门类型"""
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


# ============================================================
# 叶子节点 (Leaf Nodes)
# ============================================================
class TriggerLeaf(BaseModel):
    """Trigger 叶子节点"""
    type: Literal["trigger"] = "trigger"
    id: str = Field(..., description="叶子节点唯一标识")
    config: TriggerConfig = Field(..., description="Trigger 配置")


class FilterLeaf(BaseModel):
    """Filter 叶子节点"""
    type: Literal["filter"] = "filter"
    id: str = Field(..., description="叶子节点唯一标识")
    config: FilterConfig = Field(..., description="Filter 配置")


# ============================================================
# LeafNode 联合类型 (使用 Discriminator)
# ============================================================
# 定义内部 Union 类型供 isinstance 检查使用
_LeafNodeUnion = Union[TriggerLeaf, FilterLeaf]

LeafNode = Annotated[
    _LeafNodeUnion,
    Field(discriminator="type")
]


# ============================================================
# 递归 LogicNode 定义
# ============================================================
class LogicNode(BaseModel):
    """
    递归逻辑节点

    支持 AND/OR/NOT 逻辑门，子节点可以是：
    - 其他 LogicNode（内部节点）
    - LeafNode（TriggerLeaf 或 FilterLeaf）

    嵌套深度限制为 ≤ 3
    """
    gate: Literal["AND", "OR", "NOT"] = Field(..., description="逻辑门类型")
    children: List[Union["LogicNode", LeafNode]] = Field(
        default_factory=list,
        description="子节点列表"
    )

    @model_validator(mode="after")
    def check_depth(self) -> "LogicNode":
        """
        验证嵌套深度不超过 3

        深度计算规则：
        - 根节点深度为 1
        - 每增加一层子 LogicNode，深度 +1
        - LeafNode 不增加深度
        """
        max_depth = self._calculate_depth(self)
        if max_depth > 3:
            raise ValueError(
                f"LogicNode 嵌套深度不能超过 3，当前深度：{max_depth}"
            )
        return self

    @staticmethod
    def _calculate_depth(node: Union["LogicNode", "TriggerLeaf", "FilterLeaf"]) -> int:
        """
        递归计算节点深度

        Args:
            node: LogicNode 或 LeafNode

        Returns:
            从该节点开始的最大深度
        """
        if isinstance(node, (TriggerLeaf, FilterLeaf)):
            return 0

        if not node.children:
            return 1

        max_child_depth = 0
        for child in node.children:
            child_depth = LogicNode._calculate_depth(child)
            max_child_depth = max(max_child_depth, child_depth)

        return 1 + max_child_depth

    def get_depth(self) -> int:
        """获取当前节点的深度"""
        return self._calculate_depth(self)


# ============================================================
# 辅助函数
# ============================================================
def create_trigger_leaf(trigger_config: TriggerConfig) -> TriggerLeaf:
    """
    创建 Trigger 叶子节点

    Args:
        trigger_config: Trigger 配置

    Returns:
        TriggerLeaf 实例
    """
    return TriggerLeaf(
        type="trigger",
        id=trigger_config.id,
        config=trigger_config
    )


def create_filter_leaf(filter_config: FilterConfig) -> FilterLeaf:
    """
    创建 Filter 叶子节点

    Args:
        filter_config: Filter 配置

    Returns:
        FilterLeaf 实例
    """
    return FilterLeaf(
        type="filter",
        id=filter_config.id,
        config=filter_config
    )


def create_and_node(*children: Union["LogicNode", LeafNode]) -> LogicNode:
    """
    创建 AND 逻辑节点

    Args:
        *children: 子节点列表

    Returns:
        LogicNode 实例
    """
    return LogicNode(gate="AND", children=list(children))


def create_or_node(*children: Union["LogicNode", LeafNode]) -> LogicNode:
    """
    创建 OR 逻辑节点

    Args:
        *children: 子节点列表

    Returns:
        LogicNode 实例
    """
    return LogicNode(gate="OR", children=list(children))


def create_not_node(child: Union["LogicNode", LeafNode]) -> LogicNode:
    """
    创建 NOT 逻辑节点

    Args:
        child: 单个子节点

    Returns:
        LogicNode 实例
    """
    return LogicNode(gate="NOT", children=[child])
