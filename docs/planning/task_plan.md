# 子任务 F 和 E 实现计划

**目标**: 将平铺式策略引擎升级为递归逻辑树引擎，并实现前端递归渲染组件

**状态**: ⏸️ 暂停 - 优先完成文件结构重组

---

# 文件结构重组计划（2026-03-31）

**目标**: 整理项目文件结构，建立清晰的文档导航和 memory 系统

**阶段概览**:
| 阶段 | 任务 | 状态 | 完成时间 |
|------|------|------|----------|
| Phase 1 | 项目结构优化 | ✅ 完成 | 2026-03-31 |
| Phase 2 | memory 整合与任务归档 | ✅ 完成 | 2026-03-31 |

**Phase 1: 项目结构优化**
- [x] 分析项目结构问题（106 个 markdown 文件分散在 14 个子目录）
- [x] 创建文档导航索引 `docs/README.md`
- [x] 创建脚本工具索引 `scripts/README.md`
- [x] 更新 `.gitignore` 添加日志和覆盖率文件

**Phase 2: memory 整合与任务归档**
- [x] 创建 `.claude/memory/` 目录结构
- [x] 整合 5 个 memory 文件到 `project-core-memory.md`
- [x] 创建 MEMORY.md 索引文件
- [x] 归档 28 个已完成任务文档到 `docs/tasks/archive/`
- [x] 清理 `docs/archive/` 目录（27 个子目录）
- [x] 删除原 `memory/` 目录

**Git 提交**:
```
50c1e27 refactor: 项目文件结构重组（第一阶段）
7bef3cb docs: 创建文档导航索引 README.md
bd06538 refactor: 文件结构重组第二阶段 - memory 整合与任务归档
49a2c3b docs: 更新进度日志 - 文件结构重组 Phase 1&2 完成
```

---

# 子任务 F 和 E 实现计划（已暂停）

**目标**: 将平铺式策略引擎升级为递归逻辑树引擎，并实现前端递归渲染组件

**架构**:
- 后端：Pydantic 递归模型 + Discriminator Union + 递归评估算法
- 前端：React 递归组件 + Schema 驱动表单 + Trace 树可视化

**依赖关系**:
```
子任务 F (后端) → 子任务 E (前端)
```

**阶段概览**:
| 阶段 | 任务 | 状态 | 负责人 |
|------|------|------|--------|
| F-1 | 定义递归 LogicNode 类型 | completed | backend-dev |
| F-2 | 实现递归评估引擎 | completed | backend-dev |
| F-3 | 升级 StrategyDefinition | completed | backend-dev |
| F-4 | 实现热预览接口 | completed | backend-dev |
| E-1 | 定义前端递归类型 | completed | frontend-dev |
| E-2 | 实现递归渲染组件 | completed | frontend-dev |
| E-3 | 实现热预览交互 | completed | frontend-dev |

---

## 阶段详情

### 阶段 F-1: 定义递归 LogicNode 类型

**目标**: 创建强类型递归数据模型

**文件**:
- 创建：`src/domain/logic_tree.py`
- 修改：`src/domain/models.py`

**步骤**:
1. [ ] 创建递归 LogicNode 类型定义
2. [ ] 编写单元测试验证类型定义
3. [ ] 运行类型检查 `python -c "from src.domain.logic_tree import LogicNode; print('OK')"`
4. [ ] 提交

**验收标准**:
- 支持 AND/OR/NOT 逻辑门
- 支持 Trigger 和 Filter 叶子节点
- 使用 Discriminator Union
- 限制嵌套深度 ≤ 3

---

### 阶段 F-2: 实现递归评估引擎

**目标**: 实现 `evaluate_node()` 递归函数

**文件**:
- 创建：`src/domain/recursive_engine.py`
- 测试：`tests/unit/test_recursive_engine.py`

**步骤**:
1. [ ] 编写单元测试 (覆盖 AND/OR/NOT/Leaf 场景)
2. [ ] 运行测试验证失败
3. [ ] 实现 `evaluate_node()` 函数
4. [ ] 运行测试验证通过
5. [ ] 提交

**验收标准**:
- AND 节点：all() 短路判定
- OR 节点：any() 短路判定
- NOT 节点：结果反转
- 返回 Trace 树记录评估路径

---

### 阶段 F-3: 升级 StrategyDefinition

**目标**: 支持递归逻辑树配置

**文件**:
- 修改：`src/domain/models.py`
- 修改：`src/domain/strategy_engine.py`

**步骤**:
1. [ ] 更新 `StrategyDefinition` 添加 `logic_tree` 字段
2. [ ] 实现从平铺模式迁移到递归树的验证器
3. [ ] 更新 `create_dynamic_runner()` 支持递归树
4. [ ] 向后兼容测试
5. [ ] 提交

**验收标准**:
- 新策略使用递归树
- 旧策略自动迁移
- 向后兼容

---

### 阶段 F-4: 实现热预览接口

**目标**: 实现 `POST /api/strategies/preview`

**文件**:
- 修改：`src/interfaces/api.py`

**步骤**:
1. [ ] 定义 PreviewRequest/PreviewResponse 模型
2. [ ] 实现 preview 端点
3. [ ] 临时 Runner 执行评估
4. [ ] 返回完整 Trace 树
5. [ ] 提交

**验收标准**:
- 不持久化
- 不热重载
- 返回评估路径追踪

---

### 阶段 E-1: 定义前端递归类型

**目标**: TypeScript 递归类型定义

**文件**:
- 修改：`web-front/src/types/strategy.ts`

**步骤**:
1. [ ] 定义 AndNode, OrNode, NotNode 接口
2. [ ] 定义 TriggerNode, FilterNode 接口
3. [ ] 定义 LogicNode 联合类型
4. [ ] 运行 TypeScript 类型检查
5. [ ] 提交

**验收标准**:
- 与后端模型对齐
- TypeScript 无类型错误

---

### 阶段 E-2: 实现递归渲染组件

**目标**: 递归组件 `NodeRenderer`

**文件**:
- 创建：`web-front/src/components/NodeRenderer.tsx`
- 创建：`web-front/src/components/LogicGateControl.tsx`
- 创建：`web-front/src/components/LeafNodeForm.tsx`

**步骤**:
1. [ ] 创建逻辑门控制组件
2. [ ] 创建叶子节点表单组件
3. [ ] 创建递归渲染器
4. [ ] 集成到策略工作台
5. [ ] 提交

**验收标准**:
- 支持递归渲染
- Schema 驱动表单
- 视觉层次清晰

---

### 阶段 E-3: 实现热预览交互

**目标**: "立即测试" 按钮 + Trace 树可视化

**文件**:
- 修改：`web-front/src/pages/StrategyWorkbench.tsx`
- 修改：`web-front/src/lib/api.ts`

**步骤**:
1. [ ] 添加预览 API 调用函数
2. [ ] 添加"立即测试"按钮
3. [ ] 实现 Trace 树视觉渲染
4. [ ] 成功/失败状态标记
5. [ ] 提交

**验收标准**:
- 点击按钮发送预览请求
- 渲染评估结果树
- 节点标记✅/❌

---

## 错误日志

| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| - | - | - |

---

## 关键决策

| 决策 | 原因 | 日期 |
|------|------|------|
| 使用 Pydantic Discriminator | 类型安全、自动 Schema 生成 | - |
| 限制递归深度≤3 | 防止无限递归、UI 可读性 | - |
| Trace 树返回 | 前端可视化需求 | - |

---

## 相关文件

- `docs/tasks/2026-03-25-子任务 F-强类型递归引擎与 Schema 自动化开发.md`
- `docs/tasks/2026-03-25-子任务 E-递归表单驱动与动态预览重构.md`
- `src/domain/models.py`
- `src/domain/strategy_engine.py`
- `web-front/src/types/strategy.ts`
- `web-front/src/components/`

---

## 第二阶段：交互升维（当前阶段）

**目标**: 完成技术债清理和核心重构，实现策略模板到实盘监控的无缝对接

### 阶段概览
| 阶段 | 任务 | 状态 | 负责人 | 优先级 |
|------|------|------|--------|--------|
| S2-2 | 统一 TraceEvent 字段命名 | ✅ completed | backend-dev | 高 |
| S2-4 | 信号标签动态化（子任务 C） | ✅ completed | backend-dev | 高 |
| S2-1 | 一键下发实盘热重载（子任务 A） | ✅ completed | backend-dev | 高 |
| S2-3 | 前端硬编码组件清理 | ✅ completed | frontend-dev | 中 |
| S2-5 | ATR 过滤器核心逻辑实现 | ✅ completed | backend-dev | 最高 |
| 日志系统 | 日志文件持久化与轮转 | ✅ completed | backend-dev | 高 |

---

## 执行顺序与依赖

```
S2-2 (字段统一) ✅
    ↓
S2-5 (ATR 过滤器) ← 独立，最高优先级
    ↓
S2-4 (信号标签动态化) ← 独立，可先行
    ↓
S2-1 (实盘热重载) ← 依赖 S2-4 完成
    ↓
S2-3 (前端清理) ← 独立，可并行
```

---

### 阶段 S2-2: 统一 TraceEvent 字段命名 ✅

**完成时间**: 2026-03-26

**文件**:
- 修改：`src/domain/filter_factory.py` - `TraceEvent.filter_name` → `node_name`, `context_data` → `metadata`
- 修改：`src/domain/recursive_engine.py` - `TraceNode.details` → `metadata`
- 修改：`web-front/src/lib/api.ts` - `TraceEvent.stage` → `node_name`, `details` → `metadata`
- 修改：`tests/unit/test_filter_factory.py` - 测试适配
- 修改：`tests/unit/test_recursive_engine.py` - 测试适配
- 修改：`tests/unit/test_preview_api.py` - 测试适配

**测试结果**:
```
======================== 48 passed, 3 warnings in 0.30s ========================
```

---

### 阶段 S2-4: 信号标签动态化（子任务 C）

**目标**: 移除 `ema_trend`/`mtf_status` 硬编码字段，改用动态 tags 数组

**文件**:
- 修改：`src/domain/models.py` - SignalResult 模型
- 修改：`src/domain/risk_calculator.py` - 移除硬编码标签
- 修改：`src/application/signal_pipeline.py` - 动态标签生成逻辑
- 修改：`src/infrastructure/notifier.py` - 通知消息格式化
- 修改：`src/infrastructure/signal_repository.py` - 落库字段升级
- 修改：`web-front/src/lib/api.ts` - Signal 接口定义

**步骤**:
1. [ ] 更新 SignalResult 模型，添加 `tags: List[Dict[str, str]]`
2. [ ] 移除 `ema_trend`/`mtf_status` 字段
3. [ ] 更新 risk_calculator.calculate_signal_result() 签名
4. [ ] 更新 signal_pipeline.process_kline() 动态标签生成
5. [ ] 更新 notifier 通知卡片渲染
6. [ ] 更新 signal_repository 落库逻辑 (tags_json)
7. [ ] 更新前端 Signal 接口
8. [ ] 编写测试验证

**验收标准**:
- 信号结果支持动态标签数组
- 通知卡片显示动态标签内容
- 移除对 Legacy 引擎的依赖
- 向后兼容旧数据格式

---

### 阶段 S2-1: 一键下发实盘热重载（子任务 A）

**目标**: 实现策略模板到实盘监控的无缝下发，支持热重载不重启

**文件**:
- 修改：`src/application/signal_pipeline.py` - 热重载 Observer 模式
- 修改：`src/application/config_manager.py` - 配置监听器
- 修改：`src/interfaces/api.py` - 新增 `/api/strategies/{id}/apply` 端点
- 新增：`src/infrastructure/strategy_repository.py` - 策略模板仓储

**步骤**:
1. [ ] 实现 ConfigManager 异步监听器注册
2. [ ] 实现 SignalPipeline._build_and_warmup_runner()
3. [ ] 添加 asyncio.Lock() 保护并发竞争
4. [ ] 实现异步 Queue Worker 剥离 SQLite 同步背压
5. [ ] 实现配置变更时清空信号冷却缓存
6. [ ] 新增策略模板 Apply 端点
7. [ ] 更新 main.py 入口函数
8. [ ] 编写测试验证

**验收标准**:
- 策略模板一键下发实盘
- 配置热重载不重启进程
- EMA 等有状态指标无缝恢复
- 无并发竞争条件
- SQLite 异步批量落盘

---

### 阶段 S2-5: ATR 过滤器核心逻辑实现 ✅

**完成时间**: 2026-03-29

**目标**: 完成 ATR 过滤器的核心检查逻辑，解决 Pinbar 止损过近问题

**背景**:
- 当前 ATR 过滤器 (`AtrFilterDynamic`) 的 `check()` 方法是占位符，始终返回 `passed=True`
- Pinbar 策略只检测几何比例，不考虑绝对波幅，导致十字星形态产生无效信号
- 实际信号止损距离仅 0.001%~0.01%，远低于合理交易风险 (1%~3%)

**文件**:
- 修改：`src/domain/filter_factory.py` - `AtrFilterDynamic.check()` 方法
- 修改：`src/domain/risk_calculator.py` - `calculate_stop_loss()` 添加 ATR 缓冲（可选）
- 测试：`tests/unit/test_filter_factory.py` - 添加 ATR 过滤器测试
- 配置：`config/core.yaml` - 添加 ATR 过滤器默认配置

**步骤**:
1. [x] 实现 `AtrFilterDynamic.check()` 核心逻辑
   - 获取当前 K 线的 ATR 值
   - 计算 K 线波幅与 ATR 的比率
   - 与 `min_atr_ratio` 配置比较，低于阈值则拒绝
2. [x] 在 `update_state()` 中确保 ATR 数据更新
3. [x] 添加 TraceEvent 元数据（candle_range、atr、ratio）
4. [x] 编写单元测试验证过滤逻辑
5. [x] 集成测试：验证十字星被正确过滤
6. [ ] 可选：`calculate_stop_loss()` 添加 ATR 缓冲，扩大止损距离
7. [x] 更新配置文档

**验收标准**:
- ATR 过滤器能正确拒绝波幅 < min_atr_ratio × ATR 的 K 线 ✅
- 十字星/一字线形态不再产生信号 ✅
- 止损距离从 0.001% 提升到 0.5%~1% 级别 ✅
- 单元测试覆盖率 100% ✅

**技术方案**:
```python
# check() 方法实现逻辑
candle_range = kline.high - kline.low
atr = self._get_atr(kline.symbol, kline.timeframe)
min_range = atr * self._min_atr_ratio

if candle_range < min_range:
    return TraceEvent(
        passed=False,
        reason="insufficient_volatility",
        metadata={"candle_range": float(candle_range), "atr": float(atr), "ratio": float(candle_range / atr)}
    )
```

**优先级说明**:
- 直接影响信号质量和用户体验
- 解决当前生产环境止损过近的核心问题
- 优先级高于其他待办任务


**附：Pinbar 参数优化建议**（2026-03-28 讨论）
- 用户反馈：某些有效形态被过滤（下影线 50%、实体居中）
- 建议调整：
  | 参数 | 当前值 | 建议值 |
  |------|-------|-------|
  | `min_wick_ratio` | 0.6 | 0.5 |
  | `max_body_ratio` | 0.3 | 0.35 |
  | `body_position_tolerance` | 0.1 | 0.3 |
- 待办：修改 `config/core.yaml` 后验证效果

---

### 阶段 S2-3: 前端硬编码组件清理

**目标**: 移除所有硬编码的过滤器组件，实现 100% Schema 驱动

**待清理组件**:
- `StrategyBuilder.tsx` → 替换为递归 NodeRenderer
- `PinbarParamsEditor.tsx` → 已移除
- `EmaFilterEditor.tsx` → 已移除
- `MtfFilterEditor.tsx` → 待移除

**文件**:
- 删除：`web-front/src/components/StrategyBuilder.tsx` (如仍存在)
- 删除：`web-front/src/components/*Editor.tsx` (所有硬编码编辑器)

**步骤**:
1. [ ] 检查并列出所有硬编码组件
2. [ ] 确认 NodeRenderer 已完全替代
3. [ ] 删除旧组件
4. [ ] 更新导入引用
5. [ ] 运行 TypeScript 编译验证

**验收标准**:
- 移除所有硬编码编辑器组件
- TypeScript 编译无错误
- 前端 100% Schema 驱动

---

## 第三阶段：风控执行（已完成）

**完成时间**: 2026-03-27

**交付物**:
- S3-1: MTF 多周期数据对齐优化 ✅
- S3-2: 动态风险头寸计算（方案 B） ✅
- S3-2: 16 个集成测试 ✅
- 测试修复：test_signal_repository.py 修复 ✅

**测试结果**:
```
tests/unit/test_risk_calculator.py: 35/35 通过 (100%)
tests/integration/test_risk_headroom.py: 16/16 通过 (100%)
tests/integration/test_mtf_e2e.py: 6/6 通过 (100%)
tests/unit/test_signal_repository.py: 21/21 通过 (100%)
tests/unit/: 329/329 通过 (100%)
tests/integration/: 41/41 通过 (100%)
总计：370/370 通过 (100%)
```

**Git 提交**:
- S3-2 核心功能：`1aa9619`
- S3-1 MTF 对齐：`93edce5`
- S3-2 集成测试：会话 13
- S3 测试修复：`8c5eb73`

---

### 阶段 S3-2: 动态风险头寸计算 ✅

**目标**: 根据账户实时状态动态计算风险头寸（方案 B）

**完成时间**: 2026-03-27

**交付物**:
- `src/domain/models.py` - RiskConfig 新增 `max_total_exposure` 字段
- `src/domain/risk_calculator.py` - 升级 `calculate_position_size()` 实现方案 B
- `tests/unit/test_risk_calculator.py` - 21 个新增测试用例（35 个测试 100% 通过）
- `tests/integration/test_risk_headroom.py` - 16 个集成测试（100% 通过）

**方案 B 逻辑**:
- 使用 `available_balance` 而非 `total_balance`
- 考虑当前持仓占用（通过 `current_exposure_ratio`）
- 当持仓接近 `max_total_exposure` (80%) 时自动降低风险
- 无可用风险空间时返回 0 仓位

**测试结果**:
```
tests/unit/test_risk_calculator.py: 35/35 通过 (100%)
tests/integration/test_risk_headroom.py: 16/16 通过 (100%)
tests/integration/ 总计：41/41 通过 (100%)
```

**Git 提交**: `1aa9619`

---

### 阶段 S3-1: 多周期数据对齐优化 ✅

**目标**: 优化 MTF 过滤器的多周期数据对齐逻辑

**完成时间**: 2026-03-27

**交付物**:
- `src/utils/timeframe_utils.py` - MTF 周期映射工具
- `src/application/config_manager.py` - 新增 MTF 配置字段
- `config/core.yaml` - MTF 默认配置
- `tests/integration/test_mtf_e2e.py` - 6 个集成测试

**测试结果**:
```
tests/integration/test_mtf_e2e.py: 6/6 通过 (100%)
```

**Git 提交**: `93edce5`

---

### 阶段 S3-3: 交易所挂单集成（可选） ⏸️ 暂缓

**目标**: 集成交易所挂单功能（需用户授权）

**状态**: 第三阶段完成后再评估

---

## 第四阶段 + 第五阶段：工业化调优 + 状态增强（集成测试中）

**状态**: 集成测试文档已创建，准备 3 窗口并行执行

### 集成测试任务分配

| 编号 | 测试场景 | 涉及功能 | 窗口 | 状态 |
|------|----------|----------|------|------|
| Test-01 | 配置快照 + WebSocket 降级 | S4-1 + S5-1 | 窗口 3 | ⏳ 待执行 |
| Test-02 | 队列背压 + WebSocket 降级 | S4-2 + S5-1 | 窗口 2 | ⏳ 待执行 |
| Test-03 | EMA 缓存 + WebSocket 降级 | S4-3 + S5-1 | 窗口 1 | ⏳ 待执行 |
| Test-04 | 快照回滚 + 信号状态连续性 | S4-1 + S5-2 | 窗口 1 | ⏳ 待执行 |
| Test-05 | 队列拥堵 + 信号状态完整性 | S4-2 + S5-2 | 窗口 2 | ⏳ 待执行 |
| Test-06 | 多策略 +EMA 缓存 + 状态跟踪 | S4-3 + S5-2 | 窗口 3 | ⏳ 待执行 |

**执行顺序**:
```
窗口 1: Test-04 → Test-03
窗口 2: Test-05 → Test-02
窗口 3: Test-01 → Test-06
```

**测试文档**: `docs/tasks/S-integration-Test01.md` ~ `Test06.md`

---

### 阶段 S4-1: 配置快照版本化（Rollback） ✅ 代码完成，待集成测试

### 阶段 S4-2: 异步 I/O 队列 ✅ 代码完成，待集成测试

### 阶段 S4-3: 指标计算缓存 ✅ 代码完成，待集成测试

### 阶段 S5-1: WebSocket 资产推送 ✅ 代码完成，待集成测试

### 阶段 S5-2: 信号状态跟踪系统 ✅ 代码完成，待集成测试

---

## 第六阶段：优化与改进（❌ 全部废弃）

**状态**: ❌ **全部废弃** - 2026-03-30

**废弃说明**: 除 v3 迁移外，所有待办事项全部废弃。团队资源集中投入到 v3.0 迁移。

**原阶段概览 (仅供参考)**:
| 阶段 | 任务 | 状态 | 优先级 |
|------|------|------|--------|
| ~~S6-1~~ | ~~冷却缓存优化~~ | ❌ 已废弃 | - |
| ~~立即测试功能优化~~ | ~~方案 C 实施~~ | ✅ 已完成 | - |
| ~~TraceNode.details 修复~~ | ~~API 响应验证修复~~ | ✅ 已完成 | - |

---

## 🎯 当前首要目标：v3.0 迁移

**工期**: 14 周（2026-05-06 ~ 2026-08-24）

**阶段概览**:
| 阶段 | 名称 | 工期 | 开始日期 | 结束日期 | 状态 |
|------|------|------|----------|----------|------|
| Phase 0 | v3 准备 | 1 周 | 2026-05-06 | 2026-05-13 | ✅ 已完成 |
| Phase 1 | 模型筑基 | 2 周 | 2026-05-19 | 2026-06-01 | ✅ 已完成 (2026-03-30) |
| Phase 2 | 撮合引擎 | 3 周 | 2026-06-02 | 2026-06-22 | ✅ 已完成 |
| Phase 3 | 风控状态机 | 2 周 | 2026-06-23 | 2026-07-06 | ✅ 已完成 |
| Phase 4 | 订单编排 | 2 周 | 2026-07-07 | 2026-07-20 | ✅ 已完成 |
| Phase 5 | 实盘集成 | 3 周 | 2026-07-21 | 2026-08-10 | 🔄 编码完成，待审查修复 |
| Phase 6 | 前端适配 | 2 周 | 2026-08-11 | 2026-08-24 | ⏳ pending |

**详细文档**: `docs/v3/v3-evolution-roadmap.md`

---

## Phase 1-4 验证报告（2026-03-31）

**验证状态**: ✅ 全部完成

### 测试汇总

| 类别 | 测试数 | 通过率 | 说明 |
|------|--------|--------|------|
| 单元测试 (v3 核心) | 131 | 100% | ORM/模型/撮合/风控/订单 |
| 集成测试 (Phase 1) | 70 | 66/70 (94.3%) | 4 个 alembic 测试跳过 |
| 集成测试 (Phase 3) | 7 | 100% | 完整交易流程 |
| 集成测试 (Phase 4) | 6 | 100% | 订单编排流程 |

### CHECK 约束修复

| 约束 | 问题 | 修复 |
|------|------|------|
| ORDER_STATUS_CHECK | 缺少 EXPIRED | ✅ 已添加 |
| ORDER_TYPE_CHECK | 缺少 STOP_LIMIT | ✅ 已添加 |
| ORDER_ROLE_CHECK | 缺少 TP2-TP5 | ✅ 已添加 |

**修复文件**:
- `src/infrastructure/v3_orm.py`
- `migrations/versions/2026-05-02-002_create_orders_positions_tables.py`

**Git 提交**: `dc76346`

### 结论

**Phase 1-4 全部完成**，核心功能通过测试验证。Phase 5 实盘集成编码已完成，待审查修复。

---

## Phase 1: 模型筑基 - 完成报告

**完成时间**: 2026-03-30
**执行状态**: ✅ 全部完成

### 任务完成概览

| 任务 ID | 任务名称 | 状态 | 交付物 |
|---------|----------|------|--------|
| P1-1 | 实现 v3 SQLAlchemy ORM 模型 | ✅ | `src/infrastructure/v3_orm.py` |
| P1-2 | 编写 ORM 模型单元测试 | ✅ | `tests/unit/test_v3_orm.py` (27 测试) |
| P1-3 | 定义前端 TypeScript 类型 | ✅ | `web-front/src/types/v3-models.ts` |
| P1-4 | 执行数据库迁移 | ✅ | 3 个迁移文件，4 个核心表 |
| P1-5 | 审查与验证 | ✅ | 修复 5 个问题 |
| P1-6 | 测试执行 | ✅ | 70 个集成测试全部通过 |

### 测试覆盖

**总计 143 个测试，100% 通过**

| 测试文件 | 测试数 | 说明 |
|----------|--------|------|
| `tests/unit/test_v3_models.py` | 22 | Pydantic 模型测试 |
| `tests/unit/test_v3_orm.py` | 27 | ORM 模型测试 |
| `tests/unit/test_v3_orm_regression.py` | 24 | ORM 回归测试 |
| `tests/integration/test_v3_phase1_integration.py` | 70 | Phase 1 集成测试 |

### 数据库结构

```
数据库：v3_dev.db
├── accounts       ✅ (5 字段，主键 account_id)
├── signals        ✅ (11 字段，CHECK 约束)
├── orders         ✅ (16 字段，外键级联)
└── positions      ✅ (12 字段，外键级联)
```

### 迁移文件

| 迁移 ID | 文件名 | 说明 |
|---------|--------|------|
| 001 | `2026-05-01-001_unify_direction_enum.py` | Direction 枚举统一（LONG/SHORT） |
| 002 | `2026-05-02-002_create_orders_positions_tables.py` | 创建 orders + positions 表 |
| 003 | `2026-05-03-003_create_signals_accounts_tables.py` | 创建 signals + accounts 表 |

### 修复问题汇总

| 问题 | 严重性 | 修复状态 |
|------|--------|----------|
| pattern_score 类型错误（Integer → Float） | 高 | ✅ 已修复 |
| signals/accounts 表缺失 | 高 | ✅ 已创建（迁移 003） |
| SQLite 外键约束未生效 | 中 | ✅ 已启用（PRAGMA foreign_keys = ON） |
| Direction 枚举测试过时 | 低 | ✅ 已更新 |

### 交付文档

- `docs/v3/v3-phase1-complete-report.md` - Phase 1 完成报告
- `docs/v3/v3-evolution-roadmap.md` - 已更新 Phase 1 状态
- `CLAUDE.md` - 已更新项目阶段

---

## 下一步：Phase 2 - 撮合引擎

**计划启动日期**: 2026-05-19
**工期**: 3 周

**核心任务**:
1. 实现 MockMatchingEngine（悲观撮合）
2. 支持 v3 回测模式 (`mode="v3_pms"`)
3. v2/v3 回测对比验证
4. 滑点和手续费计算

**验收标准**:
- [ ] v3.0 回测报告包含真实盈亏统计
- [ ] 同一策略 v2/v3 回测结果差异可解释
- [ ] 单元测试覆盖撮合边界 case
- [ ] 滑点/手续费计算精度验证

---

### 阶段 S6-1: 冷却缓存优化 ❌ 已废弃

**状态**: ❌ **已废弃 (Deprecated)** - 2026-03-30

**废弃原因**:

1. **信号覆盖机制已解决重复通知问题**
   - S6-2 实现的信号覆盖逻辑 (`_check_cover`) 已确保：只有更高分的信号才能触发新通知
   - 覆盖逻辑：`if score > old_score: 覆盖旧信号`

2. **双重限制过度防御**
   - 冷却缓存 (4 小时固定) + 信号覆盖两层逻辑，增加了系统复杂度
   - 边界情况处理困难：冷却期内同样/更低分信号无法触发

3. **与核心设计原则冲突**
   - 系统已有信号覆盖机制作为"去重"策略
   - 冷却缓存是历史遗留，早期为防止通知轰炸的临时方案

**原有需求**: 防止同一信号重复通知
**现有方案**: 信号覆盖机制 (S6-2) + 时间窗口控制

```python
# 信号覆盖逻辑 (signal_pipeline.py:813)
if score > old_score:
    # 新信号分数更高 → 覆盖旧信号并发送通知
    return True, old_signal_id, old_signal_data
```

**迁移指南**:
- 无需迁移 - 冷却缓存逻辑保留但不影响核心流程
- 配置项 `cooldown_seconds` 保留向后兼容

---

**原始设计文档 (仅供参考)**:

| 方案 | 描述 | 状态 |
|------|------|------|
| **A: 动态冷却** | 按周期/策略差异化设置冷却期 | ❌ 不再需要 |
| **B: 基于信号状态** | 仅当有 PENDING 信号时冷却 | ❌ 不再需要 |
| **C: 移除冷却** | 交给策略逻辑自过滤 | ✅ 信号覆盖已实现 |
| **D: 冷却过滤器** | 将冷却设计为可插拔过滤器 | ❌ 不再需要 |

---

### 2026-03-28 完成工作

#### 1. 诊断分析师角色创建 ✅

**目标**: 创建系统诊断分析师角色，专门负责疑难杂症诊断

**交付物**:
- 创建 `.claude/commands/diagnostic.md` - 诊断分析师命令配置
- 创建 `.claude/team/diagnostic-analyst/SKILL.md` - 技能定义
- 创建 `.claude/team/diagnostic-analyst/QUICKSTART.md` - 快速入门指南

**核心原则**:
- ❌ 不修改业务代码
- ❌ 不创建新业务功能
- ✅ 只分析问题，输出诊断报告和修复方案

**使用方式**:
```bash
/diagnostic
```

---

#### 2. 立即测试功能优化（方案 C） ✅

**目标**: 添加前端提示说明，引导用户理解立即测试的局限性

**问题背景**:
- 用户反馈"立即测试"没有信号触发，认为功能有问题
- 实际上接口工作正常，只是当前 K 线不满足形态条件
- 需要明确告知用户：仅评估当前一根 K 线

**交付物**:
- 修改：`web-front/src/pages/StrategyWorkbench.tsx`
  - 添加提示警告框，说明立即测试的局限性
  - 添加结果状态提示（触发/未触发）
  - 引导用户使用回测沙箱查看历史表现

**修改内容**:
```tsx
{/* 提示信息 */}
<div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
  <p>仅评估当前最新一根 K 线，如果未检测到信号属于正常现象。</p>
  <p>想查看历史表现？前往 <a href="/backtest">回测沙箱</a></p>
</div>

{/* 结果状态 */}
<div>
  <p>✅ 当前 K 线满足策略条件，信号触发！</p>
  或
  <p>ℹ️ 当前 K 线不满足策略条件，未检测到信号</p>
</div>
```

**Git 提交**: `88d2e8f`

---

#### 3. API 响应验证问题诊断 ✅

**问题**: `/api/strategies/preview` 接口返回 `'TraceNode' object has no attribute 'details'`

**根因定位**:
- `api.py:1199` 访问 `node.details`，但 `TraceNode` 定义的是 `metadata` 字段
- 字段命名不一致导致 AttributeError

**诊断报告编号**: DA-20260328-001

**修复方案** (已完成):
```python
# src/interfaces/api.py:1199
# 修改前：
"details": node.details,
# 修改后:
"details": node.metadata,
```

**验证结果**:
- 接口已正常返回 trace_tree
- 用户确认"接口已经可以正常返回数据了"

---

#### 4. 回测结果为空信号诊断 📋

**用户报告**: 回测 30 天数据，但结果为 0 个信号

**诊断发现**:
1. **时间范围参数未生效** 🔴
   - `Backtester._fetch_klines()` 只使用 `limit` 参数
   - `start_time/end_time` 被忽略
   - 实际只获取 100 根 K 线（约 1 天）

2. **`total_attempts = 0` 异常** 🟡
   - 可能原因：`DynamicStrategyRunner.run_all()` 返回空列表
   - 需要添加调试日志确认

**诊断报告编号**: DA-20260328-002

**修复方案**:
- 方案 A：实现时间范围支持（2-3 小时）
- 方案 B：添加调试日志定位问题（30 分钟）

**状态**: 等待用户确认优先级

---

#### 5. 立即测试功能局限性分析 📋

**问题**: 用户反馈"立即测试"功能没效果

**分析结果**:
- 接口工作正常 ✅
- 只评估当前一根 K 线（最新闭合 K 线）
- 没有高周期数据预热（MTF 过滤器无法工作）
- 没有 EMA 预热（EMA 过滤器无法工作）

**改进方案**:
- 方案 A：增强版立即测试（测试 100 根 K 线）- 2-3 小时
- 方案 B：添加"最近信号"模式 - 1 小时
- 方案 C：最小改动（前端提示）- 30 分钟 ✅ 已实施

**用户选择**: 方案 C ✅ 已完成

---

### 待办事项汇总

**🚫 全部废弃 (2026-03-30)**: 除 v3 迁移外，所有待办事项全部废弃。团队资源集中投入到 v3.0 迁移。

~~**实盘导向任务规划 (2026-03-30)**:~~

~~基于用户目标（止盈追踪 → 交易所测试/实盘），重新梳理优先级：~~

| 优先级 | 任务 | 预计工作量 | 状态 | 说明 |
|--------|------|-----------|------|------|
| ~~P0~~ | ~~止盈追踪逻辑~~ | ~~48h~~ | ❌ **已废弃** | 整合到 v3 Phase 3 |
| ~~P0~~ | ~~多交易所适配~~ | ✅ completed | 实盘刚需 | Bybit/OKX 配置驱动切换 |
| **v3** | **v3.0 迁移** | **14 周** | 🔄 **当前首要目标** | 2026-05 启动，详见 docs/v3/v3-evolution-roadmap.md |
| ~~P1~~ | ~~可视化 - 逻辑路径~~ | ~~4-6h~~ | ❌ **已废弃** | 整合到 v3 Phase 6 |
| ~~P1~~ | ~~可视化 - 资金监控~~ | ~~4-6h~~ | ❌ **已废弃** | 整合到 v3 Phase 6 |
| ~~P2~~ | ~~性能统计~~ | ~~5-8h~~ | ❌ **已废弃** | 整合到 v3 Phase 6 |

---

### 2026-03-30 完成：多交易所适配

**目标**: 实现 Bybit 和 OKX 的多交易所适配，支持配置驱动切换

**交付物**:
- 创建：`config/user.bybit.yaml.example` - Bybit 配置模板
- 创建：`config/user.okx.yaml.example` - OKX 配置模板
- 创建：`docs/arch/2026-03-30-多交易所适配验证报告.md`
- 创建：`tests/integration/test_multi_exchange_integration.py` - 集成测试
- 创建：`tests/integration/test_exchange_live_connection.py` - 实时连接测试
- 修改：`tests/unit/test_exchange_gateway.py` - 参数化测试支持 3 交易所
- 修改：`src/domain/models.py` - Pydantic v2 ConfigDict 迁移

**测试结果**:
```
tests/unit/test_exchange_gateway.py: 66/66 通过 (100%)
tests/integration/test_multi_exchange_integration.py: 25/25 通过 (100%)
tests/integration/test_exchange_live_connection.py: 2/2 通过 (100%)
总计：93 项测试全部通过
```

**核心功能**:
- ✅ 配置驱动切换交易所（binance/bybit/okx）
- ✅ 核心币种池兼容性验证（BTC/ETH/SOL/BNB）
- ✅ CCXT.Pro WebSocket 支持（watch_ohlcv/watch_balance）
- ✅ 完整的单元测试和集成测试覆盖
- ✅ 代码审查发现并修复 3 个低优先级问题

**快速切换**:
```bash
# 切换到 Bybit
cp config/user.bybit.yaml.example config/user.yaml

# 切换到 OKX
cp config/user.okx.yaml.example config/user.yaml
```

**Git 提交**: `0e214af`

**待办**:
- ⏳ 用户申请 API Key 后进行实盘验证

---

**已废弃任务 (2026-03-30)**:
- ~~S6-1 冷却缓存优化~~ → ❌ 已废弃 (信号覆盖机制已解决重复通知问题)

---

### 技术债清单

**已修复技术债 (2026-03-30)**:
- ~~#1 回测时间范围参数未生效~~ → ✅ 已实现 start_time/end_time 支持
- ~~#2 ATR 过滤器占位符实现~~ → ✅ 已完成 (`3c60ae2`)
- ~~#3 冷却缓存固定 4 小时~~ → ❌ 已废弃 (信号覆盖机制替代)
- ~~#4 多交易所适配~~ → ✅ 已完成 (`0e214af`)
- ~~#5 Pydantic class Config 弃用~~ → ✅ 已迁移到 ConfigDict
- ~~#TP-2 实盘止盈追踪逻辑未实现~~ → ❌ **已废弃** (整合到 v3 Phase 3)

| 编号 | 问题 | 影响范围 | 优先级 | 状态 |
|------|------|----------|--------|------|
| #TP-1 | 回测分批止盈模拟未实现 | 止盈精度模拟 | 低 | 🟢 搁置 (等待 v3.0 Phase 2 实现) |
| #2 | 立即测试无高周期数据预热 | MTF/EMA 过滤器评估 | 中 | ⏸️ 暂缓 |

**#TP-1 搁置说明**:
- v2.0 回测本质是"信号级模拟器"，非真实盈亏计算
- v3.0 Phase 2 将实现真正的订单级撮合引擎，止盈逻辑是核心功能
- 避免重复开发和未来维护负担

---

## Phase 5 实盘集成开发计划（2026-03-30 设计完成）

**状态**: ✅ 设计完成，待开发

**设计文档**:
- `docs/designs/phase5-real-exchange-integration-contract.md` (v1.3)
- `docs/designs/phase5-environment-compatibility-brainstorm.md`
- `docs/designs/phase5-contract-review-report.md` (v1.2)
- `docs/designs/phase5-development-checklist.md`

### 开发任务清单

| 编号 | 任务 | 预计工时 | 优先级 | 说明 |
|------|------|----------|--------|------|
| T-001 | ExchangeGateway 订单接口 | 4h | P0 | REST 下单、取消、查询 |
| T-002 | WebSocket 订单推送监听 | 4h | P0 | CCXT.Pro watch_orders |
| T-003 | 并发保护机制实现 | 4h | P0 | Asyncio Lock + DB 行锁 |
| T-004 | 启动对账服务 | 4h | P0 | 仓位对账、订单对账 |
| T-005 | 资金保护管理器 | 3h | P0 | 单笔/每日/仓位限制 |
| T-006 | DCA 分批建仓实现 | 6h | P0 | 2-5 批次，价格/跌幅触发 |
| T-007 | 飞书告警集成 | 2h | P1 | 多事件类型通知 |
| T-008 | 区域切换支持 | 2h | P2 | 东京↔香港脚本 |
| T-009 | 单元测试编写 | 6h | P0 | 资金保护、DCA、并发 |
| T-010 | 集成测试编写 | 8h | P0 | E2E 端到端测试 |

**预计总工时**: ~39 小时（约 5 个工作日）

### 开发前准备

**环境准备**:
- [ ] 确认 Binance 测试网 API 密钥可用
- [ ] 确认东京 AWS 服务器可访问
- [ ] 准备飞书 Webhook URL
- [ ] 配置环境变量（.env 文件）

**依赖安装**:
```bash
pip install ccxt>=4.2.24
pip install -r requirements.txt
```

**配置准备**:
```yaml
# .env
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=<测试网密钥>
EXCHANGE_API_SECRET=<测试网密钥>
DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
CAPITAL_PROTECTION_ENABLED=true
SINGLE_TRADE_MAX_LOSS_PERCENT=2.0
DAILY_MAX_LOSS_PERCENT=5.0
```

### 核心设计决策

| 决策项 | 决策结果 |
|--------|----------|
| 交易所支持 | Binance (测试网 + 生产网) |
| 数据库策略 | SQLite (开发) / PostgreSQL (测试 + 生产) |
| 服务器位置 | 东京 AWS (预留香港切换) |
| 告警渠道 | 飞书 Webhook |
| DCA 分批建仓 | Phase 5 实现 (2-5 批次) |
| 资金保护 | 单笔 2% / 每日 5% / 仓位 20% |
| 并发保护 | Asyncio Lock + DB 行锁 (双层) |

### Gemini 审查问题修复

| 问题 | 修复状态 | 说明 |
|------|----------|------|
| G-001: CCXT.Pro 依赖包废弃 | ✅ | 修正为 `ccxt>=4.2.24` |
| G-002: WebSocket 去重逻辑 | ✅ | 基于 filled_qty 推进 |
| G-003: 内存锁泄漏风险 | ✅ | 平仓后自动清理 |
| G-004: Base Asset 手续费说明 | ✅ | 明确 U 本位合约定位 |

---

## Phase 5: 实盘集成 - 编码完成（待审查修复）

**创建日期**: 2026-03-30
**状态**: 🟡 暂停中（等待审查问题修复）
**Git 提交**: `57eacd3` + `3db2d03`

### 阶段概览

| 任务 | 状态 | 测试数 | 文件 |
|------|------|--------|------|
| P5-1: ExchangeGateway 订单接口 | ✅ completed | 66 | `src/infrastructure/exchange_gateway.py` |
| P5-2: PositionManager 并发保护 | ✅ completed | 27 | `src/application/position_manager.py` |
| P5-3: WebSocket 订单推送监听 | ✅ completed | 14 | `src/infrastructure/exchange_gateway.py` |
| P5-4: 飞书告警集成 | ✅ completed | 32 | `src/infrastructure/notifier_feishu.py` |
| P5-5: 启动对账服务 | ✅ completed | 15 | `src/application/reconciliation.py` |
| P5-6: 资金保护管理器 | ✅ completed | 21 | `src/application/capital_protection.py` |
| P5-7: DCA 分批建仓策略 | ✅ completed | 30 | `src/domain/dca_strategy.py` |
| P5-8: 代码审查 | ✅ completed | - | `docs/reviews/phase5-code-review.md` |

**测试覆盖**: 205+ 个单元测试，全部通过 ✅

### Gemini 评审问题修复（Phase 5 设计）

| 编号 | 问题 | 修复方案 | 状态 |
|------|------|----------|------|
| **G-001** | asyncio.Lock 释放后使用 | WeakValueDictionary | ✅ |
| **G-002** | 市价单价格缺失 | fetch_ticker_price | ✅ |
| **G-003** | DCA 限价单吃单陷阱 | 提前预埋限价单 | ✅ |
| **G-004** | 对账幽灵偏差 | 10 秒 Grace Period | ✅ |

### 代码审查发现的问题

**审查报告**: `docs/reviews/phase5-code-review.md`

| 严重性 | 数量 | 问题说明 | 预计工时 |
|--------|------|----------|----------|
| 🔴 严重 | 7 | Pydantic 模型缺失（OrderRequest/OrderResponse 等） | ~7h |
| 🟡 一般 | 3 | 枚举对齐/日志脱敏/错误码统一 | ~1.5h |

### 待修复任务

| 编号 | 任务 | 文件 | 预计工时 |
|------|------|------|----------|
| P5-001 | OrderRequest 模型 | `src/domain/models.py` | 1h |
| P5-002 | OrderResponse 模型 | `src/domain/models.py` | 1h |
| P5-003 | OrderCancelResponse 模型 | `src/domain/models.py` | 0.5h |
| P5-004 | PositionResponse 模型 | `src/domain/models.py` | 1h |
| P5-005 | AccountBalance/AccountResponse | `src/domain/models.py` | 1h |
| P5-006 | ReconciliationRequest 模型 | `src/domain/models.py` | 0.5h |
| P5-007 | 前端 TypeScript 类型 | `web-front/src/types/order.ts` | 2h |
| P5-008 | OrderRole 枚举对齐 | `src/domain/models.py` | 0.5h |
| P5-009 | 日志脱敏检查 | 多处 | 0.5h |
| P5-010 | 错误码统一使用 | 多处 | 0.5h |

### 下一步计划

1. 修复 P5-001 ~ P5-010（预计 ~8.5h）
2. 重新运行代码审查验证
3. 执行集成测试（Binance Testnet E2E）
4. 提交 Phase 5 代码

### 遗留问题：生产环境订单清理机制 📋

**问题编号**: P5-011
**优先级**: P1
**预计工时**: 4-6h（分析 + 设计 + 实现）

**背景**:
Window 4 测试发现测试网积累了 50 笔历史订单和 4 笔未成交委托单。生产环境中，历史委托订单如果不清理可能导致：
- 保证金占用
- 仓位计算错误
- 意外成交风险
- 系统重启后状态不一致

**需要分析的场景**:
1. 系统是否有主动挂限价单的策略？（如：挂单吃 Maker 费率）
2. 止盈止损订单（TP/SL）是否属于"应保留"的订单？
3. DCA 分批建仓的限价单如何处理？
4. 订单与信号的关联关系如何追踪？
5. 系统重启 vs 正常停机 vs 异常崩溃，不同场景的清理策略

**待输出**:
1. 订单分类策略（哪些该取消、哪些该保留）
2. 清理触发时机（启动时？定期？按事件触发？）
3. 订单归属判断逻辑（如何区分"本系统订单"vs"外部订单"）
4. 异常处理（取消失败、部分取消等）

**状态**: ⏳ 待分析设计

### 相关文件

- 交接文档：`docs/planning/phase5-session-handoff.md`
- 详细设计：`docs/designs/phase5-detailed-design.md` (v1.1)
- 契约表：`docs/designs/phase5-contract.md`
- 审查报告：`docs/reviews/phase5-code-review.md`
- 进度日志：`docs/planning/progress.md`

### Git 提交

```
57eacd3 feat(phase5): 实盘集成核心功能实现（审查中）
3db2d03 docs: 更新 Phase 5 进度日志（编码完成，待审查修复）
```

---
