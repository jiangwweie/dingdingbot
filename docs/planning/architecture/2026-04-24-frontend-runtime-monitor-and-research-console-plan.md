# Frontend Runtime Monitor + Research Console Plan

> Date: 2026-04-24
> Status: Planning
> Current decision: **方案 A（分域控制台）**
> Scope: Sim-1 观察面优先，研究分析面纳入统一信息架构；当前不做配置编辑与热改

---

## 1. 背景

当前后端主线已经具备：

- `sim1_eth_runtime` 冻结 runtime config
- candidate-only Optuna / Backtest / replay 闭环
- candidate review rubric（Strict v1）
- execution / recovery / reconciliation / breaker 运行链路

但在进入 Sim-1 自然模拟盘观察后，新的主要问题不再是“链路能否工作”，而是：

1. 人类无法直观看到系统当前运行状态。
2. 研究 candidate 已经可产出，但缺少统一观察入口。
3. Runtime 观察与 Research 分析长期会进入同一控制台谱系，如果现在不一起设计，后面容易长成两个平行系统。

因此，这次前端重构规划的目标不是“重做工作台”，而是先设计并分阶段建设一个统一控制台：

- **Runtime Monitor**：服务 Sim-1 / 模拟盘 / 实盘观察
- **Research Console**：服务 Backtest / Optuna / Candidate review

实施上，当前只优先 Runtime Monitor 的 MVP。

---

## 2. 本次已确认决策

### 2.1 方案选择

采用 **方案 A：分域控制台**。

原因：

1. 能清楚分离“运行观察”与“研究分析”两种心智。
2. 不会把 Sim-1 值班观察和 Backtest Studio 混成一个大杂烩首页。
3. 后续 Backtest Studio 可自然并入 `Research` 域，不会推倒重来。

### 2.2 四个关键产品约束

已确认：

1. 第一版以前端 **只读为主**
2. Candidate review 第一版 **只展示，不做人工写回**
3. Runtime 页面第一版使用 **手动刷新**，不做 SSE / websocket UI
4. Backtest Studio 作为 **二期并入**，这次先纳入整体信息架构，不进第一版实现范围

---

## 3. 信息架构（方案 A）

统一控制台建议命名：

- `Trading Console`
- 或 `Sim Console`

### 一级导航

- `Runtime`
- `Research`

### 3.1 Runtime 域

用于观察系统现在正在发生什么。

- `Overview`
- `Signals`
- `Execution`
- `Health`

### 3.2 Research 域

用于观察回测、candidate 和 review 结果。

- `Candidates`
- `Candidate Detail`
- `Replay`
- `Backtests`（二期）
- `Compare`（二期）

---

## 4. 页面树

### 4.1 第一版（P0/P1）

```text
Trading Console
├── Runtime
│   ├── Overview
│   ├── Signals
│   ├── Execution
│   └── Health
└── Research
    ├── Candidates
    ├── Candidate Detail
    └── Replay (read-only)
```

### 4.2 二期（P2）

```text
Trading Console
├── Runtime
│   ├── Overview
│   ├── Signals
│   ├── Execution
│   └── Health
└── Research
    ├── Candidates
    ├── Candidate Detail
    ├── Replay
    ├── Backtests
    └── Compare
```

---

## 5. 页面定义

### 5.1 Runtime / Overview

目标：一眼看清“系统现在是否可运行”。

必须展示：

- 当前 runtime profile / version / hash
- runtime frozen 标记
- symbol / timeframe / mode
- exchange / pg / webhook 健康
- breaker count
- 最近一次 reconciliation 摘要
- 当前 backend 切换状态（execution intent / order / position）

### 5.2 Runtime / Signals

目标：看最近信号、attempt 和过滤拒绝原因。

必须展示：

- 最近 N 条 attempts
- 最近 N 条 fired signals
- attempt final_result 分布
- filter reject reason 摘要
- strategy / direction / timeframe / timestamp

### 5.3 Runtime / Execution

目标：看执行链当前是否顺畅。

必须展示：

- recent execution intents
- recent orders
- recent recovery tasks
- breaker rebuild / reconciliation 最近摘要

### 5.4 Runtime / Health

目标：聚焦异常与 warning，而不是业务结果。

必须展示：

- PG / Exchange / Notification 状态
- 最近 warning / error 摘要
- 启动阶段关键 marker 状态

### 5.5 Research / Candidates

目标：看有哪些 candidate 值得进入人工评审。

必须展示：

- candidate 名称
- generated_at
- source_profile / git commit
- objective
- review status（展示，不可编辑）
- Strict v1 通过情况
- warnings 列表

### 5.6 Research / Candidate Detail

目标：看单个 candidate 是否值得继续跟进。

必须展示：

- best_trial 指标
- top_trials 摘要
- fixed_params / runtime_overrides
- resolved_request
- constraints
- review rubric 对照结果

### 5.7 Research / Replay

目标：让人读懂 candidate 结构，而不是直接做重回测控制。

第一版只读展示：

- reproduce_cmd
- candidate metadata
- resolved_request
- runtime_overrides

---

## 6. 最小接口列表（第一版）

接口按前端视图模型设计，不按数据库表设计。

### P0

#### 6.1 `GET /api/runtime/overview`

返回：

- profile / version / hash
- runtime frozen
- market summary
- backend summary
- exchange / pg / webhook health
- breaker count
- reconciliation summary

#### 6.2 `GET /api/runtime/signals`

返回最近信号列表：

- signal id
- symbol / timeframe / direction
- strategy_name
- score
- created_at / status

#### 6.3 `GET /api/runtime/attempts`

返回最近 attempts：

- symbol / timeframe
- strategy_name
- final_result
- filter_results summary
- reject reason
- timestamp

#### 6.4 `GET /api/runtime/execution/intents`

返回 recent execution intents：

- intent id
- signal id
- symbol
- status
- created_at / updated_at

#### 6.5 `GET /api/runtime/execution/orders`

返回 recent orders：

- order id
- role
- symbol
- status
- quantity / price
- updated_at

#### 6.6 `GET /api/runtime/health`

返回运行健康摘要：

- pg status
- exchange status
- notification status
- recent warning/error summary
- breaker summary

### P1

#### 6.7 `GET /api/research/candidates`

返回 candidate 列表：

- candidate_name
- generated_at
- source_profile
- objective
- strict review status
- warnings

#### 6.8 `GET /api/research/candidates/{candidate_name}`

返回 candidate 详情：

- best_trial
- top_trials
- fixed_params
- runtime_overrides
- constraints
- resolved_request
- rubric evaluation

#### 6.9 `GET /api/research/replay/{candidate_name}`

返回 replay 视图需要的数据：

- reproduce_cmd
- metadata
- resolved_request
- runtime_overrides

---

## 7. 后续接口（第二阶段）

这些接口设计上先留位，不进入第一版开发。

### 7.1 Research / Backtests

- `GET /api/research/backtests`
- `GET /api/research/backtests/{report_id}`

### 7.2 Research / Compare

- `POST /api/research/compare/candidates`
- `POST /api/research/compare/backtests`

### 7.3 Review Action（后置）

如果未来允许人工标记 review 状态，再加：

- `POST /api/research/candidates/{candidate_name}/review`

当前明确不做。

---

## 8. 优先级排序

### P0（先做）

1. Runtime / Overview
2. Runtime / Signals
3. Runtime / Execution
4. Runtime / Health
5. `GET /api/runtime/overview`
6. `GET /api/runtime/signals`
7. `GET /api/runtime/attempts`
8. `GET /api/runtime/execution/intents`
9. `GET /api/runtime/execution/orders`
10. `GET /api/runtime/health`

### P1（当前主线稳定后接）

1. Research / Candidates
2. Research / Candidate Detail
3. Research / Replay
4. `GET /api/research/candidates`
5. `GET /api/research/candidates/{candidate_name}`
6. `GET /api/research/replay/{candidate_name}`

### P2（二期）

1. Research / Backtests
2. Research / Compare
3. 复杂分析图表
4. 人工 review 写回
5. 更丰富的 overfitting checks 展示

---

## 9. 与 Backtest Studio 的关系

现有文档：

- `docs/planning/architecture/2026-04-22-backtest-studio-prd.md`

本次决策：

1. 设计上，Backtest Studio 继续视为 `Research` 域的一部分。
2. 实施上，Backtest Studio 仍然是二期，不进入当前 Runtime Monitor MVP。
3. 当前前端重构不否定 `apps/backtest-studio` 的独立落地可能，但统一信息架构必须优先成立。

换句话说：

- **设计上统一**
- **实现上分期**

---

## 10. 当前明确不做

1. 不做配置编辑器
2. 不做 runtime 热改
3. 不做策略工作台 2.0
4. 不做 candidate 一键 promote
5. 不做 websocket 前端实时订阅
6. 不做大型多图表研究平台

---

## 11. 建议的下一步

### Step 1

先做 Runtime 域 P0 的接口契约表与前端页面草图。

### Step 2

用只读、手动刷新模式做 Runtime Monitor MVP。

### Step 3

待 Sim-1 观察进入稳定节奏后，再接 Research 域 P1。

### Step 4

最后再决定 Backtest Studio 是否以独立子项目形式落地。
