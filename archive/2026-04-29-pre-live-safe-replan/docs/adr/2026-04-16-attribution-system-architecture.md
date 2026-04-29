# ADR: 归因系统全局架构设计

> **日期**: 2026-04-16
> **状态**: 用户已确认，待实施

---

## 1. 背景

系统中存在三套归因相关能力，各自独立：

| 系统 | 引入时间 | 用途 | 当前状态 |
|------|---------|------|---------|
| **AttributionAnalyzer**（旧版 BT-4） | 4月6日 | 事后群体统计（四维度分析） | 断裂 — API 500，数据源不存在 |
| **AttributionEngine**（新版 阶段5） | 4月15日 | 事前单信号组件分解 | 内存正常，但**未持久化**到数据库 |
| **PositionCloseEvent**（PnL 归因 1.1+1.4） | 4月15日 | 每次出场独立盈亏记录 | 完整 — 数据流+持久化+前端 |

### 隐藏的第三个断裂

`PMSBacktestReport.signal_attributions` 在回测 API 响应中有数据（内存计算），但 `save_report()` **不持久化**到数据库。用户刷新页面从数据库重新加载时，归因数据丢失。

---

## 2. 三套系统是否合并？

**决策：不合并，统一入口。**

理由：
1. **回答不同问题**：事前信心 vs 事后结果 vs 群体统计 — 互补而非重叠
2. **语义边界清晰**：合并会模糊"为什么发出信号"和"实际结果如何"的区别
3. **违反单一职责**：强行合并导致模型膨胀

---

## 3. 统一架构设计

### 3.1 数据三层模型

```
Layer 1: PnL Events（事后结果）
  → position_close_events 表（已存在，已持久化）

Layer 2: Signal Attribution（事前信心）
  → 新增 backtest_reports 表列：signal_attributions TEXT (JSON)

Layer 3: Analysis Dimensions（群体统计）
  → 新增 backtest_reports 表列：analysis_dimensions TEXT (JSON)
```

### 3.2 数据流

```
回测运行时（内存中）:
  all_attempts → AttributionEngine → signal_attributions + aggregate
               → AttributionAnalyzer → analysis_dimensions (四维度)
               → 组装 PMSBacktestReport

持久化时:
  save_report() → backtest_reports 表（新增 2 列 JSON）
                → position_close_events 表（不变）

查询时:
  get_report() → 反序列化 JSON → 完整 PMSBacktestReport
  GET /api/backtest/{id}/attribution → 返回三层统一结构
```

### 3.3 统一 API 响应结构

```json
GET /api/backtest/{report_id}/attribution
{
  "signal_attribution": { /* Layer 2: 单信号组件分解 + 聚合 */ },
  "analysis_dimensions": { /* Layer 3: 四维度群体统计 */ },
  "pnl_events": [...] /* Layer 1: 出场盈亏明细 */
}
```

### 3.4 废弃的 API

- `POST /api/backtest/{report_id}/attribution` → 废弃（改为 GET，从数据库直接读取）
- `POST /api/backtest/attribution/preview` → 保留（用于未保存报告的即时预览）

---

## 4. 设计决策

### 决策 1: 不持久化 attempts 原始数据

attempts 是中间数据，归因计算后不再需要。持久化 attempts 需要独立表和 FK 关系，增加 10x 复杂度。归因结果是有损压缩，用户需要的信息已完整保留。

### 决策 2: AttributionAnalyzer 在回测结束时调用

当前断裂根因是 API 无法获取 attempts（数据库中不存在）。回测结束时 attempts 在内存中，是计算四维度的唯一时机。计算结果持久化为 JSON，API 直接读取。

### 决策 3: signal_attributions 存 JSON 而非独立表

单次回测 < 100 个信号 × 200 字节 = < 20KB。JSON 查询简单，不需要行级查询。未来需要信号级筛选时再拆独立表。

---

## 5. 关联影响

### 直接影响（4 个文件，~80 行）

| 文件 | 改动 | 风险 |
|------|------|------|
| `src/domain/models.py` | PMSBacktestReport 新增 analysis_dimensions 字段 | 低 |
| `src/infrastructure/backtest_repository.py` | save_report/get_report 序列化/反序列化新增 2 列 | 低 |
| `src/application/backtester.py` | 回测结束调用 AttributionAnalyzer | 低 |
| `src/interfaces/api.py` | attribution API 从 POST 改为 GET | 中（前端需适配） |

### 不受影响

- attribution_analyzer.py / attribution_engine.py — 核心逻辑不变
- position_close_events 表 — 不变
- signals / signal_attempts 表 — 不变
- 前端已实现的归因可视化 — 数据源不变

---

## 6. 分阶段实施路径

| Phase | 内容 | 优先级 | 状态 |
|-------|------|--------|------|
| Phase 1 | 修复持久化断裂（新增 2 列 JSON + save_report 序列化 + backtester 调用 Analyzer） | P0 | 待启动 |
| Phase 2 | 统一 API 入口（POST 改 GET，返回三层结构） | P1 | 待启动 |
| Phase 3 | 前端适配 + 四维度面板可视化 | P2 | 待启动 |
