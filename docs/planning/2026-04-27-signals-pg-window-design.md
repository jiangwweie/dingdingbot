# 2026-04-27 Signals PG Window 设计

## 目标

在不扩大为整棵信号域重构的前提下，将 **live `signals` + `signal_take_profits`** 纳入 PG 主线，
并保持：

- `signal_attempts` 继续留在 SQLite
- `config_snapshots` 继续留在 SQLite
- `backtest signal helpers` 继续留在 SQLite

## 方案 A（采用）：Hybrid Runtime Signal Repository

### 设计

- 新增 `PgSignalRepository`
  - 管理 `signals`
  - 管理 `signal_take_profits`
- 新增 `HybridSignalRepository`
  - live signal 相关方法 -> PG
  - attempts / config snapshots / backtest helpers -> SQLite
- runtime `SignalPipeline` / `PerformanceTracker` / runtime readonly 面统一接入 hybrid repo

### 优点

- 最小改动切主链
- 不需要现在重写 `signal_attempts`
- 不需要把 config snapshot 从 `SignalRepository` 中拆出来
- 不会把本窗从 execution/signal mainline 收口扩成 observability 全迁移

### 缺点

- 过渡期内仍是双仓储 facade
- `/api/signals` 的默认语义会更偏 live signal，而 backtest 继续走显式 backtest 路由

## 方案 B（不采用）：一次性拆分整棵 SignalRepository

### 设计

- 同时拆出：
  - `PgSignalRepository`
  - `PgSignalAttemptRepository`
  - `PgConfigSnapshotRepository`
- runtime / research / readonly API 全面改造

### 不采用原因

- 范围过大
- 会把当前“PG 主线闭环”窗口扩成“signal + observability + config repo 拆分”窗口
- 与当前用户目标“尽快把 PG 主线闭环”不匹配

## 当前采用边界

### 这窗会做

- `signals` -> PG
- `signal_take_profits` -> PG
- `SignalPipeline` dedup / covering / pending / opposing signal 主路径切 PG
- `runtime signals` readonly 切 PG

### 这窗不做

- `signal_attempts` 迁 PG
- `config_snapshots` 拆 repo
- `backtest signal` 全迁 PG
- `signals` 与 `attempts` 的统一只读聚合重构

