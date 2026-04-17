# Findings Log

> Last updated: 2026-04-17 11:30

---

## 2026-04-17 -- Trailing TP Phase 5 单元测试发现

### 技术发现

**发现 1: 水位线更新与 TTP 激活时序**
- `evaluate_and_mutate()` 的 Step 2 更新水位线，Step 4 执行 TTP
- 这意味着 TTP 在同一根 K 线内使用的是**更新后**的水位线
- 测试 `test_tp_trailing_watermark_none` 验证了这个行为：初始 watermark=None 时，Step 2 会先更新，Step 4 使用新值

**发现 2: original_tp_prices 初始化时机**
- 在 `_apply_trailing_tp()` 中，首次遇到某 TP 级别时会记录原始价格
- 使用 dict 字典存储：`position.original_tp_prices["TP1"] = order.price`
- 这确保了 floor protection 有正确的原始价格基准

**发现 3: 阶梯阈值计算方向**
- LONG: `min_required = current_tp * (1 + step_threshold)`，新价格必须高于当前价
- SHORT: `min_required = current_tp * (1 - step_threshold)`，新价格必须低于当前价
- 方向性确保了频控逻辑在两个方向上都正确工作

**发现 4: TP 价格 floor protection 方向**
- LONG: `new_tp = max(original_tp_price, theoretical_tp)`，不低于原始价格
- SHORT: `new_tp = min(original_tp_price, theoretical_tp)`，不高于原始价格
- 确保 TTP 不会把止盈价格往不利方向移动

**发现 5: 激活阈值计算**
- LONG: `activation_price = entry + activation_rr * (tp_price - entry)`
- SHORT: `activation_price = entry - activation_rr * (entry - tp_price)`
- activation_rr=0.5 表示价格需要走完入场到 TP 目标的一半距离才激活追踪

### 测试覆盖统计

| 类别 | 测试数量 | 覆盖内容 |
|------|----------|----------|
| 基础功能 | 4 | 启用/禁用、激活阈值、LONG/SHORT 激活 |
| 调价逻辑 | 5 | 水位线跟随、阶梯阈值、floor protection |
| 多级别 | 2 | 启用级别过滤、TP2/TP3 独立追踪 |
| 事件记录 | 3 | 事件生成、字段验证、无事件场景 |
| 边界条件 | 6 | 已平仓、None 水位线、Decimal 精度、零仓位、激活状态持久、多 K 线追踪 |
| 集成验证 | 2 | 设计文档示例、返回值类型 |

**总计**: 22 个测试全部通过

---

## 2026-04-16 10:00 -- 策略设计决策: Virtual TTP (追踪止盈模式)

### 架构决策背景
实盘阶段中，对于 追踪止盈 (Trailing Take Profit, TTP) 功能实施如果通过“取消原 LIMIT TP 限价单 -> 触发后转化为 TRAILING_STOP”的途径（即 Hybrid 挂单），将导致关键竞态条件在撤改期间爆发，若遭遇极端上下插针可能导致获利单彻底“裸奔”失序甚至损失加倍。

### 采用 Virtual TTP (影子追踪方案)
用户已最终确认基于**纯后台虚拟跟踪推演**（方案 B）来实现：
- 交易所端仍只悬挂极端的底线止损单（SL）以保证网络失效的安全边际。
- TP 和 TTP 规则判断全程运行在 Python 本地进程中的 `DynamicRiskManager`。
- 当行情达到触发比例，系统执行一个瞬态的市价交易平仓解决止盈。

**技术折衷**: 
以止盈阶段从 Maker（零/负费率）沦为 Taker（额外滑点和费率）为代价，换取系统状态机的**100% 绝对一致与确定性执行**。这符合 `Clean Architecture` 的指导思想并将领域层控制能力最大化。

---

## 2026-04-15 20:30 -- 任务 1.1+1.4 + 阶段 5 集成测试案例设计

### 测试现状盘点

| 测试文件 | 覆盖范围 | 状态 | 备注 |
|---|---|---|---|
| `test_backtest_tp_events.py` | TP 事件撮合 + DB 持久化 + SL 优先 | ✅ 已有 5 个测试 | 使用 MockMatchingEngine，覆盖 IT-1~IT-4 |
| `test_backtest_user_story.py` | 端到端回测流程 (API → DB) | ✅ 已有 | 验证 4 (收益率正确性) 已包含 |
| `test_backtest_repository.py` | Repository 层 close_events 序列化 | ✅ 已有 | TestCloseEventsPersistence + TestMigrationLogic |
| `test_attribution_engine.py` | AttributionEngine 单元逻辑 | ✅ 35 个 UT | 单信号/批量/聚合/边界场景 |
| `test_attribution_config.py` | AttributionConfig 校验 | ✅ 20 个 UT | 权重校验/边界/from_kv |
| `test_attribution_api.py` | 归因 API 端点 | ✅ 已有 8 个 | 但使用 Mock repo，未走真实回测 |

### 测试缺口分析

**任务 1.1+1.4 缺失覆盖**：
1. **端到端 close_events 数据流**：现有 `test_backtest_tp_events.py` 使用 MockMatchingEngine + 手动收集 close_events，未走真实 backtester.py → API → DB 全链路
2. **close_pnl 非零验证**：撮合引擎已修复 `_execute_fill` 写入 order.close_pnl/close_fee，但无集成测试验证此值非零
3. **分批止盈完整场景**：TP1+TP2+SL 组合场景的 end-to-end 数据流（一个仓位经历 TP1 部分平仓 + TP2 部分平仓 + SL 完全平仓）
4. **PnL 不变量验证**：`sum(close_pnl) == position.realized_pnl` 在端到端回测中是否成立

**阶段 5 缺失覆盖**：
1. **回测报告包含归因字段**：backtester.py 已集成 AttributionEngine，但无集成测试验证 report 中 signal_attributions / aggregate_attribution 非空
2. **真实过滤器 metadata 路径**：test_attribution_api.py 使用 Mock data，未经过真实 FilterContext → TraceEvent.metadata → AttributionEngine 路径
3. **前端归因数据契约**：API 返回的归因数据结构是否与前端 TypeScript 接口匹配

### 新增测试案例设计 — 用户故事串联模式

> **设计原则**：模拟真实用户操作路径，用 `_flow3_state` 跨步骤传递 `report_id`，
> 步骤 N 依赖步骤 N-1 的真实数据，不使用 Mock 孤立验证。

---

### 用户故事: "我跑了一个回测，想验证分批止盈和归因分析"

**测试文件**: `tests/integration/test_backtest_close_attribution_flow.py`

**共享状态**: `_flow3_state: dict = {}` （同 test_backtest_user_story.py 模式）

---

#### 步骤 1: 用户发起 PMS 回测（含多级止盈配置）

| 属性 | 值 |
|------|------|
| **测试名称** | `test_step1_run_pms_backtest_with_multi_tp` |
| **API** | `POST /api/backtest/orders` |
| **输出到 flow_state** | `report_id`, `report_json`, `total_trades` |

**测试逻辑**:
- 发起 PMS 回测，strategy 配置多级止盈（order_strategy 包含 TP1/TP2/TP3 比例）
- 断言：`status == "success"`, `report` 存在
- 断言：`report["close_events"]` 是列表（即使为空也必须有该字段）
- 断言：`report["signal_attributions"]` 非 None
- 断言：`report["aggregate_attribution"]` 非 None
- 存储 `report_id` 和完整 `report_json` 到 `_flow3_state`

---

#### 步骤 2: 用户查看回测报告列表，确认报告已保存

| 属性 | 值 |
|------|------|
| **测试名称** | `test_step2_query_report_list_sees_saved_report` |
| **API** | `GET /api/v3/backtest/reports` |
| **依赖** | 步骤 1 的 `report_id` |
| **输出到 flow_state** | `retrieved_report_id` |

**测试逻辑**:
- 用步骤 1 的 `report_id` 对应的 symbol 查询报告列表
- 断言：列表中包含步骤 1 创建的报告
- 断言：报告摘要字段一致（strategy_id, total_trades, total_pnl）
- 存储查询到的 report_id 到 `_flow3_state`

---

#### 步骤 3: 用户查看订单列表，验证 TP 订单存在

| 属性 | 值 |
|------|------|
| **测试名称** | `test_step3_query_orders_has_tp_entries` |
| **API** | `GET /api/v3/backtest/reports/{report_id}/orders` |
| **依赖** | 步骤 2 的 `report_id` |
| **输出到 flow_state** | `order_list`, `tp_order_ids` |

**测试逻辑**:
- 查询步骤 2 的报告订单列表
- 断言：订单列表中存在 `order_role` 为 TP1/TP2/TP3 的订单
- 断言：成交的 TP 订单数 >= 1（至少有 1 个止盈被执行）
- 存储所有成交的 TP 订单 ID 到 `_flow3_state`

---

#### 步骤 4: 用户验证 close_events 数据完整性和非零值

| 属性 | 值 |
|------|------|
| **测试名称** | `test_step4_close_events_nonzero_and_consistent` |
| **数据源** | 步骤 1 的 `report_json["close_events"]` |
| **依赖** | 步骤 1 + 步骤 3 |

**测试逻辑**:
- 从步骤 1 报告的 `close_events` 中验证：
  1. `close_events` 长度 > 0（有出场事件）
  2. 每个事件 `close_pnl ≠ 0`（撮合引擎正确写入，不是默认的 0）
  3. 每个事件 `close_fee > 0`（手续费计算正确）
  4. 每个事件 `close_qty > 0`、`close_price > 0`
  5. `event_type` 在 {"TP1", "TP2", "TP3", "SL"} 中
- **跨步骤一致性验证**:
  6. `close_events` 的 order_id 集合与步骤 3 的成交 TP 订单 ID 集合一致
  7. `sum(e.close_qty) == 对应仓位的初始 qty`（从 positions 反推）
  8. `sum(e.close_pnl) == 对应 position 的 realized_pnl`（PnL 不变量）

---

#### 步骤 5: 用户查看归因分析，验证归因数据正确

| 属性 | 值 |
|------|------|
| **测试名称** | `test_step5_attribution_analysis_valid` |
| **API** | `POST /api/backtest/{report_id}/attribution` |
| **依赖** | 步骤 2 的 `report_id` |

**测试逻辑**:
- 对步骤 2 的报告调用归因分析 API
- 断言：`status == "success"`, `attribution` 存在
- 断言：所有维度都存在：`shape_quality`, `filter_attribution`, `trend_attribution`, `rr_attribution`
- **数学可验证性**:
  - 从 `signal_attributions` 中取一个 attribution
  - 验证 `contribution = score × weight`（精确到 1e-6）
  - 验证 `sum(percentages.values()) ≈ 100`（容差 1%）
  - 验证 `final_score = sum(contribution for all components)`
- **前端契约验证**:
  - 所有 float 字段不为 None
  - 列表字段为空时返回 `[]` 而非 `null`
  - component name 映射正确（pattern/ema_trend/mtf）

---

#### 步骤 6: 用户交叉验证 — 回测报告内嵌归因与独立归因分析一致

| 属性 | 值 |
|------|------|
| **测试名称** | `test_step6_embedded_attribution_matches_analysis_api` |
| **依赖** | 步骤 1（内嵌归因）+ 步骤 5（独立归因 API） |

**测试逻辑**:
- 比较步骤 1 报告中的 `signal_attributions` 和步骤 5 归因分析 API 的结果
- 断言：`final_score` 一致（同一信号两次计算结果相同）
- 断言：`percentages` 各组件值一致
- 断言：`aggregate_attribution` 的 `avg_pattern_contribution` 一致
- **验证幂等性**：同一报告多次归因分析结果相同

---

### 测试执行流程

```python
_flow3_state = {}  # 跨步骤共享

class TestCloseAndAttributionFlow:
    """用户故事串联测试：回测 → 报告 → 订单 → close_events → 归因"""

    def test_step1_run_pms_backtest_with_multi_tp(self, test_client, mock_gateway):
        # POST /api/backtest/orders → store report_id, report_json

    def test_step2_query_report_list(self, test_client):
        # GET /api/v3/backtest/reports → verify report saved

    def test_step3_query_orders(self, test_client):
        # GET /api/v3/backtest/reports/{report_id}/orders → verify TP orders

    def test_step4_close_events_nonzero(self, test_client):
        # Verify close_events from step 1 report: non-zero, consistent

    def test_step5_attribution_analysis(self, test_client):
        # POST /api/backtest/{report_id}/attribution → verify attribution

    def test_step6_embedded_vs_api_consistency(self, test_client):
        # Compare embedded attribution with analysis API result
```

### 关键设计点

1. **数据串联**：步骤 2/3/5 都使用步骤 1 产生的 `report_id`，模拟用户在 UI 上点击不同 tab 的真实行为
2. **非 Mock 验证**：close_events 和 attribution 数据来自真实回测引擎，不是 Mock
3. **PnL 不变量**：`sum(close_pnl) == realized_pnl` 是最核心的业务规则验证
4. **前端契约**：步骤 5 验证 API 返回结构与前端 TypeScript 接口一致
5. **幂等性**：步骤 6 验证同一报告归因分析结果可重复

---

## 2026-04-15 -- 阶段 5 任务 5.2: AttributionEngine 核心引擎开发

### 背景
创建 AttributionEngine，基于 SignalAttempt dict 数据计算每个组件的信心评分，
聚合为最终归因结果。方案 B（非侵入式），不修改现有过滤器接口。

### 关键发现

**发现 1: 回测引擎序列化格式与任务 spec 不同**
- Backtester `_attempt_to_dict()` 使用 `pattern_score`（标量），不是 `pattern: {score: ...}`
- filter_results 格式为 `[{"filter": name, "passed": bool, ...}]`，不是 `[(name, FilterResult), ...]`
- **解决方案**: `_extract_pattern_score()` 和 `_parse_filter_results()` 两种格式兼容

**发现 2: pattern_score=0 但过滤器通过时 percentages 不应包含 0% 的 pattern**
- 原始实现: pattern 始终出现在 percentages 中（即使贡献为 0）
- **修复**: `_calc_percentages()` 只加入 contribution > 0 的组件
- 这使 zero-pattern 场景下 percentages 只包含有实际贡献的过滤器

**发现 3: ATR 过滤器名称兼容性**
- FilterFactory 注册了两个 key: "atr" 和 "atr_volatility"
- 实际运行时 filter name 是 "atr_volatility"
- 信心函数同时兼容两种名称: `if filter_name in ("atr", "atr_volatility")`

### 实现摘要

---

## 2026-04-15 -- 阶段 5 策略归因 — 代码审查分析

### 审查结论：有条件通过（2 个 P1 经分析为非问题）

**审查范围**: 11 个文件, +2486 / -675 行, 55 个测试全部通过
**完整性**: 22/22 验收标准全部通过

### P1 问题真实性分析

**P1-1: `attribution_engine.py` `_explain_confidence` 使用 float 除法**
- **结论**: 不是问题 — 审查员误判
- **理由**: 该方法仅生成人类可读的解释字符串（`str`），不参与任何金融计算。真正的计算方法 `_calculate_filter_confidence` 已全部使用 Decimal。float 偏差会被 `:.3f` 格式化截断。
- **处理**: 保持现状

**P1-2: `filter_factory.py` `distance_pct` 缺少 `ema_value == 0` 防御**
- **结论**: 理论问题，实际不可达
- **理由**: `current_trend is not None` 是前置条件，保证 EMA value 有效。加密货币价格永远为正，EMA 不可能为 0。`ema_value is not None` 防御已存在。
- **处理**: 保持现状

### 代码质量评分

| 指标 | 评分 |
|------|------|
| 领域层纯净性 | A |
| Decimal 使用 | B+ |
| 类型安全 | B- |
| 错误处理 | B |
| 测试覆盖 | A |
| 前端一致性 | A- |
| 安全隐患 | A |

**综合评分**: B+（有条件通过）

---

## 2026-04-15 -- 阶段 5 策略归因 — 全部完成

### 任务完成情况

| 任务 | 内容 | 状态 |
|------|------|------|
| 5.3 | 补充过滤器 metadata | ✅ 已完成 |
| 5.1 | AttributionConfig 模型 + 20 UT | ✅ 已完成 |
| 5.2 | AttributionEngine 核心 + 35 UT | ✅ 已完成 |
| 5.4 | 集成到回测报告输出 | ✅ 已完成 |
| 5.5 | 前端归因可视化 | ✅ 已完成 |

### Git 提交

- `4e77b8d` — feat(attribution): 阶段 5 策略归因 - 5.1/5.2/5.3 任务完成
- `2019530` — feat(frontend): 阶段 5.5 — 前端归因可视化

---

## 2026-04-15 -- 阶段 5 任务 5.2: AttributionEngine 核心引擎开发

| 文件 | 内容 |
|------|------|
| `src/application/attribution_engine.py` | AttributionEngine 核心 + 4 个响应模型 |
| `tests/unit/test_attribution_engine.py` | 35 个单元测试，覆盖正常/异常/边界场景 |

### 核心方法
- `attribute(attempt_dict)` — 单信号归因
- `attribute_batch(attempts)` — 批量归因
- `get_aggregate_attribution(attributions)` — 聚合归因

### 信心函数表
| 过滤器 | 公式 | 默认值 |
|--------|------|--------|
| ema_trend/ema | `min(distance_pct / 0.05, 1.0)` | 0.5 |
| mtf | `aligned_count / total_count` | 0.5 |
| atr/atr_volatility | `min(volatility_ratio / 2.0, 1.0)` | 0.5 |
| 未知 | -- | 0.5 |

### 测试验证
- `test_attribution_engine.py`: 35/35 passed
- 回归测试: `test_attribution_config.py` 20/20 passed, `test_attribution_analyzer.py` 20/20 passed
- Import 验证: 无循环导入

---
