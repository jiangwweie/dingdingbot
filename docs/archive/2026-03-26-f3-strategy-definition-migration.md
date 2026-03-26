# F-3 阶段：StrategyDefinition 迁移设计

> **创建日期**: 2026-03-26
> **状态**: 已批准
> **阶段**: F-3 - 升级 StrategyDefinition

---

## 目标

将 `StrategyDefinition` 从平铺式 `triggers/filters` 列表升级为递归 `logic_tree` 结构，同时保持向后兼容性。

---

## 架构决策

### 1. 向后兼容策略：**双轨并行**

同时支持新旧两种格式，旧格式自动迁移到新格式。

**旧格式**：
```json
{
  "name": "pinbar_basic",
  "triggers": [{"type": "pinbar", "params": {...}}],
  "filters": [{"type": "ema", "params": {...}}],
  "trigger_logic": "OR",
  "filter_logic": "AND"
}
```

**新格式**：
```json
{
  "name": "pinbar_basic",
  "logic_tree": {
    "gate": "AND",
    "children": [
      {"gate": "OR", "children": [trigger_leafs...]},
      {"gate": "AND", "children": [filter_leafs...]}
    ]
  }
}
```

### 2. 模型设计：**添加 `logic_tree` 字段**

在现有 `StrategyDefinition` 中添加 `logic_tree` 字段，保留旧字段用于向后兼容。

```python
class StrategyDefinition(BaseModel):
    # 新字段（推荐）
    logic_tree: Optional[Union[LogicNode, LeafNode]] = None

    # 旧字段（保留，废弃）
    triggers: List[TriggerConfig] = []
    filters: List[FilterConfig] = []
    trigger_logic: Literal["AND", "OR"] = "OR"
    filter_logic: Literal["AND", "OR"] = "AND"
```

### 3. 迁移时机：**Pydantic 模型验证器**

在 `model_validator(mode="after")` 中自动执行迁移。

---

## 实现方案

### 核心代码结构

```python
from typing import Union, Optional, List, Literal
from pydantic import BaseModel, Field, model_validator
import warnings

class StrategyDefinition(BaseModel):
    """
    策略定义（支持新旧格式）

    新格式使用 logic_tree 字段（推荐）
    旧格式使用 triggers/filters 字段（已废弃，自动迁移）
    """
    id: str = Field(default_factory=lambda: "")
    name: str = Field(..., description="策略名称")

    # ===== 新字段（推荐）=====
    logic_tree: Optional[Union[LogicNode, LeafNode]] = Field(
        default=None,
        description="递归逻辑树（推荐）"
    )

    # ===== 旧字段（已废弃，保留用于向后兼容）=====
    triggers: List[TriggerConfig] = Field(default_factory=list)
    trigger_logic: Literal["AND", "OR"] = Field(default="OR")
    filters: List[FilterConfig] = Field(default_factory=list)
    filter_logic: Literal["AND", "OR"] = Field(default="AND")

    # 环境作用域
    is_global: bool = Field(default=True)
    apply_to: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def migrate_legacy(self) -> "StrategyDefinition":
        """
        如果 logic_tree 为空且存在旧字段，自动迁移
        """
        if self.logic_tree is None and (self.triggers or getattr(self, 'trigger', None)):
            warnings.warn(
                f"Strategy '{self.name}' 使用已废弃的 triggers/filters 字段，"
                f"将自动迁移到 logic_tree。请使用 logic_tree 字段。",
                DeprecationWarning,
                stacklevel=2
            )
            self.logic_tree = self._build_from_legacy()
        return self

    def _build_from_legacy(self) -> Union[LogicNode, LeafNode]:
        """
        从旧字段构建逻辑树

        构建逻辑：
        1. 单个 trigger → 直接使用 TriggerLeaf
        2. 多个 trigger → 用 trigger_logic 组合
        3. 单个 filter → 直接使用 FilterLeaf
        4. 多个 filter → 用 filter_logic 组合
        5. trigger 组 AND filter 组 → AND 组合
        """
        from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf

        children = []

        # 构建 trigger 部分
        if self.triggers:
            trigger_leafs = [
                TriggerLeaf(type="trigger", id=t.id, config=t)
                for t in self.triggers
            ]
            if len(trigger_leafs) == 1:
                children.append(trigger_leafs[0])
            else:
                children.append(LogicNode(
                    gate=self.trigger_logic,
                    children=trigger_leafs
                ))

        # 构建 filter 部分
        if self.filters:
            filter_leafs = [
                FilterLeaf(type="filter", id=f.id, config=f)
                for f in self.filters
            ]
            if len(filter_leafs) == 1:
                children.append(filter_leafs[0])
            else:
                children.append(LogicNode(
                    gate=self.filter_logic,
                    children=filter_leafs
                ))

        # 合并
        if len(children) == 0:
            raise ValueError(f"Strategy '{self.name}' 必须至少有一个 trigger 或 filter")
        if len(children) == 1:
            return children[0]
        return LogicNode(gate="AND", children=children)
```

---

## 迁移测试用例

```python
class TestStrategyDefinitionMigration:
    """测试迁移逻辑"""

    def test_migrate_single_trigger(self):
        """测试单 Trigger 迁移"""
        strat = StrategyDefinition(
            name="test",
            triggers=[TriggerConfig(id="t1", type="pinbar", ...)]
        )
        assert strat.logic_tree.type == "trigger"
        assert strat.logic_tree.config.type == "pinbar"

    def test_migrate_multiple_triggers_or(self):
        """测试多 Trigger OR 迁移"""
        strat = StrategyDefinition(
            name="test",
            triggers=[t1, t2],
            trigger_logic="OR"
        )
        assert strat.logic_tree.gate == "OR"
        assert len(strat.logic_tree.children) == 2

    def test_migrate_with_filters(self):
        """测试带 Filter 迁移"""
        strat = StrategyDefinition(
            name="test",
            triggers=[t1],
            filters=[f1, f2],
            filter_logic="AND"
        )
        # 顶层应该是 AND（trigger 组 AND filter 组）
        assert strat.logic_tree.gate == "AND"
        assert len(strat.logic_tree.children) == 2

    def test_logic_tree_priority(self):
        """测试 logic_tree 优先于旧字段"""
        custom_tree = LogicNode(gate="OR", children=[...])
        strat = StrategyDefinition(
            name="test",
            logic_tree=custom_tree,  # 显式指定
            triggers=[t1]  # 旧字段应忽略
        )
        assert strat.logic_tree == custom_tree

    def test_no_warning_with_logic_tree(self):
        """测试使用 logic_tree 时不触发警告"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            strat = StrategyDefinition(
                name="test",
                logic_tree=some_tree
            )
            assert len(w) == 0
```

---

## 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/domain/models.py` | 修改 | 更新 `StrategyDefinition` 添加 `logic_tree` 字段和迁移验证器 |
| `tests/unit/test_models.py` | 创建 | 迁移逻辑单元测试 |
| `src/domain/strategy_engine.py` | 修改 | `create_dynamic_runner()` 直接使用 `logic_tree` 字段 |

---

## 验收标准

- [ ] `StrategyDefinition` 支持 `logic_tree` 字段
- [ ] 旧格式自动迁移到新格式
- [ ] 迁移时触发 `DeprecationWarning`
- [ ] `logic_tree` 优先于旧字段
- [ ] 单元测试覆盖所有迁移场景
- [ ] `create_dynamic_runner()` 直接使用 `logic_tree`
- [ ] 向后兼容测试通过

---

## 相关文件

- `src/domain/logic_tree.py` - 递归类型定义
- `src/domain/recursive_engine.py` - 递归评估引擎
- `src/domain/models.py` - 数据模型
- `src/domain/strategy_engine.py` - 策略引擎

---

## 设计批准

- [x] 设计已批准
- [ ] 实现计划已创建
- [ ] 实现已完成
