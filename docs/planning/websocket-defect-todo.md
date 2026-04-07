# 待办事项 - WebSocket K 线处理与形态检测缺陷修复

> **创建日期**: 2026-04-07
> **优先级**: 🔴 P0（严重缺陷）
> **预计工时**: 3 小时

---

## 📋 待办事项列表

### [1] 🔴 P0: WebSocket K 线处理缺陷修复（预计 2h）

**问题描述**:
1. WebSocket 未正确处理交易所提供的 `is_closed` 字段
2. `_parse_ohlcv()` 方法构造 `KlineData` 时错误使用默认值 `is_closed=True`
3. 导致未收盘的 K 线可能触发信号

**修复范围**:
- `src/infrastructure/exchange_gateway.py:290-462`
- WebSocket 订阅逻辑
- `_parse_ohlcv()` 方法签名

**修复内容**:
- [ ] 修改 `_parse_ohlcv()` 增加 `is_closed` 参数
- [ ] WebSocket 订阅时正确获取交易所的 `is_closed` 字段
- [ ] 仅触发已收盘 K 线的回调

**验收标准**:
- ✅ WebSocket 仅处理已收盘 K 线
- ✅ 单元测试验证 `is_closed=False` 的 K 线被正确过滤

---

### [2] 🔴 P0: process_kline() 防御性检查（预计 0.5h）

**问题描述**:
- `signal_pipeline.py` 的 `process_kline()` 方法缺少 `is_closed` 检查
- 如果 WebSocket 层传递了未收盘的 K 线，会被直接处理

**修复范围**:
- `src/application/signal_pipeline.py:455`

**修复内容**:
- [ ] 在方法开头添加 `if not kline.is_closed: return` 检查
- [ ] 记录警告日志

**验收标准**:
- ✅ 收到未收盘 K 线时记录警告并返回
- ✅ 单元测试验证防御逻辑

---

### [3] 🔴 P0: Pinbar 最小波幅检查（预计 0.5h）

**问题描述**:
- Pinbar 检测缺少最小波幅检查
- 刚开盘的 K 线（波幅极小）可能被误判为 Pinbar

**修复范围**:
- `src/domain/strategy_engine.py:184-276`
- `src/domain/models.py` (PinbarParams 配置)

**修复内容**:
- [ ] 在 `PinbarParams` 中添加 `min_candle_range` 参数
- [ ] 在 `PinbarStrategy.detect()` 中检查最小波幅

**验收标准**:
- ✅ 波幅 < `min_candle_range` 的 K 线不检测形态
- ✅ 单元测试验证误判消除

---

### [4] ✅ P0: 回测引擎缺陷排查（已完成）

**问题描述**:
- 需要排查回测引擎是否存在相同的 K 线处理缺陷
- 检查历史数据加载逻辑是否正确设置 `is_closed`

**检查范围**:
- `src/application/backtester.py` - 主循环和 `_fetch_klines()` 方法
- `src/infrastructure/exchange_gateway.py:fetch_historical_ohlcv()`
- `src/infrastructure/historical_data_repository.py`

**检查结果**: ✅ **回测引擎不受影响**
- ✅ 历史数据必定已收盘，数据源正确
- ✅ `_parse_ohlcv()` 硬编码 `is_closed=True` 符合历史数据特性
- ✅ 不存在"未收盘 K 线触发信号"的风险

**审查报告**: `docs/reviews/backtester-kline-review.md`

**结论**: 无需修复，不添加到待办清单

---

## 📊 总工时预估

| 任务 | 预计工时 | 优先级 | 状态 |
|------|---------|--------|------|
| [1] WebSocket 修复 | 2h | P0 | 待实施 |
| [2] 防御性检查 | 0.5h | P0 | 待实施 |
| [3] Pinbar 波幅检查 | 0.5h | P0 | 待实施 |
| [4] 回测引擎排查 | 1h | P0 | ✅ 已完成 |
| **总计** | **3h（剩余）** | - | - |

---

## 🔗 相关文档

- 架构审查报告: `docs/reviews/websocket-kline-defect-review.md`
- 用户问题描述: 历史版本发现的 3 个问题

---

## 📝 备注

**影响评估**:
- 问题 1+2+3 叠加可能导致：
  - 未收盘 K 线触发信号
  - 刚开盘 K 线被误判为 Pinbar
  - 系统信号质量严重下降

**修复顺序**:
1. 先修复 WebSocket `is_closed` 处理（根源问题）
2. 添加 `process_kline()` 防御检查（防御层）
3. 添加 Pinbar 最小波幅检查（形态质量）
4. 排查回测引擎（数据一致性）

---

*创建人: Architect*
*创建日期: 2026-04-07*