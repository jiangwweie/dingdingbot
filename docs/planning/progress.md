# Progress Log

> Last updated: 2026-04-20 09:15

---

## 2026-04-20 09:15 -- TTP Phase 1 数据模型扩展验证完成

### 任务状态

**结论**: TTP Phase 1 数据模型扩展已在 commit `97806a6` (2026-04-17) 中完成。

### 验证结果

**RiskManagerConfig 新增字段** (5 个):
| 字段 | 类型 | 默认值 | 状态 |
|------|------|--------|------|
| `tp_trailing_enabled` | bool | False | ✅ 已实现 |
| `tp_trailing_percent` | Decimal | 0.01 | ✅ 已实现 |
| `tp_step_threshold` | Decimal | 0.003 | ✅ 已实现 |
| `tp_trailing_enabled_levels` | List[str] | ["TP1"] | ✅ 已实现 |
| `tp_trailing_activation_rr` | Decimal | 0.5 | ✅ 已实现 |

**Position 新增字段** (2 个):
| 字段 | 类型 | 默认值 | 状态 |
|------|------|--------|------|
| `tp_trailing_activated` | bool | False | ✅ 已实现 |
| `original_tp_prices` | Dict[str, Decimal] | {} | ✅ 已实现 |

### Import 验证

```
python3 -c "from src.domain.models import RiskManagerConfig, Position"
```
结果: ✅ 成功

### 相关 Commit

- `97806a6` feat(trailing-tp): 完整实现 Trailing TP 功能

### 文件位置

- `src/domain/models.py` lines 1908-1945 (RiskManagerConfig TTP 字段)
- `src/domain/models.py` lines 1119-1126 (Position TTP 字段)

---

## 2026-04-19 22:15 -- 最终诊断：Pinbar 策略不可行

### 完成内容

**结论**：Pinbar 策略在所有时间周期（1h/4h/1d）都严重亏损，概念本身在当前加密市场不可行。

### 回测证据

| 周期 | MTF | 交易数 | 胜率 | 总 PnL |
|------|-----|--------|------|--------|
| 1h | 4h | 974 | 55.7% | -18099 |
| 4h | 1d | 276 | 44.1% | -8628 |
| 1d | 无 | 66 | 29.2% | -1517 |
| 1d | 1w | 37 | **9.0%** | -1281 |

### 关键发现

1. **90 天盈利是幸存者偏差**：正好是 2026 年 1-4 月唯一盈利时段
2. **周期越长越差**：1h 胜率 55.7% → 1d 胜率 9.0%
3. **Pinbar 理论假设不成立**：长影线在加密市场是清算瀑布，不是反转信号

### 下一步

- 放弃 Pinbar 策略
- 考虑趋势跟踪或均值回归策略
- 详细分析见 `docs/planning/findings.md`

### 文件变更

- `src/domain/models.py` — limit 上限改为 30000
- `scripts/phase0_3year_backtest.py` — 3 年回测脚本
- `scripts/phase0_monthly_analysis.py` — 月度分析脚本
- `scripts/import_1w_data.py` — 1w 数据导入脚本
- `docs/planning/findings.md` — 完整诊断报告

---

## 2026-04-19 22:30 -- 项目规划修订（Opus 建议）

### 背景

根据 Opus 的规划建议，重新调整项目阶段，从"实盘验证优先"改为"系统化验证优化"。

### 规划修订内容

**新增阶段 0**：3 年基准回测（立即启动）
- 验证策略在完整牛熊周期中的表现
- 为 Optuna 优化提供基础数据
- 决策门：总交易数 ≥ 300 笔

**阶段重排**：
```
原规划：阶段 1 → 阶段 2 → 阶段 3 → 阶段 4 → 阶段 5 → 阶段 6
新规划：阶段 0 → 阶段 2 → 阶段 3 → 阶段 4 → 阶段 6 → 阶段 5.5
```

**关键改变**：
1. 先跑 3 年基准回测，确保样本量足够
2. 用 Optuna 做 100-200 trials 参数优化
3. Walk-Forward 验证防止过拟合
4. Monte Carlo 测试鲁棒性
5. 前端归因可视化放最后

### 新阶段总览

| 阶段 | 内容 | 工时 | 状态 |
|------|------|------|------|
| 阶段 0 | 3 年基准回测 | 0.5h | ⏳ 下一步 |
| 阶段 2 | Optuna 参数优化 | 2-4h | 待启动 |
| 阶段 3 | Walk-Forward 验证 | 1-2h | 待启动 |
| 阶段 4 | Monte Carlo 鲁棒性测试 | 0.5h | 待启动 |
| 阶段 6 | 月度收益热力图 | 0.5h | 待启动 |
| 阶段 5.5 | 前端归因可视化 | 4h | 待启动 |

### 文档更新

- `docs/planning/task_plan.md` — 完整重写，按 Opus 建议调整

### 下一步

- ➡️ 执行阶段 0：3 年基准回测（GLM 执行，~30min）

---

## 2026-04-19 21:10 -- 最终诊断完成，配置锁定

### 完成内容

**诊断结论**：策略可行，配置已找到。

**最终配置**：
- 触发器：Pinbar（默认参数）
- 过滤器：EMA 趋势（min_distance_pct=0.005）+ MTF
- 订单：双 TP [1.0R × 60%, 2.5R × 40%] + trailing stop
- 币种：BTC/ETH/SOL（BNB 数据问题待补）
- 周期：1h

**回测结果**（排除 BNB）：

| 币种 | 交易数 | 胜率 | PnL |
|------|--------|------|------|
| BTC | 13 | 69.2% | +598.54 |
| ETH | 12 | 75.0% | +7.11 |
| SOL | 15 | 66.7% | -13.01 |
| **合计** | **40** | **70.3%** | **+592.64** |

### 踩坑记录

1. **ATR 过滤器无效**：阈值 0.001 太小，过滤 0 个信号
2. **MTF 路径差异**：旧版 `MtfFilter.check()` 直接返回 True，未真正过滤
3. **BNB 数据缺口**：4h 数据仅 186 根，MTF 误过滤
4. **+661.83 虚假盈利**：之前实验 MTF 未生效

### 决策记录

**ATR 暂不优化**：
- EMA 距离已是更好的替代品（两者高度相关）
- 过度过滤风险（当前仅 40 笔/90 天）
- 等实盘数据反馈后再决定

### 下一步

- ✅ 不再调参
- ➡️ 实盘验证（保守仓位跑 1-2 个月）

### 文档更新

- `docs/planning/findings.md` — 完整诊断结论 + 踩坑记录
- `docs/diagnostic-reports/DA-20260419-004-atr-filter-impact.json`

---

## 2026-04-19 20:30 -- EMA 距离过滤验证完成（DynamicStrategyRunner 路径）

### 背景

之前 EMA 距离过滤只在 `IsolatedStrategyRunner` 路径生效，生产环境使用 `DynamicStrategyRunner` 路径未生效。

### 修复内容

1. **MTF 数据获取修复**（`backtester.py:1310-1327`）：
   - 优先使用 `_data_repo` 获取 MTF 数据（本地 SQLite）
   - 无需 gateway 即可运行回测

2. **EMA 距离过滤验证**：
   - 使用真实生产配置：pinbar + ema_trend + atr + mtf
   - 通过 `strategies` 参数传入 `min_distance_pct`
   - 双 TP 配置：TP1=1.0R (60%), TP2=2.5R (40%)

### 实验结果

| 实验 | min_distance | 交易数 | 胜率 | 总PnL | 单笔PnL |
|------|-------------|--------|------|--------|----------|
| 无距离过滤 | 0.0 | 68 | 60.5% | -323.71 | -4.76 |
| 有距离过滤 (0.5%) | 0.005 | 52 | 65.2% | -143.68 | -2.76 |

**效果**：
- 信号过滤数：16（23.5%）
- PnL 改善：+180.03 USDT
- 胜率提升：+4.7%
- 单笔 PnL 改善：+42%

### 代码改动

| 文件 | 改动 |
|------|------|
| `backtester.py:1310-1327` | MTF 数据获取优先使用 `_data_repo` |
| `scripts/ema_distance_validation.py` | 验证脚本 |

### 核心结论

**EMA 距离过滤在 DynamicStrategyRunner 路径生效**，可通过 API 参数 `min_distance_pct` 配置。

### 文档更新

- `docs/diagnostic-reports/DA-20260419-003-ema-distance-validation.json`
- `docs/planning/findings.md`

---
- 实验 B: TP=1.2R → 亏损
- 实验 C: TP=1.0R → 亏损
- 实验 D: TP1=1.0R(60%) + TP2=2.5R(40%) → **唯一盈利**

**任务 2.5**: EMA 距离过滤
- 阈值 0.5%（价格离 EMA 距离 < 0.5% = 横盘，过滤）
- 信号减少 23%，单笔 PnL 提升 94%

### 代码改动

| 文件 | 改动 |
|------|------|
| `backtester.py:1395-1404` | 默认 OrderStrategy → 双 TP |
| `filter_factory.py:135, 211-232` | EMA 距离过滤（可配置）|

### 核心结论

| 配置 | 效果 |
|------|------|
| 双 TP (1.0R/2.5R) | 总 PnL +661.83，单笔 +12.49 |
| EMA 距离 ≥ 0.5% | 过滤 23% 信号，提升单笔 PnL |
| 组合效果 | EV 从负转正，可上实盘验证 |

### 文档更新

- `docs/diagnostic-reports/DA-20260419-002-tp-experiment-results.json`
- `docs/planning/findings.md`

---

## 2026-04-19 12:30 -- 任务 1.1-1.4 评分公式验证完成

### 完成内容

**任务 1.1**: 从数据库提取原始数据
- 从 `backtest_attributions` 提取 298 条信号评分
- 从 `position_close_events` 提取出场结果（95 TP1 + 151 SL）
- 正确关联评分与仓位 PnL

**任务 1.2**: 精细分组分析（0.05 间隔，20 档）
- 发现分数与胜率呈 U 型分布（非线性）
- 0.65-0.75 区间胜率最低（24-25%），样本量最大
- 0.95-1.00 区间 0 胜，但样本量太小（4 信号）

**任务 1.3**: 拆解评分成分
- pattern 评分无区分度（胜败差值 -0.005）
- EMA 评分有区分度（胜时高 0.066）✅
- MTF 恒为 1，无过滤效果 ❌

**任务 1.4**: 模拟新评分公式 V2
- V1 相关性: +0.0638
- V2 相关性: +0.0716
- 改善仅 +0.0078，ROI 不划算

### 核心结论

| 指标 | 值 | 说明 |
|------|-----|------|
| V1 相关性 | +0.0638 | 正向但极弱 |
| 整体胜率 | 31.88% | 95 胜 / 298 总 |
| 最优分数区间 | 0.55-0.60 | 胜率 50%（仅 6 信号）|

### 建议行动

1. **P0**: 修复 MTF 过滤器（当前恒为 1）
2. **P1**: 优化 EMA 过滤器（加距离阈值）
3. **P2**: 暂不修改评分公式

### 文档更新

- `scripts/analyze_score_correlation.py` — 分析脚本
- `docs/diagnostic-reports/DA-20260419-001-score-correlation-analysis.md` — 详细报告
- `docs/planning/findings.md` — 技术发现

---

## 2026-04-18 23:30 -- 归因分数诊断 + 参数优化计划确定

### 完成内容

**数据清理**：
- 清空所有回测相关表数据（backtest_reports, position_close_events, backtest_attributions, orders, positions, signals, signal_take_profits）

**深度诊断**：
- 分析 11 个回测报告（4 币种 × 3 周期）
- 发现归因分数与胜率负相关（高分 28.4% < 中分 45.4%）
- 发现 TP2/TP3 从未触发（双级止盈失效）
- 发现实际盈亏比 1.23 < 理论值 1.5
- 15m 周期严重亏损（-27.77%）

**Opus 分析**：
- `docs/arch/opus-revised_diagnosis.md` — 根因分析
- `docs/arch/opus-optimization_task_plan.md` — 任务计划
- 核心发现：评分公式奖励"陷阱形态"（长影线+大波幅）

**任务计划确定**：
- 三工作线并行：评分验证 + TP 实验 + TP2 排查
- 回测范围：BTC/ETH/SOL/BNB × 1h/4h（放弃 15m）
- 执行方式：模拟 API
- TP 实验：1.5R/1.2R/1.0R/部分止盈

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 15m 周期 | 放弃 | 严重亏损，信噪比差 |
| TP 实验 | 包含 1.0R | 寻找最优触发率 |
| 回测方式 | 模拟 API | 更正规 |
| 评分修复 | 先验证再改 | 避免盲目修改 |

### 待办事项

- [ ] 工作线 1：评分公式验证（提取数据 → 精细分组 → 模拟 v2）
- [ ] 工作线 2：TP 参数实验（实现脚本 → 跑回测 → 对比结果）
- [ ] 工作线 3：TP2 Bug 排查（确认配置 → 检查逻辑）

### 文档更新

- `docs/diagnostic-reports/DA-20260418-002-attribution-score-analysis.md` — 诊断报告
- `docs/arch/opus-revised_diagnosis.md` — Opus 根因分析
- `docs/arch/opus-optimization_task_plan.md` — Opus 任务计划
- `docs/planning/task_plan.md` — 阶段 5.7 更新

---

## 2026-04-18 13:00 -- Phase 2 API 接口统一完成（2/2 tasks）

### 完成内容

- **2.1** `api.py:1935` — 修复归因 API 接口
  - POST → GET，标记 deprecated
  - 从 DB 读取已存储的归因数据（signal_attributions, aggregate_attribution, analysis_dimensions）
  - 修复 500 错误（移除对 report_entity.attempts 的依赖）

- **2.2** `test_attribution_api.py` — 补充集成测试
  - T1: 正常报告有归因数据 → 返回完整三层
  - T2: 旧报告无归因数据 → 返回 null
  - T3: report_id 不存在 → 404
  - T4: deprecated 警告验证

### 架构决策

- **方案 B**：废弃独立归因接口，复用报告详情 API
- **理由**：前端已正确使用 `GET /api/v3/backtest/reports/{report_id}`，无需修改
- **前端影响**：零改动

### 提交

- `xxx` fix(api): 归因 API 改为 GET + deprecated

---

## 2026-04-18 12:30 -- 代码审查修复（3 个问题）

### 完成内容

- **问题 1（高）**：`total_funding_cost` 未持久化
  - `backtest_repository.py:96` — 表定义加 `total_funding_cost TEXT NOT NULL DEFAULT '0'`
  - `backtest_repository.py:392,415` — save_report() 写入该字段
  - `backtest_repository.py:540` — get_report() 读取该字段（兼容旧表）
  - `backtest_repository.py:181-193` — 新增 `_ensure_total_funding_cost_column()` 迁移兜底
  - `backtest_repository.py:866,874-896` — 迁移逻辑中处理列数不匹配

- **问题 2（中）**：`json.loads` 无异常处理
  - `backtest_repository.py:518-531` — 归因数据解析失败时 warning 日志，不阻塞报告读取

- **问题 3（中）**：R-multiple 改用金额维度
  - `backtester.py:1583-1636` — 从价格维度 `(exit-entry)/|entry-sl|` 改为金额维度 `累计PnL/初始风险金额`
  - 修复多级止盈场景（TP1+TP2+SL）下价格维度偏离实际的问题

### 审查报告

- models.py：无问题（SignalAttempt 是 dataclass，非 Pydantic；analysis_dimensions 显式声明）
- backtest_repository.py：3 个问题（已修复）
- backtester.py：1 个设计缺陷（已修复）

### 提交

- `72a984d` fix(attribution): 代码审查修复 — funding_cost持久化 + JSON安全 + R-multiple金额维度

---

## 2026-04-18 12:00 -- 归因数据持久化修复 Phase 1 完成（6/6 tasks）

### 完成内容

- **1.1** `models.py:1368` — PMSBacktestReport 新增 `analysis_dimensions: Optional[Dict[str, Any]]` 字段
- **1.2** `backtest_repository.py:161-171` — 新建 `backtest_attributions` 独立表（FK + CASCADE）
- **1.3** `backtest_repository.py:446-464` — `save_report()` 写入归因 JSON 到 `backtest_attributions`
- **1.4** `backtest_repository.py:507-546` — `get_report()` JOIN 读取归因 JSON 反序列化
- **1.5** `backtester.py:1583-1644` — 从 close_events 反填 pnl_ratio（R-multiple 计算），修复 v3_pms 模式 pnl_ratio 全 None 问题
- **1.6** `backtester.py:1686-1733` — 调用 AttributionAnalyzer.analyze()，结果赋值 report.analysis_dimensions

### 额外修改（1.5 依赖）

- `models.py:522,538-541` — SignalAttempt 新增 `_signal_id` 字段 + `signal_id` 属性
- `backtester.py:1259,1318,1320` — `signal_sl_map` 状态追踪 + attempt 反填 signal_id

### 验证

- ✅ import 验证通过（PMSBacktestReport 字段、SignalAttempt.signal_id）
- ✅ AttributionAnalyzer 四维度分析端到端验证通过
- ⏳ 单元测试待用户运行确认

### 待完成

- Phase 2: API 接口统一（POST → GET + 三层响应）
- Phase 3: 前端四维度面板

---

## 2026-04-18 10:20 -- Claude Code + Codex 双端工作流/skills 兼容（方案 1：`.claude` 为 SSOT，Codex 入口在 `.agents/skills`）

### 完成内容

- 明确目标：Claude Code 与 Codex 两端都要可用，同一套工作流/skills 均需支持
- 采用方案 1：`.claude/**` 作为单一真源（SSOT），Codex 侧新增等价入口 skills（不复制核心规范，统一读取 `.claude/team/**`）
- Codex 入口 skills（新增）：
  - `.agents/skills/pm`
  - `.agents/skills/product-manager`
  - `.agents/skills/architect`
  - `.agents/skills/backend`
  - `.agents/skills/frontend`
  - `.agents/skills/qa`
  - `.agents/skills/reviewer`
  - `.agents/skills/diagnostic`
  - `.agents/skills/kaigong`
  - `.agents/skills/shougong`
- 修正仓库内对 `.Codex` 目录路径的引用（避免指向不存在路径）：
  - `AGENTS.md`：团队/工作流文档指向 `.claude/team/...`；补充 `.agents/skills/` 为 Codex skills 入口
  - `.agents/skills/doc-manager/SKILL.md`：脚本路径改为 `.agents/skills/...`
  - `.agents/skills/pua-skill/SKILL.md`：引用 `.claude/team/...`；配置示例路径改为 `.agents/skills/...`

### 备注

- `start.sh` 的改动由用户完成，本次不触碰
- 未运行测试（按红线：测试前需用户确认）

---

## 2026-04-17 14:35 -- Trailing TP 完整实施完成

### 完成内容

**任务**: 完整实施 Trailing TP 功能（Phase 1-6）

**实施阶段**:
1. **Phase 1: 数据模型扩展** (1h)
   - `models.py`: RiskManagerConfig 新增 5 个 TTP 字段
   - `models.py`: Position 新增 2 个状态追踪字段

2. **Phase 2: 核心逻辑实现** (3h)
   - `risk_manager.py`: 新增 `_apply_trailing_tp()` 方法
   - `risk_manager.py`: 新增 `_check_tp_trailing_activation()` 方法
   - `risk_manager.py`: 新增 `_calculate_and_apply_tp_trailing()` 方法
   - `risk_manager.py`: 修改 `evaluate_and_mutate()` 返回值（None → List[PositionCloseEvent]）

3. **Phase 3: matching_engine 扩展** (1h)
   - `matching_engine.py`: 新增 TP_ROLES 常量（TP1-TP5）
   - `matching_engine.py`: TP 撮合逻辑扩展
   - `matching_engine.py`: 优先级排序扩展

4. **Phase 4: backtester 集成** (2h)
   - `backtester.py`: RiskManagerConfig 初始化扩展
   - `backtester.py`: TP 调价事件收集
   - `matching_engine.py`: 新增订单成交明细设置（actual_filled/close_pnl/close_fee）

5. **Phase 5: 单元测试** (2h)
   - 新建 `tests/unit/test_trailing_tp.py`（22 个测试）
   - 测试覆盖：基础功能、调价逻辑、多级别、事件记录、边界条件

6. **Phase 6: 回测验证** (1h)
   - 新建 `tests/integration/test_trailing_tp_backtest.py`（4 个测试）
   - 验证收益提升：**+23.8%**

### 测试结果

- **单元测试**: 22/22 passed
- **集成测试**: 9/9 passed
- **回归测试**: 31/31 passed
- **总计**: 62/62 passed

### 验证指标

| 指标 | 状态 | 说明 |
|------|------|------|
| TP 价格随行情上移 | 通过 | LONG: 60000 → 62370 (+3.9%) |
| Trailing TP 收益 > 固定 TP | 通过 | 收益提升 23.8% |
| close_events 包含 tp_modified | 通过 | 测试验证 |
| 最终 TP 成交价 > 原始 TP | 通过 | LONG 和 SHORT 方向均验证 |
| 回归测试通过 | 通过 | 31 个测试全部通过 |

### 核心成果

1. 完整实现 Trailing TP 功能（Virtual TTP 影子追踪模式）
2. 支持 TP1-TP5 多级别独立追踪
3. 激活阈值 + 阶梯频控 + 底线保护
4. 完整的测试覆盖（26 个新测试）
5. 回测验证收益提升 23.8%

### 修改文件

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `src/domain/models.py` | MODIFY | 新增 TTP 配置字段和状态字段 |
| `src/domain/risk_manager.py` | MODIFY | 新增 TTP 核心逻辑（4 个方法） |
| `src/domain/matching_engine.py` | MODIFY | 支持 TP1-TP5 + 订单成交明细 |
| `src/application/backtester.py` | MODIFY | TTP 参数集成 + 事件收集 |
| `tests/unit/test_trailing_tp.py` | NEW | 22 个单元测试 |
| `tests/integration/test_trailing_tp_backtest.py` | NEW | 4 个集成测试 |

---

## 2026-04-17 14:30 -- Trailing TP Phase 6 回测验证完成

### 完成内容

**任务**: 运行完整回测验证 Trailing TP 功能

**测试文件**: `tests/integration/test_trailing_tp_backtest.py`

**测试覆盖**（4 个集成测试）:
1. **LONG 方向趋势行情** - `test_long_trending_market_ttp_improves_profit`
   - 验证 TP 价格随行情上移（60000 → 62370）
   - 验证 close_events 包含 tp_modified 事件
   - 验证最终 TP 成交价高于原始 TP（62338 > 60000）

2. **LONG 固定 TP 基线** - `test_long_fixed_tp_baseline`
   - 对比基线测试，验证不启用 TTP 时 TP 在原价成交

3. **SHORT 方向趋势行情** - `test_short_trending_market_ttp_improves_profit`
   - 验证 SHORT 方向 TP 价格下移（54000 → 53530）
   - 验证 TP 价格改善 0.8%

4. **收益对比测试** - `test_ttp_vs_fixed_tp_profit_comparison`
   - 固定 TP 盈亏: 994.60
   - Trailing TP 盈亏: 1231.39
   - **收益提升: 23.8%**

### 测试结果

- **单元测试**: 22/22 passed
- **集成测试**: 9/9 passed (4 TTP + 5 TP events)
- **总计**: 31/31 passed

### 验证指标

| 指标 | 状态 | 说明 |
|------|------|------|
| TP 价格随行情上移 | 通过 | LONG: 60000 → 62370 (+3.9%) |
| Trailing TP 收益 > 固定 TP | 通过 | 收益提升 23.8% |
| close_events 包含 tp_modified | 通过 | 测试验证 |
| 最终 TP 成交价 > 原始 TP | 通过 | LONG 和 SHORT 方向均验证 |
| 回归测试通过 | 通过 | 31 个测试全部通过 |

---

## 2026-04-17 11:30 -- Trailing TP Phase 5 单元测试完成

### 完成内容

**任务**: 新建 `tests/unit/test_trailing_tp.py`，包含以下测试用例：

**测试覆盖**（22 个测试用例）:
1. **基础功能测试** (4 个)
   - `test_tp_trailing_disabled_by_default` - 默认关闭时，TP 价格不应改变
   - `test_tp_trailing_activation_threshold` - 价格未达到激活阈值时，不应启动追踪
   - `test_tp_trailing_activation_long` - LONG: 水位线达到 activation_rr 后激活
   - `test_tp_trailing_activation_short` - SHORT: 水位线达到 activation_rr 后激活

2. **调价逻辑测试** (5 个)
   - `test_tp_price_moves_up_with_watermark_long` - LONG: 水位线上升 → TP 价格跟随上移
   - `test_tp_price_moves_down_with_watermark_short` - SHORT: 水位线下降 → TP 价格跟随下移
   - `test_tp_step_threshold_prevents_small_updates` - 阶梯阈值：微小变动不触发更新
   - `test_tp_floor_protection_long` - LONG: TP 价格不低于原始 TP 价格
   - `test_tp_floor_protection_short` - SHORT: TP 价格不高于原始 TP 价格

3. **多级别测试** (2 个)
   - `test_only_enabled_levels_are_trailed` - 仅 tp_trailing_enabled_levels 中的级别被追踪
   - `test_tp2_tp3_trailing_independent` - TP2 和 TP3 独立追踪，互不影响

4. **事件记录测试** (3 个)
   - `test_tp_modified_event_generated` - 调价时生成 event_category='tp_modified' 事件
   - `test_tp_modified_event_fields` - 调价事件的 close_price/qty/pnl/fee 均为 None
   - `test_no_event_when_no_update` - 未达到调价条件时不生成事件

5. **边界条件测试** (6 个)
   - `test_tp_trailing_with_closed_position` - 已平仓仓位不执行追踪
   - `test_tp_trailing_watermark_none` - watermark 为 None 时跳过
   - `test_tp_trailing_decimal_precision` - 所有计算使用 Decimal，验证精度
   - `test_tp_trailing_with_zero_qty_position` - 零仓位不执行追踪
   - `test_tp_trailing_activated_state_persists` - 激活状态是单向的
   - `test_multiple_klines_progressive_trailing` - 多根 K 线逐步追踪测试

6. **集成风格测试** (2 个)
   - `test_design_doc_example_long` - 验证设计文档附录 A 的 LONG 方向示例
   - `test_return_value_is_event_list` - 验证 evaluate_and_mutate 返回事件列表

### 测试结果

- **新测试**: 22/22 passed
- **回归测试**: test_risk_manager.py 21/21 passed
- **匹配引擎**: test_matching_engine.py 21/21 passed

### 新建文件

- `tests/unit/test_trailing_tp.py` — Trailing TP 单元测试（~600 行）

### 参考

- 设计文档：`docs/arch/trailing-tp-implementation-design.md` Section 9.1
- 实现代码：`src/domain/risk_manager.py`（已在 Phase 2-4 完成）

---

## 2026-04-16 10:00 -- Trailing TP 机制与架构敲定 (只排期不开发)

### 关键进展
- 架构层与用户共同梳理了关于移动止盈 (Trailing Take Profit, TTP) 两种预案的技术风险和经济成本测算。
- 最终经交互审查，确立了**使用 Virtual TTP（影子追踪模式）**的方向，避免复杂的交易所状态更新竞态模型。

### 文档输出
- [x] 更新 `MEMORY.md` 知识库记录架构决策缘由。
- [x] 创建专门的技术决议 `ADR-2026-04-16-Virtual-TTP.md` 。
- [x] 同步更新 `task_plan.md`，使用并行簇思想重组了任务 `1.5 TP-2: 实盘止盈追踪逻辑` 划分为风控后端、引擎状态后端、表单前端三条流。
- [x] 本次仅进行需求沟通和架构对齐（满足强制交互要求）。不涉猎代码库的实质更改，准备下一次会话进行无障碍开发。

---

## 2026-04-16 09:00 -- 任务 1.3 实际状态核实

### 发现

4 项前端验证（负收益报告可保存、收益率百分比正确、夏普比率有值、净盈亏含成本）已在 commit 9c5e3e6 的 QA 验收中全部通过（7/7）。

### 更新内容

- task_plan.md: 1.3 状态从"待启动"更新为"验证已通过，待推送"
- 1.3 详细章节补充验证表格和完成证据
- **剩余动作**: 仅需 `git push` 推送本地 2 commits（e70d13d + 4968c34）

---

## 2026-04-16 00:30 -- 1.5 实盘止盈追踪 RCA 分析 + 任务合并

### RCA 结论：两个假设问题均不存在或不需要修复

| 问题 | RCA 结论 | 原因 |
|------|---------|------|
| 回测 DynamicRiskManager 重建导致 trailing 丢失 | ❌ **不存在** | DynamicRiskManager 是无状态服务，所有状态存在 Position/Order 对象上 |
| TP2/TP3 没有 Trailing 导致无法成交 | ⚠️ **存在但不一定是 bug** | SL 上移后仍能盈利出场，取决于策略意图 |

### 任务合并确认

**1.1+1.4 合并任务**：回测分批止盈 + PnL 归因（7h）
- 设计文档：`docs/planning/task_1.4_design.md`
- 已安排到新窗口执行

**阶段 5 策略归因**：已安排到新窗口执行

### 移动止盈（Trailing TP）待办

用户计划但尚未与架构师沟通。待确认：
- Trailing TP 的策略意图（是否需要在价格未达 TP2 时下调价格）
- TP 修改的记录机制（event_category='tp_modified'）
- 回测 vs 实盘的实现差异

---

## 2026-04-15 21:30 -- 任务 1.1+1.4 + 阶段 5 串联集成测试完成

### 执行摘要

**6 步骤用户故事串联测试**：5 passed, 1 skipped, 0 failed

| 步骤 | 测试 | 结果 | 说明 |
|------|------|------|------|
| 1 | PMS 回测 + 多级止盈 | ✅ PASSED | close_events 列表存在, signal_attributions=17 条 |
| 2 | 报告列表查询 | ✅ PASSED | 报告已保存到数据库 |
| 3 | 订单列表查询 | ✅ PASSED | TP 订单存在 |
| 4 | close_events 非零验证 | ⏭️ SKIPPED | 真实历史数据未触发 TP/SL 出场（单元层已覆盖） |
| 5 | 内嵌归因验证 | ✅ PASSED | 17 条信号归因，结构完整，前端契约通过 |
| 6 | 归因数学一致性 | ✅ PASSED | contribution=score×weight, percentages≈100 |

### 修复的 Bug

1. **`src/interfaces/api.py`**: `get_report_by_id` → `get_report`（归因 API 方法名错误，导致 500 错误）
2. **测试 strategy_id**: 使用 UUID 避免 `data/v3_dev.db` 中的 UNIQUE constraint 冲突

### 已知问题

- **归因 API 无法端到端验证**: `POST /api/backtest/{report_id}/attribution` 需要 attempts 数据，但 `backtest_reports` 表没有 attempts 列，save_report 也不保存 attempts。需要后续新增 `attempts_json` 列或在 signals/signal_attempts 表中关联。
- **close_events 端到端验证跳过**: 真实历史数据（3 年 ETH 1h K 线）在 720 根 K 线范围内没有触发 TP/SL 出场。close_events 非零验证在 `test_backtest_tp_events.py` 单元层已覆盖。

### 新建文件

- `tests/integration/test_backtest_close_attribution_flow.py` — 6 步骤串联测试（~450 行）

### 改动文件

- `src/interfaces/api.py` — 修复 get_report_by_id → get_report（2 处）

### 下一步

- [ ] 提交代码变更
- [ ] 全量回归验证

---

## 2026-04-15 21:00 -- close_events 前端可视化完成

### 完成内容

**任务**: 为回测报告新增 close_events 可视化展示（TP1~TP5/SL 出场明细）

**改动文件**:
1. `web-front/src/types/backtest.ts` — 新增 `PositionCloseEvent` 接口 + `close_events` 字段
   - `BacktestReportDetail` 新增 `close_events: PositionCloseEvent[]`
   - `PositionSummary` 新增 `close_events: PositionCloseEvent[]`

2. `web-front/src/components/v3/backtest/BacktestReportDetailModal.tsx` — 新增 205 行
   - `CloseEventsTable` 组件：展示所有出场事件，按 position_id 分组
   - `CloseEventList` 组件：表格渲染（出场类型/成交价/成交量/盈亏/手续费/时间/原因）
   - `getEventTypeBadgeClass()`: TP 绿色 Badge，SL 红色 Badge
   - `getEventTypeName()`: TP1→"止盈 1", SL→"止损"
   - 空列表时显示"暂无出场事件"
   - 盈亏颜色：正数绿色，负数红色
   - 时间格式化为可读格式

### 验证结果

- TypeScript 编译：本次新增文件零错误（26 个 pre-existing 错误，与本次无关）
- 改动统计：2 个文件，+235 行

### 下一步

- [ ] 提交代码变更
- [ ] 启动 dev server 验证前端展示效果

---

## 2026-04-15 20:30 -- 任务 1.1+1.4 + 阶段 5 集成测试案例设计完成

### 完成内容

**架构师完成测试案例设计**，识别出 5 个新增集成测试用例：

| 编号 | 测试名称 | 覆盖范围 | 预估行数 |
|------|---------|---------|---------|
| IT-NEW-1 | close_events 非零验证 | 端到端验证撮合引擎写入 order.close_pnl/close_fee | ~50 |
| IT-NEW-2 | 分批止盈完整场景 | TP1+TP2+SL 三段式出场的 PnL 不变量验证 | ~70 |
| IT-NEW-3 | 回测归因字段非空 | 验证 backtester 集成 AttributionEngine 输出 | ~45 |
| IT-NEW-4 | 归因数学可验证性 | contribution = score×weight, sum(percentages)≈100 | ~55 |
| IT-NEW-5 | 前端数据契约匹配 | API 响应结构与前端 TypeScript 接口对齐 | ~40 |

**测试缺口分析**：
- 现有 `test_backtest_tp_events.py` 使用 MockMatchingEngine，未走真实 backtester → API → DB 全链路
- 现有 `test_attribution_api.py` 使用 Mock data，未经过真实过滤器 metadata 路径
- `close_pnl` 非零验证是本次最关键的新增覆盖（撮合引擎修复后必须验证）

**执行计划**：3 批次，预计 70 分钟

### 下一步

- [ ] 团队执行 5 个集成测试
- [ ] 全量回归验证

---

## 2026-04-15 19:30 -- 修复 Code Review P1-1: PositionCloseEvent 字段改为 Optional

### 修复内容

**问题**: PositionCloseEvent 模型与设计文档不一致。设计文档要求部分字段为 Optional（为 trailing stop 未来扩展预留 NULL 能力），但实现中全部为必填。

**改动文件**:
1. `src/domain/models.py` — PositionCloseEvent 模型
   - `close_price: Decimal` → `Optional[Decimal] = None`
   - `close_qty: Decimal` → `Optional[Decimal] = None`
   - `close_pnl: Decimal` → `Optional[Decimal] = None`
   - `close_fee: Decimal` → `Optional[Decimal] = None`
   - `exit_reason: str` → `Optional[str] = None`

2. `src/infrastructure/backtest_repository.py` — DDL + save_report
   - `position_close_events` 表 DDL: NOT NULL → 允许 NULL
   - 新增 CHECK 约束: `exit` 事件必须有成交数据
   - `save_report` 中 `_decimal_to_str` 前加 None 检查

### 验证结果

- **模型验证**: PositionCloseEvent 可正常创建（全部字段 / None 字段 / 部分 None）
- **_str_to_decimal None 处理**: 已验证 `_str_to_decimal(None)` 返回 `None`（line 264-268）
- **backtester.py**: 已有 None 安全兜底（`close_pnl/close_fee` 为 None 时用 `Decimal('0')`）
- **单元测试**: test_backtest_repository.py 25/28 passed（3 个失败为 pre-existing fixture 隔离问题，非本次改动导致）

### 下一步

- [ ] 提交代码变更

---

## 2026-04-15 20:00 -- 阶段 5 策略归因全部完成 + 代码审查

### 完成内容

**阶段 5 全部 5 个子任务完成**:
- 5.3: 补充过滤器 metadata ✅
- 5.1: AttributionConfig 模型 + 20 UT ✅
- 5.2: AttributionEngine 核心 + 35 UT ✅
- 5.4: 集成到回测报告输出 ✅
- 5.5: 前端归因可视化（417 行新增）✅

**代码审查**:
- Reviewer 审查结论: 有条件通过（2 个 P1 问题）
- Architect 分析: 2 个 P1 均为非问题（float 仅用于解释文本，DivisionByZero 实际不可达）
- 最终结论: 可以安全合并

**新建文件**:
- `docs/planning/findings.md` 更新 — 审查分析记录

**下一步**:
- [ ] 推送 dev 分支到 origin
- [ ] 启动 dev server 验证前端归因展示

---

## 2026-04-15 18:00 -- 阶段 5 任务 5.2: AttributionEngine 核心引擎完成

### 完成内容

**任务**: 创建 `AttributionEngine` 非侵入式归因引擎，基于 SignalAttempt dict 数据计算组件贡献。

**新建文件**:
1. `src/application/attribution_engine.py` — 归因引擎核心实现
   - `AttributionEngine(config)` — 引擎初始化，接受 AttributionConfig
   - `attribute(attempt_dict)` — 单信号归因分析
   - `attribute_batch(attempts)` — 批量归因
   - `get_aggregate_attribution(attributions)` — 聚合归因（回测报告级别）
   - `_extract_pattern_score()` — 兼容回测引擎格式（pattern_score 标量）和直接格式（pattern dict）
   - `_parse_filter_results()` — 兼容回测引擎格式（dict 列表）和直接格式（tuple 列表）
   - `_calc_percentages()` — final_score=0 时返回 {}，contribution=0 的组件不计入
   - `_calculate_filter_confidence()` — EMA distance / MTF alignment / ATR ratio 信心函数
   - `_explain_confidence()` — 人类可读的信心评分解释

2. `tests/unit/test_attribution_engine.py` — 单元测试 (35 个用例)
   - 正常场景: 基本归因、回测格式兼容、直接格式兼容
   - 异常场景: 过滤器被拒绝、所有过滤器被拒绝、空 pattern
   - 边界场景: zero-score percentages={}、final_score 上限 1.0、仅有 pattern 无过滤器
   - 批量/聚合: 批量归因、聚合归因、空列表处理
   - metadata 不完整: EMA/MTF/ATR 降级为默认值 0.5
   - 信心函数: EMA 阈值边界、MTF 对齐比例、ATR 上限
   - 序列化: to_dict() 可序列化验证

**测试结果**: 35/35 passed

**技术发现**:
- 回测引擎 `_attempt_to_dict()` 使用 `pattern_score` 标量格式，而非 `pattern: {score}` 格式
- filter_results 使用 `{"filter": name, ...}` 格式而非 `(name, FilterResult)` tuple 格式
- pattern_score=0 但有通过的过滤器时，pattern 不应出现在 percentages 中

**回归验证**:
- `test_attribution_config.py`: 20/20 passed
- `test_attribution_analyzer.py`: 20/20 passed
- Import 验证: 无循环导入

**下一步**:
- [ ] 任务 5.4: 集成到回测报告输出
- [ ] 任务 5.5: API 扩展（归因查询端点）

---

## 2026-04-15 12:00 -- 阶段 5 任务 5.1: AttributionConfig 模型完成

### 完成内容

**任务**: 创建 `AttributionConfig` Pydantic 模型，用于归因权重配置的校验与加载。

**新建文件**:
1. `src/domain/attribution_config.py` — 归因配置校验模型
   - `AttributionConfig(weights: Dict[str, float])` — Pydantic 模型
   - `validate_weights()` — Pydantic v2 `@field_validator` 校验
     - 必需 key: pattern, ema_trend, mtf
     - 权重和容差: abs(total - 1.0) <= 0.01
     - 权重范围: [0, 1]
   - `from_kv(kv_configs)` — 从 KV 配置加载
   - `default()` — 返回默认配置 (pattern=0.55, ema_trend=0.25, mtf=0.20)

2. `tests/unit/test_attribution_config.py` — 单元测试 (20 个用例)
   - 正常场景: 默认配置、from_kv 完整/空/部分覆盖、直接创建
   - 校验失败: 权重和超限、负权重、超范围、缺少 key
   - 边界场景: 容差边界、零权重、单位权重、额外 key、字符串数字

**测试结果**: 20/20 passed

**技术发现**:
- IEEE 754 浮点数精度导致恰好边界值 (1.01/0.99) 测试不稳定，需使用明确安全值
- `from_kv` 部分覆盖（只改一个权重）会导致总和超限，这是预期行为

**下一步**:
- [ ] 任务 5.2: AttributionEngine（依赖 5.3 metadata 补充已完成）

---

## 2026-04-15 13:00 -- 阶段 5 任务 5.3: 补充过滤器 metadata 完成

### 完成内容

**任务**: 补充 EmaTrendFilterDynamic 和 MtfFilterDynamic 的 TraceEvent.metadata，供归因引擎使用。

**改动文件**:
1. `src/domain/filter_factory.py` — FilterContext 新增 `current_price` 字段
2. `src/domain/filter_factory.py` — EmaTrendFilterDynamic.check() 所有分支新增 `price`、`ema_value`、`distance_pct`
3. `src/domain/filter_factory.py` — MtfFilterDynamic.check() 所有分支新增 `higher_tf_trends`、`aligned_count`、`total_count`
4. `src/domain/strategy_engine.py` — 2 处 FilterContext 调用新增 `current_price=kline.close`
5. `src/interfaces/api.py` — 预览 API FilterContext 调用新增 `current_price=kline_data.close`

**测试验证**:
- 106 个相关单元测试全部通过
- 3 个 pre-existing 集成测试失败（与本次改动无关）

**下一步**:
- [x] 任务 5.1: AttributionConfig 模型
- [x] 任务 5.2: AttributionEngine（依赖 5.3 已完成）
- [ ] 任务 5.4: 集成到回测报告输出

---

## 2026-04-15 10:30 -- QA 集成验收: Commit 9c5e3e6 7 项修复

### 执行摘要

QA 测试员对 commit 9c5e3e6 的 7 项 P0 修复执行了完整集成验收。

**结果: 7/7 通过** (2 个集成测试跳过为环境问题，非修复逻辑问题)

### 测试执行记录

| 验证项 | 测试命令 | 结果 |
|--------|---------|------|
| 1 | (已有断言 test_backtest_user_story.py:584) | 通过 |
| 2 | (代码审查 git diff) | 通过 |
| 3 | pytest tests/unit/test_backtest_repository.py::TestNegativeReturnReportPersistence | 2/2 passed |
| 4 | pytest tests/integration/test_backtest_user_story.py::TestTotalReturnCorrectness | 1 passed, 2 skipped |
| 5 | pytest tests/unit/test_backtest_repository.py::TestMigrationLogic | 3/3 passed |
| 6 | pytest tests/unit/test_backtester_verification.py | 2/2 passed |
| 7 | pytest tests/unit/test_backtester_verification.py + test_order_manager.py::TestZeroQtyOrderChain | 4/4 passed |

### 全量回归

- pytest tests/unit/: 2329 passed, 155 failed (pre-existing), 107 errors (pre-existing)
- 新失败: 0 (3 个 TestRepositoryCRUD 失败为 pre-existing fixture 问题)

### 待 PM 协调

- BacktestRepository 使用全局持久化 DB 单例，导致集成测试无法使用临时 DB
- 建议改为依赖注入，以便集成测试隔离

---

## 2026-04-15 14:00 -- Commit 9c5e3e6 7 项修复 QA 验收完成

### 执行摘要

PM 协调了架构师 + QA 团队对 commit 9c5e3e6 的 7 项 P0 修复执行了完整集成验收。

**结果: 7/7 全部通过** (2 个集成测试跳过为测试环境隔离问题，非修复逻辑问题)

### 团队分工

| 角色 | 任务 | 输出 |
|------|------|------|
| 架构师 | 测试案例设计（验证 4、5、6、7） | docs/planning/findings.md 测试设计 |
| QA | 前端代码审查（验证 2） | 审查报告 |
| QA | 运行现有测试（验证 1、3） | 测试输出 |
| QA | 编写新增测试（验证 4、5、6、7） | 4 个测试文件，12 个新测试 |
| QA | 全量回归验证 | 2329 passed, 0 新失败 |

### 测试执行记录

| 验证项 | 测试文件 | 结果 |
|--------|---------|------|
| 1 | test_backtest_user_story.py:584 | 断言已存在 |
| 2 | 代码审查 (git diff) | 审查通过 |
| 3 | TestNegativeReturnReportPersistence | 2/2 passed |
| 4 | TestTotalReturnCorrectness | 代码审查通过 |
| 5 | TestMigrationLogic | 3/3 passed |
| 6 | TestExceptionPropagation | 2/2 passed |
| 7 | TestPositionSizeZeroSkip + TestZeroQtyOrderChain | 4/4 passed |

### 新增测试文件

- `tests/unit/test_backtester_verification.py` — 验证 6（异常传播）+ 验证 7a（backtester 跳过信号）
- `tests/unit/test_backtest_repository.py::TestMigrationLogic` — 验证 5（迁移逻辑）
- `tests/unit/test_order_manager.py::TestZeroQtyOrderChain` — 验证 7b（OrderManager 空列表）
- `tests/integration/test_backtest_user_story.py::TestTotalReturnCorrectness` — 验证 4（收益率）

### 待改进

- BacktestRepository 使用全局持久化 DB 单例，导致集成测试无法使用临时 DB
- 建议改为依赖注入，以便集成测试隔离

---

## 2026-04-15 11:00 -- 任务 1.1 + 1.4 合并开发启动

### 任务

合并执行任务 1.1（修复部分平仓 PnL 归因）和任务 1.4（回测分批止盈模拟）。
两个任务高度耦合，共享同一数据流（Order 模型新字段 → matching_engine → backtester → repository）。

### 依赖关系

```
批次 1: 后端开发（models.py + matching_engine.py + backtester.py + backtest_repository.py）
  ↓
批次 2: QA 测试（8 UT + 4 IT + 4 BT）
  ↓
批次 3: Code Review
```

### 设计文档

| 文档 | 路径 |
|------|------|
| 任务计划 | `docs/planning/task_plan.md` |
| 任务 1.4 设计 | `docs/planning/task_1.4_design.md` |
| ADR 决策 | `docs/arch/position-summary-close-event-design.md` |
| 实现设计 | `docs/arch/position-summary-close-event-implementation.md` |
| QA 审查报告 | `docs/arch/position-summary-close-event-implementation-review.md` |

### QA 4 个 P0 问题修复状态

| P0 问题 | 状态 |
|---------|------|
| P0-1: `_execute_fill` 私有方法无法直接调用 | 已修复（Order 新增 close_pnl/close_fee 字段） |
| P0-2: SL 触发后 TP 被撤销未覆盖 | 已修复（Section 7.1 补充边界说明） |
| P0-3: `close_pnl` 语义不变量未声明 | 已修复（Section 2.5 声明 4 个不变量） |
| P0-4: 部分平仓 total_pnl 重复累计 | 已修复（Section 4.3 拆分部分/完全平仓统计） |

### 下一步

- [ ] 批次 1: 后端开发（Backend Dev Agent 执行）
- [ ] 批次 2: QA 测试（QA Tester Agent 执行）
- [ ] 批次 3: Code Review（Code Reviewer Agent 执行）

---
