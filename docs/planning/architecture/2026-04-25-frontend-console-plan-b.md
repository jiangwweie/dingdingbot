# Frontend Console Plan B

> Date: 2026-04-25
> Status: Planning
> Current decision: **方案 B（完整控制台扩展）**
> Scope: 基于 `gemimi-web-front` 现有骨架继续扩展，优先补齐量化使用者真正会频繁打开的页面
> Security default: **仅本地 / 内网访问**
> Data mode: **mock-first**

---

## 1. 当前骨架评估

`gemimi-web-front` 现有骨架已经具备继续扩展的基础：

1. 已有统一路由和布局。
2. 已有 `Runtime / Research / Config` 三域的信息架构。
3. 已有 mock API 层和类型定义，便于继续扩页。
4. 已有手动刷新语义，适合 Sim-1 观察模式。
5. 已有基础的 read-only 页面骨架，不需要推倒重来。

结论：

- 不是“从 0 到 1”重做
- 是“从骨架到完整控制台”继续长出来
- 适合走完整扩展方案 B

---

## 2. 方案 B 的目标

把当前骨架扩展成一个真正可用的量化观察与研究控制台，覆盖：

1. Sim-1 / 模拟盘 / 实盘观察
2. 账户与仓位风险查看
3. 事件与告警聚合查看
4. candidate 与 backtest 的只读研究工作流
5. frozen runtime 的配置快照预览

核心原则：

- read-only
- manual refresh
- mock-first
- 不做热改
- 不做配置编辑
- 不做写回动作

---

## 3. 页面树

### 3.1 Runtime 域

```text
Runtime
├── Overview
├── Portfolio
├── Positions
├── Signals
├── Execution
├── Events
├── Health
└── Alerts (后续可选)
```

### 3.2 Research 域

```text
Research
├── Candidates
├── Candidate Detail
├── Candidate Review
├── Replay
├── Backtests
├── Compare
├── Runs (后续可选)
└── Artifact Explorer (后续可选)
```

### 3.3 Config 域

```text
Config
└── Snapshot
```

---

## 4. 页面职责

### 4.1 Runtime / Overview

用于一眼判断系统是否“还活着”。

必须展示：

- runtime profile / version / hash
- frozen 标志
- symbol / timeframe / mode
- exchange / pg / webhook 健康
- breaker count
- reconciliation 摘要
- server_time
- last_runtime_update_at
- last_heartbeat_at
- freshness_status

### 4.2 Runtime / Portfolio

用于看账户整体风险。

必须展示：

- total equity
- available balance
- unrealized PnL
- total exposure
- daily loss used / limit
- leverage usage
- margin summary

### 4.3 Runtime / Positions

用于看持仓细节。

必须展示：

- symbol
- direction
- entry price
- mark price
- unrealized PnL
- leverage
- margin usage
- TP / SL 状态
- lifecycle / protection 状态

### 4.4 Runtime / Signals

用于看信号、attempt、过滤结果。

必须展示：

- recent attempts
- recent fired signals
- filter reject reason
- strategy / direction / timeframe / timestamp

### 4.5 Runtime / Execution

用于看执行链当前状态。

必须展示：

- execution intents
- recent orders
- recovery tasks
- reconciliation 摘要

### 4.6 Runtime / Events

用于看系统事件时间线。

必须展示：

- startup events
- reconciliation events
- breaker events
- recovery events
- warnings / errors
- signal decision summaries
- execution lifecycle summaries

### 4.7 Runtime / Health

用于看健康与异常摘要。

必须展示：

- PG / Exchange / Notification 状态
- recent warning / error summary
- startup markers
- breaker summary
- recovery summary

### 4.8 Research / Candidates

用于看 candidate 列表，进入人工评审前的入口。

必须展示：

- candidate name
- generated_at
- source_profile / git commit
- objective
- review status
- Strict v1 结果
- warnings

### 4.9 Research / Candidate Detail

用于看单个 candidate 的结构化详情。

必须展示：

- best_trial
- top_trials
- fixed_params
- runtime_overrides
- constraints
- resolved_request
- rubric evaluation

### 4.10 Research / Candidate Review

用于做评审判断，不是写回。

必须展示：

- Strict v1 checklist
- warning-only checks
- best trial vs top trials
- boundary warning
- review summary

### 4.11 Research / Replay

第一版只作为 Replay Context / Reproduce Context。

必须展示：

- reproduce_cmd
- metadata
- resolved_request
- runtime_overrides

### 4.12 Research / Backtests

用于看回测记录和结果摘要。

必须展示：

- report id
- candidate ref
- time range
- key metrics
- status

### 4.13 Research / Compare

用于做 candidate / backtest 的横向对比。

必须展示：

- metric table
- baseline vs candidate
- difference
- summary ranking

### 4.14 Config / Snapshot

用于查看 frozen runtime 当前快照。

必须展示：

- runtime profile identity
- market snapshot
- strategy snapshot
- risk snapshot
- execution snapshot
- backend summary
- source-of-truth hints
- frozen indicators

---

## 5. 模块化接口规划

### 5.1 Runtime APIs

- `GET /api/runtime/overview`
- `GET /api/runtime/portfolio`
- `GET /api/runtime/positions`
- `GET /api/runtime/signals`
- `GET /api/runtime/attempts`
- `GET /api/runtime/execution/intents`
- `GET /api/runtime/execution/orders`
- `GET /api/runtime/events`
- `GET /api/runtime/health`

### 5.2 Research APIs

- `GET /api/research/candidates`
- `GET /api/research/candidates/{candidate_name}`
- `GET /api/research/candidates/{candidate_name}/review-summary`
- `GET /api/research/replay/{candidate_name}`
- `GET /api/research/backtests`
- `GET /api/research/backtests/{report_id}`
- `GET /api/research/compare/candidates`
- `GET /api/research/compare/backtests`

### 5.3 Config APIs

- `GET /api/config/snapshot`

---

## 6. 实施步骤

### Phase 1 - 骨架收口

1. 审核 `gemimi-web-front` 现有结构。
2. 保留可用 layout / routing / mock 层。
3. 统一视觉风格、状态样式、卡片与表格组件。
4. 清理明显的 toy-like mock 数据。

### Phase 2 - Runtime 补全

1. 完成 `Portfolio`
2. 完成 `Positions`
3. 完成 `Events`
4. 加强 `Overview`
5. 强化 `Health`

### Phase 3 - Research 补全

1. 完成 `Candidate Review`
2. 完成 `Backtests`
3. 完成 `Compare`
4. 做厚 `Candidate Detail`
5. 让 `Replay` 语义明确为 context / reproduce

### Phase 4 - Config Snapshot

1. 实现只读快照页
2. 明确 frozen runtime 与 source-of-truth
3. 确保 UI 不出现编辑入口

### Phase 5 - 接口替换准备

1. mock service 接口命名稳定化
2. 前端类型与 mock payload 对齐
3. 为后续真实 API 替换留好边界

---

## 7. 页面优先级

### P0

1. `Runtime / Overview`
2. `Runtime / Portfolio`
3. `Runtime / Positions`
4. `Runtime / Events`
5. `Runtime / Health`

### P1

1. `Research / Candidates`
2. `Research / Candidate Detail`
3. `Research / Candidate Review`
4. `Research / Replay`

### P2

1. `Research / Backtests`
2. `Research / Compare`
3. `Config / Snapshot`

### P3

1. `Runtime / Alerts`
2. `Research / Runs`
3. `Research / Artifact Explorer`

---

## 8. 设计边界

1. 第一版全部只读。
2. 第一版手动刷新。
3. 第一版 mock-first。
4. 不做 websocket。
5. 不做配置编辑。
6. 不做 runtime 热改。
7. 不做 review 写回。
8. 不默认暴露公网访问。

---

## 9. 验收标准

前端第一阶段通过的标准：

1. Runtime 观察信息完整。
2. Research candidate 评审信息完整。
3. Replay 语义清楚。
4. Config snapshot 明确只读。
5. 页面层次和导航清晰。
6. mock 数据足够真实，不像演示玩具。
7. 所有页面具备 loading / empty / error 状态。
8. 后续可以平滑替换真实 API。

---

## 10. 建议结论

方案 B 适合继续推进，因为当前骨架已经具备足够清晰的起点。

下一步不是重写，而是：

1. 补齐高价值页面
2. 收敛 mock API 契约
3. 让控制台先成为“真正可用的观察工具”

