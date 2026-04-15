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
