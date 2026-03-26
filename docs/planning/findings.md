# 研究发现

## 子任务 F - 递归逻辑树引擎

### 技术要点

1. **Pydantic 递归模型**
   - 使用 `from __future__ import annotations` 启用字符串自引用
   - 使用 `Annotated[Union[...], Field(discriminator='type')]` 实现多态
   - 使用 `model_validator` 限制递归深度

2. **Discriminator Union**
   - 自动类型识别基于 `type` 字段
   - 支持运行时类型缩窄

3. **递归评估算法**
   - 深度优先遍历
   - AND 节点：`all()` 短路
   - OR 节点：`any()` 短路
   - NOT 节点：结果反转

### 现有代码分析

**当前策略引擎** (`src/domain/strategy_engine.py`):
- `DynamicStrategyRunner` - 平铺式 runner
- `StrategyWithFilters` - 平铺过滤器链
- `create_dynamic_runner()` - 工厂函数

**当前数据模型** (`src/domain/models.py`):
- `StrategyDefinition` - 平铺的 `triggers` 和 `filters` 列表
- `TriggerConfig` - 触发器配置
- `FilterConfig` - 过滤器配置

### 需要创建的新文件

```
src/domain/
├── logic_tree.py          # 递归类型定义
├── recursive_engine.py    # 递归评估引擎
└── ...

tests/unit/
└── test_recursive_engine.py  # 递归引擎测试
```

---

## 子任务 E - 前端递归渲染

### 技术要点

1. **React 递归组件**
   - 组件调用自身处理子节点
   - 使用 `depth` prop 控制缩进和样式

2. **Schema 驱动表单**
   - 从后端 API 获取 JSON Schema
   - 动态生成输入控件

3. **Trace 树可视化**
   - 与逻辑树同构的结果树
   - 成功/失败状态标记

### 现有前端分析

**当前组件** (`web-front/src/components/`):
- `StrategyBuilder.tsx` - 硬编码平铺组件
- 各种 `*Editor.tsx` - 死板的参数编辑器

**需要删除**:
- `StrategyBuilder.tsx`
- `PinbarParamsEditor.tsx`
- `EmaFilterEditor.tsx`
- 等 10+ 个硬编码组件

### 需要创建的新文件

```
web-front/src/components/
├── NodeRenderer.tsx       # 递归渲染器
├── LogicGateControl.tsx   # 逻辑门控制
└── LeafNodeForm.tsx       # 叶子节点表单
```

---

## 参考资料

### Pydantic 递归模型
- https://docs.pydantic.dev/latest/usage/postponed_annotations/#self-referencing-models
- https://docs.pydantic.dev/latest/usage/types/unions/#discriminated-unions

### React 递归组件
- https://react.dev/learn/passing-data-deeply-context
- https://advanced-react.com/advanced-patterns/recursion
