# 2026-04-27 Research Control Plane v1 决策记录

> 状态：设计封板
> 目的：在实现前扫清核心决策问题，避免研究台把 runtime / config / research 再次耦合。

---

## 1. 背景判断

当前系统已经进入 Sim-1 自然模拟盘观察阶段：

1. execution PG mainline 已闭环
2. live signals 已进入 PG hybrid 路径
3. runtime profile 已冻结为启动期真源
4. 前端以只读观察面为主
5. research 仍偏脚本、文件产物和离线流程

因此下一阶段最值钱的工作不是继续迁库，而是建设一个可用的 research control plane，让研究任务可以被发起、记录、回看、沉淀 candidate，同时保持 runtime 不被污染。

---

## 2. 关闭的决策

### D1：研究台的产品形态

**决策**：采用 Research Control Plane，而不是简单 Backtest Form。

**理由**：

1. 研究任务需要生命周期，而不是一次 HTTP 请求
2. 结果需要沉淀和复盘，而不是只返回一段 JSON
3. candidate 需要和 runtime 明确隔离

**影响**：

1. 新增 job / run / candidate 对象
2. 前端从“提交表单等结果”改成“提交任务、轮询状态、查看结果”

---

### D2：v1 功能范围

**决策**：A 架构 + B 范围。

v1 只做：

1. 单次 backtest job
2. runs 列表
3. run detail
4. candidate 创建与 review

v1 不做：

1. runtime profile 编辑
2. 一键 promote live
3. 全量 Optuna UI
4. 通用配置编辑器
5. 研究报表全量 PG 化

---

### D3：API 边界

**决策**：新增 `/api/research/jobs/*` 作为研究台主入口。

现有 `/api/backtest/*` 定位为：

1. 兼容旧测试与工具
2. 回测 engine/tooling 层入口
3. 不作为新前端研究台的主产品 API

**验收点**：

1. 前端 Research v1 不直接调用 deprecated `/api/backtest`
2. 新 job API 不写 runtime truth

---

### D4：执行模型

**决策**：v1 使用本机 runner；核心代码骨架由 Codex 实施。

v1 可先采用：

1. FastAPI background task / in-process local runner
2. 单实例串行或低并发执行
3. 明确状态流转

预留：

1. subprocess runner
2. cancel
3. worker queue

暂不引入：

1. Celery
2. RabbitMQ
3. 分布式 worker

---

### D5：存储介质

**决策**：research metadata v1 使用独立 SQLite，artifact 使用文件系统。

推荐路径：

1. `data/research_control_plane.db`
2. `reports/research_runs/{job_id}/`

不写入：

1. execution PG schema
2. runtime profile SQLite 表
3. config profile 旧配置域

**理由**：

1. 当前单机低并发足够
2. research 不是 execution truth
3. 独立 DB 可以降低污染 runtime 的风险

---

### D6：Candidate 语义

**决策**：Candidate 是研究候选，不是 runtime 发布物。

Candidate 可做：

1. 记录 run_result
2. 记录 review notes
3. 标记 `DRAFT / REVIEWED / REJECTED / RECOMMENDED`

Candidate 不可做：

1. 自动修改 `runtime_profiles`
2. 自动切换 live 策略
3. 自动创建执行任务

---

### D7：Claude 分工

**决策**：核心代码骨架由 Codex 实施；Claude 只做杂活。

Codex 负责：

1. core models
2. repository contract
3. job service
4. runner contract
5. API shell
6. 边界审查

Claude 可负责：

1. 单元测试补齐
2. API fixture / TestClient 用例
3. 文档现状盘点
4. 前端字段对齐检查
5. 非核心 CRUD 查询补齐

---

## 3. 风险与约束

| 风险 | 等级 | 处理 |
| --- | --- | --- |
| 研究台误写 runtime profile | P0 | API/service 层禁止引用 runtime profile 写接口 |
| candidate 被误解为 live | P0 | 字段、页面、文档都标注 candidate-only |
| 同步回测导致 HTTP 超时 | P1 | job API 立即返回，runner 后台执行 |
| 回测历史脏数据导致列表 500 | P1 | repository/readmodel 防御解析，脏字段返回 None |
| SQLite 并发写瓶颈 | P2 | v1 低并发接受；后续按需要迁 PG |
| 旧 `/api/backtest/*` 继续扩散 | P2 | 新前端只接 `/api/research/jobs/*` |

---

## 4. 实施路线

### Phase 0：前置稳定

1. 确认 console research router 可加载
2. 确认 backtest report 脏数据不会让列表 500
3. 明确旧 backtest API 与新 research job API 的职责边界

### Phase 1：核心骨架

1. 新增 research control plane domain models
2. 新增 SQLite repository
3. 新增 job service
4. 新增 runner contract
5. 新增 API shell

### Phase 2：Backtest job 串联

1. `ResearchSpec` 转 `BacktestJobSpec`
2. `BacktestJobSpec` 转 `BacktestRequest`
3. 调现有 backtester
4. 写 result + artifact
5. 更新 job status

### Phase 3：Candidate 工作流

1. run result 标记 candidate
2. candidate review / status update
3. candidate detail

### Phase 4：前端 v1

1. Research Home
2. New Backtest
3. Runs
4. Run Detail
5. Candidates
6. Candidate Detail

### Phase 5：后续演进

1. compare / replay
2. Optuna job
3. research metadata PG 化
4. promote approval workflow

---

## 5. 开工判断

可以开工，但开工顺序必须是：

1. 先落核心后端骨架
2. 再补测试
3. 再接前端
4. 最后再讨论 PG 化或 Optuna 扩展

本轮不应从前端页面或大规模测试开始。
