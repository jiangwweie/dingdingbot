# 2026-04-27 边界治理主线重排

> 状态：执行中
> 前提：execution PG 主线代码修复已完成，runtime/console 定向测试通过，4 个 PG Repository 真实 PostgreSQL 集成测试通过

---

## 1. 当前主线一句话

后续主线不再是“继续把能迁的表迁到 PG”，而是把系统正式切成四条稳定边界：

1. `runtime execution truth`
2. `runtime observability`
3. `config freeze / parameter governance`
4. `research / history`

---

## 2. 从 5 份审计中提炼出的当前有效风险

### P0：仍会影响主线可信度或边界稳定性的风险

1. **runtime/config 仍可能被研究链污染**
   - 来源：`2026-04-26-research-chain-audit-and-config-freeze-design.md`
   - 当前风险：
     - `ConfigManager.set_instance()` 被研究脚本调用
     - profile 切换入口缺少更硬确认
     - shared `data/v3_dev.db` 仍让“研究脚本误改 runtime 配置”成为可能
   - 结论：这已经超过“文档约定”层面，需要进入主计划

2. **`signals / signal_attempts` 的角色尚未正式定型**
   - 来源：`2026-04-26-full-db-source-audit.md`
   - 当前风险：
     - 如果它们其实还参与执行判断/恢复/状态推进，就不能继续被当作“可长期留 SQLite 的纯观察层”
   - 结论：需要先做角色定性，再决定迁移，而不是直接开迁

3. **PG 主线虽已验证，但边界文义仍未正式冻结**
   - 来源：`2026-04-26-runtime-observation-audit.md` + `sqlite-retirement-design.md`
   - 当前风险：
     - 开发者可能继续把“observability 修复”“config 改动”“signals 迁移”混进 execution 主线
   - 结论：必须把“什么算 execution truth”写成 SSOT

### P1：应尽快收紧，但不阻塞 execution PG 主线完成

1. `PositionInfo.current_price / mark_price` 语义缺口
2. `list_active()` / `list_blocking()` 方法语义需要明确
3. 前端/只读 API 需要继续显式表达数据来源（PG vs SQLite vs Exchange snapshot）
4. runtime profile / config source priority 仍需更正式定义

### 已过时或已被代码/测试解除的旧风险

1. `orders API 链 fallback 读 SQLite`：已不再是当前主风险，需以最新代码为准复核
2. `runtime overview / health 永远 DEGRADED`：已修复并通过测试
3. `PgOrderRepository` 方法不完整：主路径所需方法已补齐并通过测试
4. `PG repo 无验证`：4 个 PG Repository 已完成真实 PostgreSQL 集成测试

---

## 3. 新的主线重排

### 主线 A：固化 execution truth 边界

目标：把已经完成的 execution PG 主线写成正式边界，而不是“当前实现碰巧这样”。

必须明确：

1. 哪些对象属于 execution truth：
   - `orders`
   - `execution_intents`
   - `positions`（execution projection）
   - `execution_recovery_tasks`
2. 哪些执行语义不得再回落到 SQLite
3. 哪些只读 API / console 面必须以 PG 为准

### 主线 B：固化 observability 边界

目标：明确哪些数据是“执行真相”，哪些只是“观察/诊断/补充”。

必须明确：

1. `signals / signal_attempts` 当前是：
   - 纯 observability / diagnosis
   - 还是仍参与 execution decision
2. `account_snapshot` 与 `PG positions projection` 的优先级
3. 前端看到的数据来源如何表达

### 主线 C：配置冻结与参数链防污染

目标：让 runtime freeze 成为架构事实，而不是人为约定。

必须明确：

1. runtime profile 的发布/冻结边界
2. resolver / provider / ConfigManager 的来源优先级
3. 哪些配置启动后不可变
4. 哪些入口必须显式确认才允许切换 active profile

### 主线 D：research / runtime 隔离

目标：research 继续产出 candidate、报告、比较，但不得绕写 runtime。

必须明确：

1. research 允许写什么
2. research 不允许写什么
3. candidate 进入 runtime 的唯一合法动作是什么

---

## 4. 接下来不作为主线推进的事项

以下事项默认不再作为下一步主任务：

1. 继续迁移更多 SQLite 表到 PG
2. 直接启动 `signals / signal_attempts` 迁移
3. config 全域迁 PG
4. backtest / klines / history 迁 PG
5. 多实例 / 分布式语义增强

---

## 5. 下一轮实施建议

### 由 Codex / GPT 继续承担

1. 边界治理设计与主线收敛
2. 风险重新定级
3. execution / observability / config / research 四边界的 SSOT 文档落盘

### 适合交给 Claude / GLM 的杂活

1. 清理研究脚本里的 `ConfigManager.set_instance()`
2. 给 profile switch API 增加确认参数的测试
3. 补 `PositionInfo.current_price / mark_price` 相关测试或兼容修复测试
4. 只读 API / 前端契约类的小型机械修补

---

## 6. 当前阶段结论

execution PG 主线已经从“代码闭环”进入“边界治理”阶段。

后续成败不再取决于还能迁多少表，而取决于：

1. execution truth 是否被正式钉死
2. observability 是否不再伪装成 truth
3. config freeze 是否不再能被研究链旁路污染
4. research 是否被限制在 candidate / report 边界内
