# Task Plan: 盯盘狗策略优化项目

> **Created**: 2026-04-15
> **Last updated**: 2026-04-23 17:30
> **Status**: 第二阶段第一步已完成
> **Archive backup**: `docs/planning/archive/2026-04-23-planning-backup/task_plan.full.md`

---

## 当前阶段

### 阶段结论

第二阶段第一步已完成，SQLite `pending_recovery` 过渡链已完全移除：

1. ✅ `execution_recovery_tasks` 是 PG 正式恢复真源
2. ✅ `circuit_breaker` 由 PG active recovery tasks 重建（内存缓存）
3. ✅ SQLite `pending_recovery` 整条过渡链已移除
4. ✅ 恢复主链统一到 PG `execution_recovery_tasks`

### 当前唯一主线

**第二阶段：执行恢复状态继续向 PG 收敛，并把执行链从”可运行”推到”可运营”。**

### 设计前提（已锁定）

1. 当前主线已明确，不再并行展开回测/前端/API 新线
2. 只要属于执行、恢复、对账、熔断语义，设计时默认优先考虑 PG 主线
3. 非 PG 实现只允许作为明确标注的过渡态

### 当前明确不做

1. 不做回测精细化深挖
2. 不做前端扩张
3. 不做 API 面扩张
4. 不同时推进多条 PG 表迁移

---

## 近期规划

### 目标

把当前执行恢复链继续收口，明确哪些状态进入 PG 主线，哪些过渡态准备退役。

### 第二阶段启动定义

#### 阶段主题

**Phase 2：执行恢复状态收敛与可运营化**

#### 阶段目标

1. 继续把执行恢复相关状态向 PG 主线收敛
2. 明确并启动 SQLite 过渡态的退役路径
3. 让当前执行链从“可运行”走到“可运营”

#### 本阶段只做

1. 恢复/熔断/对账相关状态的收敛
2. recovery task 的最小重试与运维边界梳理
3. 小范围 execution 主链稳定运行前的边界确认

#### 本阶段不做

1. 不做回测精细化
2. 不做参数搜索扩展
3. 不做前端/工作台推进
4. 不做新的 API 面扩张
5. 不同时推进多张核心 PG 表的实切

#### 本阶段入口任务

**优先从 `circuit_breaker` 是否需要 PG 真源化 开始。**

原因：

1. 它是当前恢复链下一层最自然的状态收敛点
2. 比回测/前端/更多 PG 迁移更贴当前主线
3. 比直接退役 SQLite `pending_recovery` 更适合作为第二阶段起点

#### 入口议题当前结论

已完成架构判断：

1. `circuit_breaker` 不建议单独新增 PG 表
2. 更合理的方案是让它作为 `execution_recovery_tasks` 的派生保护状态
3. 第二阶段后续实现应围绕“由 PG active recovery tasks 重建/驱动 breaker”展开

### 近期候选事项（按优先级）

1. **`circuit_breaker` 是否 PG 真源化**
   - 这是第二阶段最自然的入口题
   - 重点不是立刻实现，而是先确认是否值得进入 PG

2. **SQLite `pending_recovery` 的退役路径**
   - 当前它已降级为过渡兼容
   - 后续要定义什么时候停止双写、什么时候完全移除

3. **recovery task 的 retry/backoff / 运维操作面**
   - 当前已有最小 `pending / retrying / resolved / failed`
   - 后续要决定是否需要更正式的重试与人工操作面

### 当前建议顺序

1. 先冻结第二阶段范围
2. 再只挑一个入口任务推进（当前锁定为 `circuit_breaker` 议题）
3. 其它事项保留在后续规划，不进入当前执行态

### 当前执行状态

- 第二阶段**尚未启动实现**
- 当前仅完成阶段定义与入口锁定
- 等用户发令后，再正式进入第二阶段执行

---

## 后续规划

### A. 执行链方向

1. `circuit_breaker` 真源化方案
2. SQLite 过渡态退役
3. 执行恢复运维面收口

### B. PG 迁移方向

1. `ExecutionIntent` 已切通
2. `execution_recovery_tasks` 已接通
3. `orders / positions` 是否继续切 PG，不属于当前阶段默认动作

### C. 研究/回测方向（非当前主线）

1. 回测精细化
2. 参数继续搜索
3. `backtest-studio` 独立前端

这些事项保留 backlog，不进入当前阶段执行。

---

## 约束提醒

1. 强执行语义状态优先向 PG 收敛
2. SQLite 只允许作为明确标注的过渡态
3. 新增执行状态真源前，先复核表设计
4. 测试执行前遵守项目红线，先用户确认

---

## 历史说明

旧版完整任务计划、历史阶段、研究冻结记录、长期 backlog 已备份到：

- `docs/planning/archive/2026-04-23-planning-backup/task_plan.full.md`

主文档今后只保留：

1. 当前阶段
2. 近期规划
3. 后续规划
