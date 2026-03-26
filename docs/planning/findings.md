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

---

## 第二阶段研究发现（2026-03-26）

### 系统状态验证结果

**已完成功能**:
1. 递归逻辑树引擎 - `src/domain/logic_tree.py` + `src/domain/recursive_engine.py` ✅
2. 热预览接口 - `POST /api/strategies/preview` ✅
3. 前端递归组件 - `NodeRenderer.tsx`, `LogicGateControl.tsx`, `LeafNodeForm.tsx` ✅
4. Trace 树可视化 - `TraceTreeViewer.tsx` ✅
5. 策略模板 CRUD - `GET/POST/PUT/DELETE /api/strategies` ✅
6. 策略元数据接口 - `GET /api/strategies/meta` ✅

**待完成功能**:
1. 一键下发实盘 - 策略模板应用到实盘监控
2. 信号标签动态化 - 移除 `ema_trend`/`mtf_status` 硬编码
3. 前端硬编码组件清理 - 确认是否还有遗留

### 技术债清单

| 编号 | 问题 | 影响范围 | 优先级 |
|------|------|----------|--------|
| #1 | TraceEvent 字段命名不一致 | 前后端数据对齐 | 高 |
| #2 | SignalResult 硬编码标签 | 通知卡片动态化 | 高 |
| #3 | FilterConfig.params 为 Dict[str, Any] | API 类型安全 | 中 |
| #4 | 前端可能还有硬编码组件 | Schema 驱动纯度 | 中 |

### 下一阶段技术方案

### 下一阶段技术方案

**一键下发实盘方案**:
```
用户操作：选择模板 → 点击"应用"
    ↓
前端：POST /api/strategies/{id}/apply
    ↓
后端：
  1. 从数据库加载策略模板
  2. 反序列化为 StrategyDefinition
  3. 调用 ConfigManager 更新 user_config
  4. 触发信号管道热重载
  5. 回填 K 线状态（200+ 根）
    ↓
响应：{ success: true, message: "策略已应用" }
```

**关键实现点**:
- 使用 `asyncio.Lock()` 保护配置替换过程
- 原子操作：先创建新 Runner，再替换指针
- 状态回填：从交易所拉取历史 K 线

**信号标签动态化方案**:
```
旧流程:
  process_kline → _legacy_engine.get_ema_trend() → SignalResult(ema_trend="Bullish")

新流程:
  process_kline → 从 attempt.filter_results 提取通过的过滤器
               → 生成 tags = [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
               → SignalResult(tags=...)
```

**热重载并发控制**:
```python
class SignalPipeline:
    def __init__(self):
        self._runner_lock = asyncio.Lock()  # 互斥锁
        self._attempts_queue = asyncio.Queue()  # 异步背压队列

    async def on_config_updated(self, new_config):
        async with self._runner_lock:
            # 重建 Runner
            self._runner = create_dynamic_runner(new_config)
            # 预热：用历史 K 线恢复状态
            await self._warmup_runner(self._kline_history)
        # 清空冷却缓存
        self._signal_cooldown_cache.clear()

    async def _flush_attempts_worker(self):
        """后台 Worker 批量落盘，避免阻塞主事件循环"""
        while True:
            attempts = await self._attempts_queue.get_batch()
            await self._repository.save_batch(attempts)
```

### 相关文件参考

- `docs/tasks/2026-03-25-子任务 B-策略工作台与 CRUD 接口开发.md` - 策略模板库设计
- `docs/tasks/2026-03-25-子任务 C-信号结果动态标签系统重构.md` - 信号标签动态化
- `docs/tasks/2026-03-25-子任务 A-实盘引擎热重载与稳定性重构.md` - 热重载机制
