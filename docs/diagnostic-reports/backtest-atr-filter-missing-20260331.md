# 诊断报告：回测引擎 ATR 过滤器缺失

**报告编号**: DA-20260331-001
**优先级**: 🟠 P1 - 尽快修复（3 天内）
**状态**: ✅ **已修复** (commit: c469943)

---

## 问题描述

| 字段 | 内容 |
|------|------|
| 用户报告 | 核实回测信号是否符合业务逻辑 |
| 影响范围 | 所有使用 legacy 模式的回测信号（`IsolatedStrategyRunner`） |
| 出现频率 | 必现 - 所有回测信号均未经过 ATR 过滤器 |
| 首次出现时间 | ATR 过滤器集成到实盘后，回测引擎未同步更新 |
| 相关组件 | `src/application/backtester.py::IsolatedStrategyRunner` |

---

## 排查过程

### Step 1: 初步假设

| 假设 | 可能性 | 验证方法 | 验证结果 |
|------|--------|----------|----------|
| ATR 过滤器配置错误 | 中 | 检查服务器配置文件 | ❌ 配置正确 |
| ATR 过滤器未执行 | 高 | 检查回测引擎代码 | ✅ 确认 `IsolatedStrategyRunner` 未集成 ATR 过滤器 |
| 信号标签生成逻辑缺陷 | 低 | 检查 `_generate_tags_from_filter_results` | ✅ 逻辑正确，但无 ATR 结果 |

### Step 2: 根因定位

**问题代码位置**: `src/application/backtester.py:70-82`（已删除）

```python
# 修复前：IsolatedStrategyRunner 硬编码创建过滤器
self._ema_filter = EmaTrendFilter(...)
self._mtf_filter = MtfFilter(...)
# ❌ 没有 ATR 过滤器！
```

**根本原因**:
`IsolatedStrategyRunner` 是 legacy 模式的回测专用类，设计时未集成 ATR 过滤器。

---

## 数据验证

### 回测信号统计（修复前）

```
总信号数：31
- 问题信号数：7 (22.6%)
- 问题表现：止损距离过近（<0.3%）
```

### 问题信号列表

| ID | 品种 | 方向 | 止损距离 | 问题 |
|----|------|------|----------|------|
| 270 | ETH/USDT:USDT | SHORT | 0.170% | ATR 过滤失效 |
| 269 | ETH/USDT:USDT | SHORT | 0.161% | ATR 过滤失效 |
| 264 | ETH/USDT:USDT | LONG  | 0.234% | ATR 过滤失效 |
| 260 | ETH/USDT:USDT | SHORT | 0.134% | ATR 过滤失效 |
| 258 | ETH/USDT:USDT | SHORT | 0.268% | ATR 过滤失效 |
| 254 | ETH/USDT:USDT | LONG  | 0.233% | ATR 过滤失效 |
| 253 | ETH/USDT:USDT | LONG  | 0.262% | ATR 过滤失效 |

---

## 修复方案

### 方案 C（已实施）：统一使用 DynamicStrategyRunner

**修改内容**:
- 删除 `IsolatedStrategyRunner` 类
- 新增 `_convert_legacy_to_strategy_definition()` 转换器
- ATR 过滤器默认启用（0.5% 阈值）

**优点**:
- 回测与实盘过滤器链完全一致
- 减少 legacy 代码维护成本
- 支持未来扩展新过滤器

**工作量**: 4 小时
**测试**: 48 项测试全部通过

---

## 验证方法

```bash
# 运行单元测试
pytest tests/unit/test_backtester_atr.py -v
# 10 passed

pytest tests/unit/test_filter_factory.py -v
# 38 passed
```

---

## 状态

✅ **已修复并部署**

- 提交：c469943
- 实施报告：`docs/ops/solution-c-implementation-report.md`
- 部署状态：待服务器部署

---

**诊断分析师**: Diagnostic Analyst
**实施人员**: Backend Dev + Team Coordinator
**修复完成时间**: 2026-03-31
