# Sim-1 准入审查报告

> **审查日期**: 2026-04-26
> **审查基准**: dev 分支 HEAD (7d866f6), tag v3.0.0-dev-snapshot-20260427
> **审查方式**: 静态代码审查 + 关键路径验证，未运行完整测试套件
> **审查人**: Claude Code (Sonnet 4.6)

---

## 一句话准入结论

**有条件进入 Sim-1 观察** — 存在 1 个 P0 阻塞项（console API 运行时崩溃）和 2 个 P1 风险项（无周期性 recovery loop、PG_DATABASE_URL 未配置），修复后可进入观察。

---

## 一、审查边界

### 审什么（准入必审）

| 模块 | 范围 | 理由 |
|------|------|------|
| sim1_eth_runtime profile | 冻结状态、参数完整性 | Sim-1 唯一运行时配置源 |
| RuntimeConfigResolver | 配置解析、无旧路径回落 | 配置完整性是执行安全前提 |
| PG 执行主线 | orders/intents/positions/recovery_tasks | 执行真源，核心闭环 |
| HybridSignalRepository | 实时信号路由 | 信号→执行入口 |
| Console readonly API | health/overview/orders/positions/signals | 观察窗口唯一入口 |
| Frontend runtime 页面 | Execution.tsx | 可视化观察 |
| 启动入口 + Docker | main.py / docker-compose.yml | 部署一致性 |
| 环境变量 | .env / .env.local | 运行时配置注入 |

### 不审什么（不构成阻塞）

| 模块 | 理由 |
|------|------|
| 回测引擎 | 不参与 Sim-1 实盘路径 |
| 策略模板 CRUD | Sim-1 使用冻结 profile，不动态创建 |
| 配置快照版本化 | 附属功能，不影响执行主线 |
| 多交易所适配 | Sim-1 仅 Binance testnet |
| Backtester | 独立沙箱，与实盘路径隔离 |

---

## 二、各维度审查结论

### 2.1 Runtime Freeze / Config Integrity — ✅ 通过

**结论**: sim1_eth_runtime 已冻结，RuntimeConfigResolver 无旧路径回落。

| 检查项 | 结果 | 证据 |
|--------|------|------|
| profile 冻结 | ✅ | `seed_sim1_runtime_profile.py` 定义完整参数集，PG 存储 |
| 无 YAML 散读 | ✅ | `RuntimeConfigResolver` 直接从 PG `runtime_profiles` 表读取，不读 YAML |
| 无隐式 merge | ✅ | `ResolvedRuntimeConfig` 使用 `ConfigDict(frozen=True)`，Pydantic 不可变 |
| 无默认值回落 | ✅ | profile 缺失时 `ValueError` 直接退出，不 fallback |
| 研究链隔离 | ✅ | `SignalPipeline` 接收 `ResolvedRuntimeConfig` 注入，不反向修改 |
| 运行期污染 | ✅ | 无运行期修改 profile 的入口 |

**唯一注意**: `CORE_ORDER_BACKEND` / `CORE_POSITION_BACKEND` 环境变量默认值为 `"sqlite"`，但运行时工厂 `create_runtime_order_repository()` / `create_runtime_position_repository()` 无条件返回 PG。默认值与实际行为不一致，但**不影响运行时**（因为死代码路径 `create_order_repository()` 未被调用）。

### 2.2 Execution Mainline / PG Truth — ⚠️ 有条件通过

**结论**: 执行主线 PG 闭环基本完成，但存在 recovery loop 缺失和 env 默认值误导两个风险。

| 检查项 | 结果 | 证据 |
|--------|------|------|
| orders → PG | ✅ | `create_runtime_order_repository()` → `PgOrderRepository`（无条件） |
| execution_intents → PG | ⚠️ | 依赖 `PG_DATABASE_URL` 设置；未设置时回退内存（易失性） |
| positions → PG | ✅ | `create_runtime_position_repository()` → `PgPositionRepository`（无条件） |
| recovery_tasks → PG | ✅ | `PgExecutionRecoveryRepository`，PG 可用时自动启用 |
| signals → hybrid | ✅ | 实时信号走 PG，回测走 SQLite，显式路由 |
| 启动对账 | ✅ | `StartupReconciliationService` 扫描 SUBMITTED/OPEN/PARTIALLY_FILLED 订单 + recovery tasks |
| partial fill | ✅ | 增量保护订单机制，幂等，SL 替换覆盖完整仓位 |
| SL replace recovery | ❌ | **无周期性后台重试循环**，recovery tasks 仅在启动时处理 |
| 跨库双真源 | ⚠️ | `create_order_repository()` (sqlite) 是死代码但存在，env 默认值误导 |
| 仓位对账 | ❌ | 无交易所→PG 仓位验证，仓位纯由订单填充事件推演 |

**关键风险详解**:

**R1: 无周期性 recovery loop**
- `replace_sl_failed` recovery task 创建后，仅在下次进程启动时由 `StartupReconciliationService` 处理
- 运行期间 SL 下单失败 → 止损保护窗口敞口 → 直到重启才重试
- **Sim-1 影响**: 如果 SL 下单失败，仓位将处于无保护状态，直到人工重启

**R2: env 默认值与运行时不一致**
- `CORE_ORDER_BACKEND` 默认 `"sqlite"`，`CORE_POSITION_BACKEND` 默认 `"sqlite"`
- 但运行时工厂无条件返回 PG，这些默认值永远不会生效
- 不影响运行时行为，但误导运维人员

### 2.3 Observability / Readonly Console — ❌ P0 阻塞

**结论**: Console API 存在运行时崩溃 bug，无法提供可靠观察窗口。

| 检查项 | 结果 | 证据 |
|--------|------|------|
| health endpoint | ❌ | `Optional` 未导入，请求时 Pydantic 解析崩溃 |
| overview endpoint | ❌ | 同上 |
| orders endpoint | ❌ | 同上 |
| positions endpoint | ❌ | 同上 |
| signals endpoint | ❌ | 同上 |
| attempts endpoint | ⚠️ | 读 SQLite，非 PG 真源（但 attempts 本身就存在 SQLite，可接受） |
| repo 注入 | ✅ | console API 使用 `create_runtime_*_repository()`，均指向 PG |
| readmodel 口径 | ✅ | 各 readmodel 查询 PG repo，与执行主线一致 |

**P0 Bug 详解**:

`api_console_runtime.py` 使用了 `Optional[str]` 类型注解 6 处，但**未导入 `Optional`**。由于文件头部有 `from __future__ import annotations`，路由注册不会报错（注解变为字符串延迟求值），但实际请求到达时 Pydantic 尝试解析类型，触发 `NameError: name 'Optional' is not defined`。

**影响**: 所有 console runtime API 端点在请求时崩溃，前端无法获取任何运行时数据。

**修复**: 在文件头部添加 `from typing import Optional`，1 行代码。

**验证方式**: 我通过 FastAPI TestClient 实际测试确认了此 bug — 不导入 `Optional` 时请求返回 500，导入后正常。

### 2.4 Deployment / Startup Readiness — ⚠️ 有条件通过

**结论**: 部署方案完整，但 PG 连接配置缺失。

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 启动入口 | ✅ | `python src/main.py`，启动序列清晰 |
| Docker Compose | ✅ | 3 服务 (PG + backend + frontend)，PG 健康检查 |
| Dockerfile | ✅ | backend + frontend 各有 Dockerfile |
| PG 连接 | ❌ | `.env` 和 `.env.local` 均未配置 `PG_DATABASE_URL` |
| seed 脚本 | ✅ | `scripts/seed_sim1_runtime_profile.py`，写入 PG |
| 启动顺序 | ✅ | docker-compose 依赖 PG healthcheck |
| 前端反代 | ✅ | vite dev server proxy → localhost:8000 |
| .env 安全 | ❌ | `.env` 被 git 追踪，包含真实 API key/secret 和飞书 webhook |

**关键缺失**:

**M1: PG_DATABASE_URL 未配置**
- `.env` 中无 `PG_DATABASE_URL`
- `.env.local` 中也无 `PG_DATABASE_URL`
- 后端启动时 `get_pg_session_maker()` 将失败
- **必须**: 在 `.env.local` 中添加 `PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:yourpassword@localhost:5432/dingdingbot`

**M2: .env 安全风险**
- `.env` 被 git 追踪，包含 Binance testnet API key/secret 和飞书 webhook URL
- 建议: `git rm --cached .env`，添加到 `.gitignore`，轮换已泄露的密钥

### 2.5 Operational Safety — ⚠️ 可接受

**结论**: 异常处理和告警基本到位，但 recovery loop 缺失是最大操作风险。

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 交易所异常处理 | ✅ | `ExchangeGateway` 有 try/except + 重试逻辑 |
| 订单失败处理 | ✅ | `ExecutionOrchestrator` 创建 recovery task |
| 超时/重试 | ✅ | 指数退避重试 |
| 降级逻辑 | ⚠️ | SL 下单失败后无自动恢复，需人工重启 |
| silent failure | ✅ | 未发现 bare `except: pass` 模式 |
| 告警通知 | ✅ | 飞书 webhook 集成，执行事件通知 |
| 日志脱敏 | ✅ | `mask_secret()` 函数 |
| 优雅关闭 | ✅ | SIGTERM handler，关闭连接 |
| 崩溃恢复 | ⚠️ | 启动对账覆盖订单，但无仓位对账 |

---

## 三、P0/P1/P2 风险清单

### P0 阻塞项（必须修复才能进入观察）

| # | 风险 | 影响 | 修复量 | 文件 |
|---|------|------|--------|------|
| P0-1 | Console API `Optional` 未导入 | 所有 runtime API 请求崩溃，前端无法观察 | 1 行 | `src/interfaces/api_console_runtime.py` |

### P1 观察前建议修复项

| # | 风险 | 影响 | 修复量 | 文件 |
|---|------|------|--------|------|
| P1-1 | 无周期性 recovery loop | SL 失败后仓位无保护直到重启 | ~50 行 | `src/application/execution_orchestrator.py` |
| P1-2 | PG_DATABASE_URL 未配置 | 后端无法连接 PG | 配置 | `.env.local` |
| P1-3 | .env 被 git 追踪 | API 密钥泄露 | git 操作 | `.env`, `.gitignore` |

### P2 可带着进入观察但需记录的风险项

| # | 风险 | 影响 | 记录 |
|---|------|------|------|
| P2-1 | env 默认值与运行时不一致 | 误导运维，不影响运行时 | `CORE_ORDER_BACKEND`/`CORE_POSITION_BACKEND` 默认 sqlite 但运行时用 PG |
| P2-2 | 无仓位对账 | 仓位纯推演，无交易所验证 | 启动时仅对账订单，不对账仓位 |
| P2-3 | StartupReconciliationService 类型注解 | 类型标注 OrderRepository(SQLite) 但实际接收 PgOrderRepository | `startup_reconciliation_service.py:29,53` |
| P2-4 | HybridSignalRepository `__getattr__` | 未覆盖的方法静默回落 SQLite | 新增方法可能意外走 SQLite |
| P2-5 | execution_intents 内存回退 | PG_DATABASE_URL 未设置时意图仅存内存 | 进程重启丢失意图状态（Sim-1 会设置 PG，风险低） |

---

## 四、准入前最后动作清单

### 现在必须做的事

1. **修复 P0-1**: 在 `api_console_runtime.py` 头部添加 `from typing import Optional`（1 行）
2. **配置 PG_DATABASE_URL**: 在 `.env.local` 中添加 PG 连接串
3. **运行 seed 脚本**: `python scripts/seed_sim1_runtime_profile.py` 写入 sim1_eth_runtime profile

### 可以观察中继续做的事

1. **P1-1 recovery loop**: 在观察期间如果 SL 下单失败，人工重启即可恢复；可并行开发周期性 recovery loop
2. **P1-3 .env 安全**: 观察期间处理 git 追踪清理和密钥轮换
3. **P2 项**: 记录到 findings.md，不阻塞观察

### 现在不要再扩的事

1. **不做仓位对账** — Sim-1 观察窗口不需要，记录为后续改进
2. **不做 env 默认值清理** — 死代码不影响运行时，观察后统一清理
3. **不做 HybridSignalRepository `__getattr__` 重构** — 当前路由覆盖了所有执行主线方法
4. **不做前端功能扩展** — 当前只读观察足够

---

## 五、涉及的关键文件路径

| 文件 | 审查角色 |
|------|----------|
| `src/interfaces/api_console_runtime.py` | P0 bug 所在 |
| `src/application/runtime_config.py` | 配置冻结验证 |
| `src/application/execution_orchestrator.py` | 执行主线、recovery loop |
| `src/infrastructure/core_repository_factory.py` | PG repo 工厂 |
| `src/infrastructure/database.py` | env 默认值 |
| `src/infrastructure/hybrid_signal_repository.py` | 信号路由 |
| `src/application/startup_reconciliation_service.py` | 启动对账 |
| `scripts/seed_sim1_runtime_profile.py` | Sim-1 profile 种子 |
| `docker-compose.yml` | 部署方案 |
| `.env` / `.env.local` | 环境变量 |
| `gemimi-web-front/vite.config.ts` | 前端反代 |

---

## 六、测试说明

**未运行完整测试套件**。仅通过 FastAPI TestClient 对 `Optional` 缺失 bug 做了轻量验证（确认请求时 500 崩溃）。其余审查基于静态代码分析。

---

*本报告基于 dev 分支 7d866f6 提交状态，代码与文档冲突时以代码为准。*
