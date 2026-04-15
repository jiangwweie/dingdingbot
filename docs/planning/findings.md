# Findings Log

> Last updated: 2026-04-15 18:00

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
