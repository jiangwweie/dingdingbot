# 模拟盘准入冒烟验证报告

> **验证时间**: 2026-04-23
> **验证目标**: 确认当前执行恢复主链已具备进入模拟盘的最小条件
> **验证范围**: 可运行 + 可恢复 + 可拦截

---

## 验证结果总览

| 场景 | 结果 | 说明 |
|------|------|------|
| **场景 A：正常链路冒烟** | ✅ 通过 | 信号执行流程可运行，breaker 未误触发 |
| **场景 B：异常链路冒烟** | ✅ 通过 | replace_sl_failed 能安全停住，创建 recovery task + breaker + 告警 |
| **场景 C：启动恢复冒烟** | ✅ 通过 | 启动对账能扫描 PG recovery tasks，推进 resolved，breaker 重建正常 |
| **场景 D：熔断拦截冒烟** | ✅ 通过 | breaker 生效后拒绝新信号，不触发 place_order |

---

## 详细验证结果

### 场景 A：正常链路冒烟

**验证目标**: 验证信号 -> 执行 -> 挂保护单 -> 进入受保护状态这条正常路径成立

**验证点**:
- ✅ `ExecutionOrchestrator.execute_signal()` 正常执行
- ✅ Intent 创建成功，ID 格式正确
- ✅ 没有触发 breaker（正常路径不应误触发熔断）

**测试文件**: `tests/smoke/test_sim_trading_readiness.py::test_scenario_a_normal_execution_path`

**结果**: **通过**

---

### 场景 B：异常链路冒烟（replace_sl_failed）

**验证目标**: 验证撤旧 SL 失败时，系统能安全停住，而不是继续错误执行

**验证点**:
- ✅ 触发 `replace_sl_failed`（cancel_order 抛异常）
- ✅ 创建 1 条 PG `execution_recovery_tasks`（recovery_type="replace_sl_failed"）
- ✅ 对应 symbol breaker 生效（is_symbol_blocked 返回 True）
- ✅ 飞书 notifier 路径被调用
- ✅ 系统停止继续动作（place_order 未被调用）

**测试文件**: `tests/smoke/test_sim_trading_readiness.py::test_scenario_b_replace_sl_failed_recovery`

**结果**: **通过**

---

### 场景 C：启动恢复冒烟

**验证目标**: 验证程序启动后，恢复主链能从 PG recovery task 接上

**验证点**:
- ✅ `StartupReconciliationService.run_startup_reconciliation()` 能扫描 active recovery tasks
- ✅ 对于可自然收敛的任务（订单终态），能推进为 `resolved`
- ✅ Phase 4.4 breaker 重建能够根据 active tasks 重建内存 breaker 集合
- ✅ 日志摘要字段与当前实现一致，不报 KeyError / 旧字段错误

**测试文件**: `tests/smoke/test_sim_trading_readiness.py::test_scenario_c_startup_recovery`

**结果**: **通过**

---

### 场景 D：熔断拦截冒烟

**验证目标**: 验证 breaker 生效后，系统会拒绝同 symbol 新信号

**验证点**:
- ✅ breaker 集合中存在目标 symbol
- ✅ `execute_signal()` 直接返回 BLOCKED
- ✅ 不触发 `gateway.place_order()`
- ✅ blocked_reason 为 `CIRCUIT_BREAKER`

**测试文件**: `tests/smoke/test_sim_trading_readiness.py::test_scenario_d_circuit_breaker_blocks_signal`

**结果**: **通过**

---

## 结论

### ✅ **具备模拟盘准入条件**

当前执行恢复主链已满足"可运行 + 可恢复 + 可拦截"的最小条件：

1. **可运行**: 正常链路能跑通，不会误触发 breaker
2. **可恢复**: 异常链路能安全停住，创建 recovery task，启动对账能推进状态
3. **可拦截**: breaker 生效后拒绝新信号，避免错误继续执行

### 当前架构状态

- ✅ `ExecutionIntent` 已进入 PG 主线
- ✅ `execution_recovery_tasks` 是唯一恢复真源
- ✅ `circuit_breaker` 由 PG active recovery tasks 重建
- ✅ SQLite `pending_recovery` 已移除
- ✅ Recovery retry/backoff 策略已显式化（指数退避）

### 建议下一步

可以开始模拟盘测试，建议关注：

1. 真实交易所连接测试（当前使用 mock）
2. 真实 PG 数据库集成测试（当前使用 mock）
3. 长时间运行稳定性观测
4. 多 symbol 并发场景测试

---

## 测试执行记录

```bash
$ pytest tests/smoke/test_sim_trading_readiness.py -v

tests/smoke/test_sim_trading_readiness.py::test_scenario_a_normal_execution_path PASSED [ 25%]
tests/smoke/test_sim_trading_readiness.py::test_scenario_b_replace_sl_failed_recovery PASSED [ 50%]
tests/smoke/test_sim_trading_readiness.py::test_scenario_c_startup_recovery PASSED [ 75%]
tests/smoke/test_sim_trading_readiness.py::test_scenario_d_circuit_breaker_blocks_signal PASSED [100%]

========================= 4 passed, 1 warning in 0.58s =========================
```

---

**验证人**: Claude Sonnet 4.6
**验证日期**: 2026-04-23
