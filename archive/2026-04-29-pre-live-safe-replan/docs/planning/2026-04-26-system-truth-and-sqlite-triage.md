# 当前系统真相收口报告

> **生成日期**: 2026-04-26
> **基准提交**: 7d866f6 (feat: complete sim1 deployment with PG+backend stack)
> **未运行测试** — 本报告基于代码静态分析，非运行时验证

---

## 结论摘要

1. **Runtime 执行主线已 PG 闭环**：orders / execution_intents / positions / live signals / signal_take_profits / execution_recovery_tasks 六张表在 PG，runtime 主链全部走 PG 实现。
2. **Config 全量仍在 SQLite**：9+ 个 config repository、runtime_profiles、config_entries_v2、config_snapshots 全部 SQLite，无 PG 表。这是当前最大的"半切"状态。
3. **Signal_attempts 纯 SQLite**：每次 K 线评估的可观测性数据，无 PG 对应表，通过 `HybridSignalRepository.__getattr__` 代理到 SQLite。
4. **Backtest 全链路 SQLite**：回测信号、历史数据、优化记录全部 SQLite，与 PG 主线完全隔离。
5. **启动入口已收敛到 `src/main.py`**，但存在 6 个 shell 脚本入口和 1 个已废弃的 `api_server.py`。
6. **Docker 方案是 sim1 观察的推荐入口**，本地开发仍以 Python 直启为主。

---

## 一、当前系统真相说明

### 1.1 Runtime 主线数据真源

| 执行对象 | 真源 | 存储位置 | 路由机制 |
|----------|------|----------|----------|
| Orders | PG | `orders` (PGCoreBase) | `create_runtime_order_repository()` → `PgOrderRepository` (硬编码) |
| Execution Intents | PG | `execution_intents` (PGCoreBase) | `create_execution_intent_repository()` → `PgExecutionIntentRepository` (需 `PG_DATABASE_URL`) |
| Positions | PG | `positions` (PGCoreBase) | `create_runtime_position_repository()` → `PgPositionRepository` (硬编码) |
| Live Signals | PG | `signals` (PGCoreBase) | `HybridSignalRepository` → `PgSignalRepository` |
| Signal Take Profits | PG | `signal_take_profits` (PGCoreBase) | `HybridSignalRepository` → `PgSignalRepository` |
| Execution Recovery | PG | `execution_recovery_tasks` (PGCoreBase) | `main.py` try/except → `PgExecutionRecoveryRepository` |

**结论**：Runtime 执行主链 6 张核心表全部在 PG，factory 层 `create_runtime_*` 方法已硬编码 PG 实现，不再走环境变量切换。

### 1.2 仍在 SQLite 的对象

| 对象 | SQLite 表 | DB 文件 | 当前作用 |
|------|-----------|---------|----------|
| Signal Attempts | `signal_attempts` | `data/v3_dev.db` | 每次 K 线评估记录（可观测性） |
| Config Snapshots (signal) | `config_snapshots` | `data/v3_dev.db` | 信号触发时的配置快照 |
| Strategies | `strategies` | `data/v3_dev.db` | 策略定义 CRUD |
| Risk Configs | `risk_configs` | `data/v3_dev.db` | 风控参数 |
| System Configs | `system_configs` | `data/v3_dev.db` | 系统参数 |
| Symbols | `symbols` | `data/v3_dev.db` | 交易对池 |
| Notifications | `notifications` | `data/v3_dev.db` | 通知渠道配置 |
| Config History | `config_history` | `data/v3_dev.db` | 配置变更审计 |
| Exchange Configs | `exchange_configs` | `data/v3_dev.db` | 交易所连接凭证 |
| Config Entries V2 | `config_entries_v2` | `data/config_entries.db` | KV 策略参数 |
| Runtime Profiles | `runtime_profiles` | `data/v3_dev.db` | 冻结的 runtime 配置包 |
| Config Snapshots (extended) | `config_snapshots` | `data/config_snapshots.db` | 配置快照（UUID 版） |
| Backtest Signals | `signals` | `data/v3_dev.db` | 回测信号 |
| Backtest Reports | `backtest_reports` | `data/v3_dev.db` | 回测报告 |
| Historical Klines | `klines` | `data/v3_dev.db` | 历史 K 线缓存 |
| Optimization History | — | `data/optimization_history.db` | 策略优化记录 |
| Reconciliation | `reconciliation_reports` / `reconciliation_details` | `data/reconciliation.db` | 对账记录 |
| Order Audit Logs | `order_audit_logs` | `data/v3_dev.db` | 订单审计 |

### 1.3 Runtime Config 生效路径

```
启动 Phase 1:   load_all_configs() (同步 YAML) → ConfigManager 单例
启动 Phase 1:   await config_manager.initialize_from_db() (SQLite config 表覆盖 YAML)
启动 Phase 1.1: RuntimeProfileRepository (SQLite) → RuntimeConfigResolver → RuntimeConfigProvider
运行时:         ConfigManager 内存缓存 + observer 热重载
```

**关键事实**：
- Config 先读 YAML 建默认值，再从 SQLite 覆盖 — 两步初始化
- Runtime Profile 从 SQLite `runtime_profiles` 表加载，由 `RUNTIME_PROFILE` 环境变量选择
- Runtime Config 当前仅驱动 **市场范围**（symbol/timeframe/exchange），策略/风控/执行仍走 ConfigManager 旧路径
- `main.py:243` 明确标注 "partial-cutover mode"

### 1.4 研究链与 Runtime 的边界

| 维度 | Runtime (PG) | Research (SQLite) |
|------|-------------|-------------------|
| 信号写入 | `PgSignalRepository` | `SignalRepository` (via HybridSignal) |
| 信号读取 | `HybridSignalRepository` 按 source 路由 | `source=backtest` 走 SQLite |
| 订单/仓位 | PG only | 无回测订单 |
| K 线数据 | ExchangeGateway 实时推送 | `HistoricalDataRepository` (SQLite) |
| 配置 | ConfigManager + RuntimeProfile | Backtester 自带 config_manager 注入 |
| 对账 | `ReconciliationRepository` (独立 SQLite) | 不涉及 |

**边界清晰度**：研究链与 runtime 通过 `source` 字段隔离，`HybridSignalRepository` 是唯一交叉点。回测不触碰 PG。

### 1.5 Docker 方案定位

| Compose 文件 | 定位 | 包含服务 |
|--------------|------|----------|
| `docker/docker-compose.yml` | **Sim-1 全栈推荐** | PG + Backend |
| `docker/docker-compose.frontend.yml` | **前端可选附加** | Frontend (nginx) |
| `docker-compose.pg.yml` (根目录) | **本地开发 PG** | PG only |

Docker 方案当前是 **sim1 观察环境的主推荐入口**，不是本地开发入口。`docker-compose.yml` 已硬编码 `CORE_ORDER_BACKEND=postgres`，PG 是必选依赖。

### 1.6 当前推荐启动入口

| 场景 | 推荐方式 | 命令 |
|------|----------|------|
| 本地开发 | Python 直启 + 本地 PG | `docker compose -f docker-compose.pg.yml up -d` → `python3 src/main.py` |
| Sim-1 观察 | Docker 全栈 | `cd docker && docker compose up -d` |
| 前端开发 | Vite dev server | `cd gemimi-web-front && npm run dev` |
| 回测 | 独立脚本 | `python3 tests/backtest.py` |

### 1.7 已不再成立的旧假设

| 旧假设 | 当前事实 |
|--------|----------|
| `CORE_ORDER_BACKEND=sqlite` 可用于 runtime | Runtime 主链已硬编码 PG，环境变量仅影响 `create_order_repository()` (非 runtime 入口) |
| `api_server.py` 可独立启动 | 已废弃，API 嵌入 `main.py` Phase 9 |
| Config 从 YAML 文件读取 | YAML 仅作为初始化默认值，真源是 SQLite DB |
| `core.yaml` 是运行时配置 | 已改为 `core.yaml.reference`，标注"仅供参考" |
| Signals 全部走 SQLite | Live signals 已走 PG，仅 backtest 走 SQLite |
| 单一 SQLite 数据库 | 当前有 9 个 `.db` 文件，`v3_dev.db` 197MB |

---

## 二、剩余 SQLite 分级表

### A 类：必须尽快迁移或收口（影响主线）

| # | 对象 | 当前作用 | 影响 | 归类理由 |
|---|------|----------|------|----------|
| A1 | `runtime_profiles` | Runtime 启动 Phase 1.1 的配置真源 | **影响 runtime 启动** — 无此表则 FatalStartupError | Runtime 主链依赖 SQLite 读取配置，与 PG 主线定位矛盾。若 PG 不可用则 runtime 无法启动，但配置真源仍在 SQLite，形成"PG 执行 + SQLite 配置"的割裂 |
| A2 | `signal_attempts` | 每次 K 线评估的可观测性记录 | **影响观察口径** — API `/api/attempts` 读 SQLite | Runtime 信号评估的核心可观测数据，与 PG signals 表无关联。当前无法在 PG 侧做 signal→attempt 关联查询 |
| A3 | Config 全套 (strategies/risk_configs/system_configs/symbols/notifications/exchange_configs) | ConfigManager 启动和运行时配置 CRUD | **影响配置冻结** — 配置变更写入 SQLite，PG 执行链无法感知 | 配置是 runtime 行为的输入，但真源在 SQLite。Runtime profile 虽冻结了市场范围，策略/风控参数仍从 SQLite 动态读取 |

### B 类：可保留一段时间，但必须明确边界

| # | 对象 | 当前作用 | 影响 | 归类理由 |
|---|------|----------|------|----------|
| B1 | `config_entries_v2` | KV 策略参数存储 | 不直接影响 runtime 主线 | 是 config 的补充维度，当前使用频率低，可保留但需标注"非 runtime 真源" |
| B2 | `config_snapshots` (signal 侧) | 信号触发时的配置快照 | 不影响 runtime 执行 | 仅用于事后审计，与 PG signals 无关联查询需求 |
| B3 | `config_history` | 配置变更审计 | 不影响 runtime | 纯审计用途，保留 SQLite 可接受 |
| B4 | `reconciliation_reports/details` | 启动对账记录 | 不影响 runtime 执行 | 独立 DB 文件 (`reconciliation.db`)，边界清晰 |
| B5 | `order_audit_logs` | 订单审计 | 不影响 runtime 执行 | Alembic 迁移创建，当前无活跃写入路径 |

### C 类：可长期保留，不必强迁

| # | 对象 | 当前作用 | 影响 | 归类理由 |
|---|------|----------|------|----------|
| C1 | Backtest signals | 回测信号存储 | **不影响 runtime** — HybridSignalRepository 按 source 隔离 | 回测是独立研究链，与 PG 执行主线无交叉 |
| C2 | `backtest_reports` | 回测报告 | 不影响 runtime | 纯研究数据 |
| C3 | `klines` (historical) | 历史 K 线缓存 | 不影响 runtime | 回测专用，runtime 用 ExchangeGateway 实时推送 |
| C4 | `optimization_history` | 策略优化记录 | 不影响 runtime | 独立 DB 文件，纯研究用途 |
| C5 | `config_snapshots` (extended, UUID 版) | 配置快照服务 | 不影响 runtime | 独立 DB 文件 (`config_snapshots.db`)，4KB 几乎为空 |

---

## 三、当前推荐启动/部署入口

### 3.1 入口盘点

| 入口 | 路径 | 状态 | 推荐度 |
|------|------|------|--------|
| `python3 src/main.py` | 主入口 | ✅ 活跃 | ★★★ 本地开发首选 |
| `python3 -m src.main` | 模块入口 | ✅ 活跃 | ★★★ deploy 脚本使用 |
| `./start.sh` | 根目录一键启动 | ⚠️ 可用但冗余 | ★★ 与 scripts/start.sh 功能重叠 |
| `./scripts/start.sh` | 7 步检查启动 | ⚠️ 可用但冗余 | ★★ 过度检查 |
| `./scripts/start-services.sh` | 简易后台启动 | ⚠️ 可用但冗余 | ★☆ 最简陋 |
| `./scripts/deploy/start.sh` | 部署启动 | ⚠️ 本地+前端 | ★☆ 混合场景 |
| `./scripts/deploy/deploy.sh` | Docker 部署 | ✅ Docker 专用 | ★★ 需要 sudo |
| `cd docker && docker compose up -d` | Docker 全栈 | ✅ Sim-1 推荐 | ★★★ Sim-1 首选 |
| `docker compose -f docker-compose.pg.yml up -d` | 本地 PG only | ✅ 开发辅助 | ★★★ 本地开发辅助 |
| `cd gemimi-web-front && npm run dev` | 前端开发 | ✅ 活跃 | ★★★ 前端首选 |
| `src/api_server.py` | 独立 API | ❌ 已废弃 | ✗ 应删除或标注 |
| `python3 tests/backtest.py` | 回测 | ✅ 独立入口 | ★★ 回测专用 |

### 3.2 推荐入口定型

**本地开发者调试**：
```bash
# 1. 启动 PG（首次或 PG 未运行时）
docker compose -f docker-compose.pg.yml up -d

# 2. 设置环境变量（或使用 .env.local）
export PG_DATABASE_URL=postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot
export RUNTIME_PROFILE=sim1_eth_runtime

# 3. 启动后端
source venv/bin/activate
python3 src/main.py

# 4. 前端（另一个终端）
cd gemimi-web-front && npm run dev
```

**Sim-1 观察**：
```bash
cd docker && docker compose up -d
# 可选：加前端
cd docker && docker compose -f docker-compose.frontend.yml up -d
```

**Docker 方案定位**：**Sim-1 观察的主推荐入口**，本地开发的可选入口（非必须）。

### 3.3 应标记 deprecated 的入口

| 入口 | 原因 |
|------|------|
| `src/api_server.py` | 已废弃，API 已嵌入 main.py |
| `./scripts/start-services.sh` | 功能被 `./start.sh` 覆盖 |
| `./scripts/deploy/deploy-frontend.sh` | 已标注 frontend 迁移到 gemimi-web-front |
| `config/user.yaml.bak` | 含明文 API 密钥，安全隐患 |
| `config/core.yaml.reference` | 标注"仅供参考"但仍存在于 config 目录 |

### 3.4 文档与代码不一致

| 文档 | 代码实际 | 差异 |
|------|----------|------|
| `README.md` "Edit config/user.yaml" | Config 真源是 SQLite DB | 文档仍指向 YAML 编辑 |
| `docs/local-pg.md` "CORE_ORDER_BACKEND 暂时保持 sqlite" | Docker compose 已设 `CORE_ORDER_BACKEND=postgres` | 文档落后于实际 |
| `docs/local-pg.md` 三阶段迁移计划 | Runtime 主链已全 PG | 迁移计划已完成，文档未更新 |
| `main.py:12` "Zero Execution Policy: READ-ONLY" | Phase 5 已实现执行功能 | 注释过时 |

---

## 四、兼容层/过渡态问题清单

### P0 — 当前就应关注

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| P0-1 | `HybridSignalRepository.__getattr__` 静态代理 | `src/infrastructure/hybrid_signal_repository.py:37` | 任何未显式覆盖的方法静默走 SQLite，新增 PG 方法时可能遗漏路由 |
| P0-2 | Config 真源在 SQLite，执行在 PG | `src/application/config_manager.py` 全文件 | 配置变更无法触发 PG 侧感知，配置冻结不完整 |
| P0-3 | `main.py:12` "READ-ONLY" 注释 | `src/main.py:12` | 系统已有执行能力，注释误导 |
| P0-4 | `config/user.yaml.bak` 含明文密钥 | `config/user.yaml.bak` | 安全隐患 |

### P1 — 随后应清理

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| P1-1 | `api_server.py` 废弃文件 | `src/api_server.py` | 整文件已废弃但仍存在 |
| P1-2 | `StrategyEngine` 兼容层 | `src/domain/strategy_engine.py:847-940` | 标注 Legacy 但仍作为 domain 公共 API 导出 |
| P1-3 | `core_repository_factory` 双入口 | `src/infrastructure/core_repository_factory.py` | `create_order_repository()` 仍可返回 SQLite，`create_runtime_order_repository()` 硬编码 PG，两套入口并存 |
| P1-4 | `database.py` 双引擎 | `src/infrastructure/database.py` | `_engine` (SQLite) + `_pg_engine` (PG) 并存，`CORE_ORDER_BACKEND` 等环境变量默认 `sqlite` 与 runtime 实际不符 |
| P1-5 | `runtime_config.py` 默认值 sqlite | `src/application/runtime_config.py:29-30` | `core_order_backend` / `core_position_backend` 默认 `"sqlite"`，与 runtime 硬编码 PG 矛盾 |
| P1-6 | 6 个 shell 启动脚本冗余 | `start.sh`, `scripts/start.sh`, `scripts/start-services.sh`, `scripts/deploy/start.sh` 等 | 功能重叠，使用者困惑 |
| P1-7 | `load_all_configs()` 同步 YAML 初始化 | `src/application/config_manager.py:2025-2040` | 两步初始化（YAML→DB），YAML 步骤已无实际意义 |
| P1-8 | 9 个 SQLite DB 文件 | `data/` 目录 | `v3_dev.db` 197MB + 8 个碎片 DB，职责不清 |
| P1-9 | `v3_orm.py` 旧 ORM 模型 | `src/infrastructure/v3_orm.py` | 使用 SQLite `Base`，与 `pg_models.py` 的 `PGCoreBase` 并存 |
| P1-10 | Domain models 遗留字段 | `src/domain/models.py:733-740` | triggers/trigger_logic/filters/filter_logic 标注 deprecated 但仍存在 |

### P2 — 当前不建议触碰

| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| P2-1 | `FilterFactory.to_legacy_result()` | `src/domain/filter_factory.py:38` | 兼容层，改动影响面大 |
| P2-2 | `console_models.py` legacy fields | `src/application/readmodels/console_models.py:247,263,306` | 前端可能依赖，需协调 |
| P2-3 | `SignalRepository` legacy column handling | `src/infrastructure/signal_repository.py:315,588,796,874,1064` | 向后兼容逻辑，回测链路依赖 |
| P2-4 | `backtester.py` ConfigManager 单例 fallback | `src/application/backtester.py:515-518` | 已有显式注入路径，fallback 是安全网 |
| P2-5 | Alembic 迁移文件 | `migrations/versions/` | 历史记录，不应删除 |

---

## 五、减熵建议与优先级

### 现在就该做的定型动作（P0）

| # | 动作 | 风险 | 工作量 |
|---|------|------|--------|
| 1 | 删除 `config/user.yaml.bak`（含明文密钥） | 安全 | 1 min |
| 2 | 修正 `main.py:12` 注释（READ-ONLY → 执行系统） | 误导 | 1 min |
| 3 | 更新 `README.md` 启动说明（YAML → DB 配置） | 文档 | 15 min |
| 4 | 更新 `docs/local-pg.md` 迁移状态（已完成） | 文档 | 10 min |
| 5 | 在 `HybridSignalRepository.__getattr__` 加 warning log | 可观测性 | 5 min |

### 可随后做的清理动作（P1）

| # | 动作 | 风险 | 工作量 |
|---|------|------|--------|
| 6 | 删除 `src/api_server.py` | 低 | 2 min |
| 7 | 合并 shell 启动脚本（保留 `start.sh` + `stop.sh`，删除冗余） | 低 | 30 min |
| 8 | `core_repository_factory` 统一入口（删除 `create_order_repository()` SQLite 分支，仅保留 `create_runtime_*`） | 中 | 1 h |
| 9 | `database.py` 环境变量默认值对齐（`CORE_ORDER_BACKEND` 默认 `postgres`） | 中 | 30 min |
| 10 | `runtime_config.py` 默认值对齐（`core_order_backend` 默认 `postgres`） | 低 | 15 min |
| 11 | `load_all_configs()` 移除 YAML 步骤，直接从 DB 初始化 | 中 | 2 h |
| 12 | SQLite DB 文件合并或职责标注（`v3_dev.db` + 8 碎片 → 明确归属） | 低 | 1 h |
| 13 | `StrategyEngine` 兼容层标注 `@deprecated` 并添加迁移指引 | 低 | 30 min |
| 14 | Domain models 遗留字段添加 `@deprecated` 装饰器 | 低 | 30 min |

### 当前不建议触碰的东西（P2）

| # | 原因 |
|---|------|
| `HybridSignalRepository` 整体重构 | signal_attempts 迁移 PG 前不宜动路由层 |
| `v3_orm.py` 删除 | 回测链路仍依赖旧 ORM |
| `SignalRepository` legacy column 处理 | 前端和回测可能依赖 |
| Config 全量迁移 PG | 大工程，需独立规划，不应在收口窗口做 |
| `console_models.py` legacy fields | 需前端协调 |

---

## 附录：SQLite DB 文件现状

| 文件 | 大小 | 主要内容 | 活跃度 |
|------|------|----------|--------|
| `data/v3_dev.db` | 197 MB | Config + Signals + Orders + Klines + Backtest | 高（config + backtest） |
| `data/signals.db` | 200 KB | 信号数据（旧？） | 低 |
| `data/orders.db` | 268 KB | 订单数据（旧？） | 低 |
| `data/config.db` | 88 KB | 配置数据 | 中 |
| `data/config_entries.db` | 0 KB | KV 策略参数 | 低 |
| `data/config_snapshots.db` | 4 KB | 配置快照 | 低 |
| `data/optimization_history.db` | 80 KB | 优化历史 | 低 |
| `data/backtest.db` | 0 KB | 回测数据 | 低 |
| `data/reconciliation.db` | — | 对账记录 | 中 |
| `data/v2.db` | 0 KB | 旧版数据 | 无（应清理） |

---

*本报告基于 2026-04-26 代码静态分析生成，未运行测试验证。以代码为准，文档不一致处已在第四节标注。*
