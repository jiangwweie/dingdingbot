# 2026-04-27 Research Control Plane v1 实施规划

> 状态：设计封板中
> 目标：在当前“前端只读 + runtime 主线已稳定 + research 仍偏脚本/离线”的状态下，建设一个**真正可用**的研究台，让系统可以从前端发起研究任务、查看结果、沉淀 candidate，同时保持 research/runtime 边界清晰。

---

## 1. 结论先行

当前最合理的方向不是“继续把 research 全量做成 PG 化平台”，而是：

> **按 Research Control Plane 的架构做，按 Backtest Workbench 的范围先落地。**

也就是：

1. 架构上，把 research、runtime、config 三条链彻底分开
2. 第一阶段功能上，只先做“能发起单次回测、能看结果、能保存结果、能标记 candidate”
3. 不在 v1 中开放任何会直接改动 runtime 的入口

### 1.1 本轮决策封板

本轮开工前已关闭以下关键决策：

| 决策 | 结论 | 原因 |
| --- | --- | --- |
| 产品形态 | Research Control Plane v1 | 避免把 research 做成脚本参数搬运页 |
| v1 功能范围 | 单次 backtest + runs + result + candidate | 先形成可用闭环，不做大平台 |
| 入口 API | 新增 `/api/research/jobs/*` | 与旧 `/api/backtest/*` 工具型端点解耦 |
| 任务执行 | 本机 runner，核心骨架由 Codex 实施 | 单机部署足够，避免 Celery/RabbitMQ 过度设计 |
| 元数据存储 | 独立 research SQLite | 不污染 execution PG truth，也避免 v1 过度迁库 |
| Artifact | 文件系统 `reports/research_runs/{job_id}` | 便于保存日志、报告、图表和 spec 快照 |
| Candidate | 独立研究候选，不可直接 promote runtime | 维持人工审查与 runtime freeze 边界 |
| Claude 分工 | 只做测试/fixture/文档盘点等杂活 | 核心代码骨架与关键边界由 Codex 亲自实施 |

详细决策记录见：

- `docs/planning/architecture/2026-04-27-research-control-plane-v1-decision-record.md`

---

## 2. 当前前提

### 已稳定的部分

1. execution PG 主线已闭环
   - orders
   - execution_intents
   - positions projection
   - execution_recovery_tasks
2. live signals 主线已切到 PG
3. runtime 真源已明确
   - `runtime_profiles`
   - `RuntimeConfigResolver`
   - 启动期冻结后的 `ResolvedRuntimeConfig`
4. Sim-1 已部署进入自然模拟盘观察

### 当前真正的缺口

1. 没有产品化的研究任务入口
2. 研究结果没有统一的对象模型和工作流
3. candidate 仍偏文件/脚本产物，不够像正式控制面
4. research 与 runtime 虽已分离，但还没有形成可操作的“研究控制台”

### Claude 回测链路分析校准

Claude 的回测链路报告中有两类结论需要区分：

1. **有效结论**
   - `/api/research/backtests` 查询链必须能容忍历史脏数据
   - 同步阻塞式回测不适合作为研究台主入口
   - 研究任务需要 job/status/result/candidate 工作流
2. **已过期或不作为本轮前提的结论**
   - 当前代码并不存在 `/api/backtest/run` 这个主入口
   - `BacktestRequest` 已支持 `strategies / risk_overrides / order_strategy / fee_rate / slippage_rate`
   - 当前研究台不以“先改现有 `/api/backtest/*`”为主线，而是新建 research control plane 入口

---

## 3. 架构目标

Research Control Plane v1 的目标不是做成完整量化平台，而是先提供一条**清晰、可控、可复现**的研究通道：

1. **发起研究任务**
2. **查看运行状态**
3. **查看和保存研究结果**
4. **把研究结果标记为 candidate**
5. **明确 candidate != runtime**

---

## 4. 核心边界

### 4.1 Runtime truth 边界

research 台不得直接修改：

1. `runtime_profiles`
2. `ResolvedRuntimeConfig`
3. execution runtime 的 live state
4. execution 主线 PG 真源

### 4.2 Research 边界

research 台只允许：

1. 发起 backtest / compare / scan 任务
2. 保存 research runs
3. 生成 candidate
4. 记录 review / notes / recommendation

### 4.3 Config 边界

research 输入必须是：

1. `ResearchSpec`
2. 明确的参数覆盖（overrides）
3. 可追溯的 baseline / source profile 引用

不允许：

1. 隐式读取当前 live runtime 作为默认真源
2. 直接修改 `config_profiles` 来驱动研究结果
3. 研究结果反向覆盖 runtime freeze

---

## 5. 推荐方案

### 方案 A：Research Control Plane（目标架构）

定位：

1. 前端是研究任务控制面
2. 后端有独立 research job / result / candidate 对象模型
3. research 与 runtime 显式隔离

优点：

1. 边界最清楚
2. 适合长期扩展 replay / optuna / compare / promote
3. 不会把 runtime/config/research 再搅回去

缺点：

1. 初始设计和对象建模工作量更大

### 方案 B：Backtest Workbench（最小范围）

定位：

1. 前端先只是一个回测工作台
2. 重点解决“我能从前端发起研究任务”
3. 结果以最小闭环形式保存和回看

优点：

1. 上线快
2. 直接解决当前最痛点

缺点：

1. 如果没有边界约束，很容易又变成“脚本参数搬进前端”

### 采用策略

> **A 的架构 + B 的范围**

---

## 6. v1 范围（必须做）

### 页面 / 模块

1. `Research Home`
2. `New Backtest`
3. `Runs`
4. `Run Detail`
5. `Candidates`
6. `Candidate Detail`

### 功能能力

1. 发起单次回测任务
2. 查看任务状态（PENDING / RUNNING / SUCCEEDED / FAILED）
3. 查看回测结果摘要与详情
4. 保存研究结果历史
5. 标记 candidate
6. 为 candidate 写 notes / review / recommendation

### 第一版验收标准

1. 前端只调用 research 域 API 发起任务
2. 创建 job 后立即返回 `job_id`，不等待回测完成
3. job 失败时有明确 `error_code / error_message`
4. 每个 run 都保存 `spec_snapshot`
5. 每个 candidate 都能追溯到 `run_result_id`
6. 任何 research API 都不能写 `runtime_profiles / orders / execution_intents / positions / execution_recovery_tasks`

---

## 7. v1 明确不做

1. 不做 runtime profile 编辑
2. 不做“一键 promote 到 live/runtime”
3. 不做通用配置编辑器
4. 不做大规模 Optuna 前端化
5. 不做 replay 工作流全量 UI
6. 不把 research 台做成“第二套配置后台”
7. 不迁 `signal_attempts`
8. 不把 backtest/research 报表强行迁到 execution PG
9. 不把旧 `/api/backtest/*` 立刻删除或重写

---

## 8. 推荐对象模型

v1 至少需要 5 个对象：

1. `ResearchSpec`
2. `ResearchJob`
3. `ResearchRunResult`
4. `CandidateRecord`
5. `PromoteDecision`（可先只在设计中定义，v1 不开放）

详细字段见：

- `docs/planning/architecture/2026-04-27-research-control-plane-v1-detailed-design.md`

---

## 9. 执行模型建议

### v1 执行方式

单机、低并发、面向开发者本人使用，因此 v1 不需要上重型队列。

推荐：

1. 后端 job service
2. 本机 runner（v1 可先 in-process task，预留 subprocess runner）
3. 前端轮询 job 状态
4. 结果落库 + artifact 落盘

### 不建议

1. 一上来就引入 Celery / RabbitMQ
2. 一上来就做分布式执行器
3. 一上来就把运行时和研究任务调度耦合

---

## 10. 存储建议

### 当前建议

research 台 v1 **不以“必须上 PG”作为前提**。

原因：

1. 当前 PG 的核心价值在 execution/live truth
2. research v1 的关键在边界和任务模型，不在数据库介质
3. 当前单机低并发研究任务，用 SQLite + 文件制品即可成立

### 建议分层

1. **Job / Candidate 元数据**
   - 可先落独立 SQLite（推荐）
2. **Result / Artifact**
   - JSON / markdown / charts / logs 落盘
3. **Runtime truth**
   - 保持现有 PG，不与 research 混写

---

## 11. API v1 建议

### 写路径

1. `POST /api/research/jobs/backtest`
2. `POST /api/research/candidates`
3. `POST /api/research/candidates/{id}/review`
4. `POST /api/research/jobs/{id}/cancel`（可预留，v1 最小实现可先返回 501）

### 读路径

1. `GET /api/research/jobs`
2. `GET /api/research/jobs/{id}`
3. `GET /api/research/runs/{id}`
4. `GET /api/research/candidates`
5. `GET /api/research/candidates/{id}`

---

## 12. 实施步骤概要

### Phase 0：前置稳定项

1. 确认 `/api/research/backtests` 不因历史脏数据崩溃
2. 确认 console research router 可正常加载
3. 将旧 backtest API 定位为 engine/tooling compatibility，不作为研究台主入口

### Phase 1：对象模型与契约冻结

1. 新增 core models：`ResearchSpec / ResearchJob / ResearchRunResult / CandidateRecord`
2. 新增 repository interface 与 SQLite adapter
3. 冻结 API 合同
4. 明确 artifact 目录与元数据字段

### Phase 2：后端 research runner v1（核心骨架由 Codex 实施）

1. 建立 job service
2. 建立 run storage
3. 建立 candidate CRUD
4. 串上现有 `BacktestJobSpec -> BacktestRequest`
5. 保证 job 状态转移与 artifact 写入可恢复、可解释

### Phase 3：前端研究台 v1

1. New Backtest
2. Runs / Run Detail
3. Candidates / Candidate Detail

### Phase 4：验收与边界校验

1. research 不污染 runtime
2. 结果可复现
3. candidate 不等于 runtime
4. 前端不会把 runtime/config/research 混成一团

### Phase 5：后续路线评估

1. 是否引入 compare / replay 页面
2. 是否扩展 Optuna jobs
3. 是否将 research 元数据迁 PG
4. 是否设计 promote approval，但仍不允许一键 live

---

## 13. 并行簇建议

### 簇 A：架构 / 契约

1. 对象模型
2. API 合同
3. artifact 结构

### 簇 B：后端 runner

1. job 创建
2. 任务执行
3. 结果保存
4. candidate CRUD

> 核心骨架属于本轮关键架构，不外包给 Claude。

### 簇 C：前端研究台

1. 发起页
2. 历史列表
3. 详情页
4. candidate 页

### 簇 D：QA / 边界验证

1. research/runtime 隔离
2. 参数来源可追溯
3. 结果可复现
4. 页面只操作 research 域

> 该簇适合交给 Claude：补单元测试、API 冒烟、fixture、边界用例。

---

## 14. 当前重点关注

### P0 关注点

1. 不允许研究台写 runtime profile
2. 不允许 candidate 直接变 live
3. 不允许继续把 `config_profiles` 当 runtime 配置入口

### P1 关注点

1. job 失败时要有明确错误可读性
2. result / artifact 要有可复现信息
3. baseline / overrides / fixed_params 要清晰显示

### P2 关注点

1. 未来 replay / compare / optuna UI 扩展能力
2. 研究元数据是否需要将来迁入 PG

---

## 15. 最终建议

当前最稳的路线是：

> **把研究台做成一个独立的 Research Control Plane v1，先解决“能发起、能查看、能沉淀 candidate”，而不是继续把 research/config/runtime 重新糊成一套系统。**

下一步执行顺序：

1. Codex 完成核心后端骨架：models / repository / service / runner contract / API shell
2. Claude 补充定向测试和文档盘点
3. Codex 做二次审查，再进入前端研究台 v1
