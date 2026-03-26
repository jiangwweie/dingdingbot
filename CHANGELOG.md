# 盯盘狗 🐶 变更日志

## [v0.2.0-phase2] - 2026-03-26

### 🎯 交互升维

#### 新增功能

##### 实盘热重载 (S2-1)
- **POST /api/strategies/{id}/apply** - 策略模板一键下发实盘
- **配置原子更新** - ConfigManager 添加 `_update_lock` 保证并发安全
- **Observer 机制** - 配置变更自动触发 SignalPipeline 重建
- **Warmup 状态回填** - EMA 等有状态指标无缝恢复
- **前端 Apply 交互** - "应用到实盘"按钮 + 确认对话框 + Toast 提示

**API 变更**:
```python
# 新增端点
POST /api/strategies/{id}/apply
Response: { status: "success", message: string, strategy_id: string }
```

**代码变更**:
- `src/interfaces/api.py` - Apply 端点 + StrategyApplyRequest/Response 模型
- `src/application/config_manager.py` - `_update_lock` 原子更新锁
- `src/application/signal_pipeline.py` - Warmup 日志增强
- `web-front/src/lib/api.ts` - `applyStrategy()` 函数
- `web-front/src/pages/StrategyWorkbench.tsx` - Apply UI + 确认对话框

##### 信号标签动态化 (S2-4)
- **模型清理** - SignalResult 移除 `ema_trend`/`mtf_status` 硬编码字段
- **动态标签** - 使用 `tags: List[Dict[str, str]]` 数组
- **标签生成** - `_generate_tags_from_filters()` 从过滤器结果提取
- **向后兼容** - 前端保留 legacy 字段为可选

**模型变更**:
```python
# SignalResult 变更
- ema_trend: Optional[str]       # 已移除
- mtf_status: Optional[str]      # 已移除
+ tags: List[Dict[str, str]]     # 新增，如 [{"name": "EMA", "value": "Bullish"}]
```

**代码变更**:
- `src/domain/models.py` - SignalResult 模型清理
- `web-front/src/lib/api.ts` - Signal 接口更新（tags + legacy 可选字段）
- `tests/unit/test_signal_pipeline.py` - TestDynamicTags (7 个新测试)

##### 前端组件清理 (S2-3)
- **重构** - StrategyBuilder.tsx 删除 1300 行硬编码代码
- **Schema 驱动** - 100% 动态表单生成
- **类型统一** - `types/strategy.ts` 与 `api.ts` 类型对齐

**代码变更**:
- `web-front/src/components/StrategyBuilder.tsx` - 重构为 Schema 驱动
- `web-front/src/types/strategy.ts` - 类型定义与 api.ts 对齐
- `web-front/src/lib/api.ts` - 辅助函数导出（generateId, getDefaultFilterParams 等）

#### 测试覆盖

**新增测试文件**:
- `tests/unit/test_strategy_apply.py` - 5 个单元测试
- `tests/integration/test_hot_reload.py` - 19 个集成测试
- `tests/unit/test_signal_pipeline.py` - +7 个动态标签测试

**测试场景**:
- 并发锁保护验证
- 队列背压测试
- 配置回滚机制
- EMA 连续性验证
- 动态标签生成

#### 技术债清理

- 移除硬编码前端组件（StrategyBuilder 重构）
- 统一前后端类型定义
- 清理 legacy 字段（ema_trend, mtf_status）
- 优化构建产物大小（-150KB）

---

### 📊 统计数据

| 指标 | 数值 |
|------|------|
| 新增测试 | 31 |
| 修改文件 | ~15 |
| 新增代码行 | ~800 |
| 删除代码行 | ~1350 |
| 构建产物 | 557 KB (-150 KB) |

---

### 🔗 Git 提交

| 提交 | 内容 |
|------|------|
| f39105f | feat: S2-4 完成信号标签动态化重构 |
| 8e78601 | feat: S2-1 完成实盘热重载功能 |
| 6b90665 | feat: S2-3 完成前端硬编码组件清理 |
| 15dff94 | docs: 更新进度日志（会话 9 - S2-1 完成） |
| 822f1c8 | docs: 更新进度日志（会话 10 - S2-3 完成） |

---

## [v0.1.0-phase1] - 2026-03-25

### 🎯 架构筑基

#### 新增功能

##### 递归逻辑树引擎 (子任务 F)
- **LogicNode 递归类型** - Pydantic Discriminator Union
- **递归评估引擎** - `evaluate_node()` 深度优先遍历
- **StrategyDefinition 升级** - 支持 logic_tree 字段
- **热预览接口** - `POST /api/strategies/preview`

##### 前端递归渲染 (子任务 E)
- **TypeScript 递归类型** - AndNode, OrNode, NotNode, LeafNode
- **NodeRenderer 组件** - 递归渲染逻辑树
- **LogicGateControl** - 逻辑门控制组件
- **LeafNodeForm** - 叶子节点表单组件
- **TraceTreeViewer** - Trace 树可视化

#### 测试覆盖

- 284 个单元测试（100% 通过）
- 核心递归功能测试：47 个

---

*更多历史版本请参考 Git 标签*
