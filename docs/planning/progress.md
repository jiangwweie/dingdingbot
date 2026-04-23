# Progress Log

> Last updated: 2026-04-23 18:30
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/progress.full.md`

---

## 近期完成

### 2026-04-23 -- 第二阶段第一步完成

1. ✅ 实现 PG 驱动的 circuit breaker 重建
   - ExecutionOrchestrator 新增 `rebuild_circuit_breakers_from_recovery_tasks()`
   - main.py 新增 Phase 4.4 调用 breaker 重建
   - 单元测试全部通过（4/4）

2. ✅ 移除 SQLite `pending_recovery` 过渡链
   - 删除 `src/infrastructure/pending_recovery_repository.py`
   - 收口 ExecutionOrchestrator（删除 `_pending_recovery_repository` 和 `_pending_recovery`）
   - 收口 StartupReconciliationService（删除阶段 2.5）
   - 收口 main.py（删除 `_pending_recovery_repo` 初始化和 shutdown）
   - 删除 3 个过渡测试文件

3. ✅ 恢复主链统一到 PG `execution_recovery_tasks`
   - 恢复真源：PG `execution_recovery_tasks`
   - 派生缓存：内存 `circuit_breaker_symbols`（由 PG 重建）

4. ✅ recovery retry/backoff 策略显式化
   - 最大重试次数：3
   - 基础延迟：60s
   - 延迟上限：900s
   - 规则：指数退避

5. ✅ 模拟盘准入冒烟验证通过
   - 报告：`docs/reports/2026-04-23-sim-trading-readiness-smoke-check.md`
   - 场景 A：正常链路冒烟通过
   - 场景 B：`replace_sl_failed` 异常链路冒烟通过
   - 场景 C：启动恢复冒烟通过
   - 场景 D：熔断拦截冒烟通过

### 当前定性

第二阶段第一步完成，SQLite `pending_recovery` 过渡链已完全移除，恢复主链统一到 PG。

模拟盘准入冒烟已通过，但真实模拟盘全链路尚未实证。下一步进入 Sim-0。

---

## 当前状态

### 已完成

1. ✅ `ExecutionIntent` PG SSOT
2. ✅ `execution_recovery_tasks` PG 正式恢复真源
3. ✅ SQLite `pending_recovery` 过渡链已移除
4. ✅ Circuit breaker 由 PG active recovery tasks 重建
5. ✅ 最小执行恢复闭环
6. ✅ 模拟盘准入冒烟

### 未完成但不阻塞

1. 少量 P2 级初始化/注入一致性收尾
2. 真实模拟盘全链路验证尚未执行

---

## 下一步

### Sim-0：真实模拟盘全链路验证

下一步不是继续扩功能，而是执行 Sim-0：

1. Sim-0.1：启动配置冻结
2. Sim-0.2：主程序真实启动
3. Sim-0.3：信号到 testnet 下单链路验证
4. Sim-0.4：WS 回写与保护单验证
5. Sim-0.5：重启对账与恢复验证

具体任务拆分：

- `docs/planning/sim-0-real-chain-validation-plan.md`
