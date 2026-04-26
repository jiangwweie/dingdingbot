# 研究链收口审计 + 配置冻结与污染防护设计

> **审计日期**: 2026-04-26
> **审计范围**: 研究链（backtest/optuna/candidate/replay/research API）与 runtime 配置冻结边界
> **审计方法**: 代码静态审计（未运行测试），以代码为准
> **当前主线**: Sim-1 自然模拟盘观察准备

---

## 一、结论摘要

### 核心发现

| 维度 | 结论 | 风险等级 |
|------|------|----------|
| 研究链收口程度 | **部分收口**：research_specs.py 定义了 Spec/Resolver/Reporter 契约，但 30+ 脚本仍旁路直连 | P1 |
| runtime 冻结程度 | **部分冻结**：market/environment 已由 runtime profile 驱动，strategy/risk/execution 仍走旧路径 | P1 |
| 反向污染风险 | **3 个 P0 + 5 个 P1 + 3 个 P2**，最高风险：共享 SQLite 无物理隔离 | P0 |
| 配置绕过入口 | profile 切换 API、backtest config API、ConfigManager 单例注入均可运行时改配置 | P1 |

### 一句话结论

**研究链与 runtime 共享同一个 `data/v3_dev.db`，且研究脚本可通过 `ConfigManager.set_instance()` 污染全局单例、通过 `allow_readonly_update=True` 绕过 profile 只读保护。当前冻结是"约定级"而非"架构级"的。**

---

## 二、研究链收口现状

### 2.1 研究链入口盘点

#### 已收口入口（沿 Spec/Resolver/Reporter）

| 入口 | 文件 | 收口方式 |
|------|------|----------|
| BacktestJobSpec | `src/application/research_specs.py:45` | 统一 Spec 定义，`to_backtest_request()` 转换 |
| OptunaStudySpec | `src/application/research_specs.py:80` | 统一 Spec 定义，`to_optimization_request()` 转换 |
| CandidateArtifactService | `src/application/readmodels/candidate_service.py` | 只读文件系统读取（`reports/optuna_candidates/`） |
| Research API (只读) | `src/interfaces/api_console_research.py` | `/api/research/candidates` 等 4 个 GET 端点 |
| Research Artifacts | `src/application/research_artifacts.py` | 纯元数据 helper，无 I/O 副作用 |

#### 未收口入口（旁路/旧入口/脚本直连）

| 入口 | 文件 | 问题 |
|------|------|------|
| 30+ backtest 脚本 | `scripts/run_eth_backtest.py` 等 | 直接构造 `BacktestRequest`，绕过 `BacktestJobSpec` |
| 20+ Optuna 脚本 | `scripts/run_optuna_*.py` 等 | 直接调用 `StrategyOptimizer`，绕过 `OptunaStudySpec` |
| 8 个 ConfigManager 注入脚本 | `scripts/validate_*.py` 等 | `ConfigManager.set_instance()` 污染全局单例 |
| sim0_runtime_chain_check | `scripts/sim0_runtime_chain_check.py:266-273` | 直接修改 `pipeline._kline_history` 等私有属性 |
| seed_sim1_runtime_profile | `scripts/seed_sim1_runtime_profile.py:93` | `allow_readonly_update=True` 绕过 readonly |
| Backtest API 端点 | `src/interfaces/api.py:2019-2108` | `PUT /api/backtest/configs` 写 `config_entries_v2` |
| Profile 切换 API | `src/interfaces/api_profile_endpoints.py:220` | `PUT /api/profiles/{name}/switch` 无权限控制 |

### 2.2 收口程度评估

```
研究链收口覆盖率 = 已收口入口 / 全部入口 ≈ 5/12 ≈ 42%
```

**表面统一，实际绕过的地方**：
- `BacktestJobSpec` 定义了标准 Spec，但绝大多数脚本不使用它，直接构造 `BacktestRequest`
- `CandidateArtifactService` 只读文件系统，但没有门禁阻止未来"promote candidate to runtime"
- `research_specs.py` 文档声明 "Keep runtime profiles read-only"，但无代码级强制

---

## 三、runtime 冻结链路现状

### 3.1 启动期配置解析链

```
.env / .env.local
    ↓ load_dotenv()
EnvironmentRuntimeConfig (frozen=True)
    ↓
runtime_profiles 表 (data/v3_dev.db)
    ↓ RuntimeProfileRepository.get_profile()
RuntimeConfigResolver.resolve()
    ↓
ResolvedRuntimeConfig (frozen=True)
    ↓
RuntimeConfigProvider (process-local holder)
    ↓
注入到: SignalPipeline, CapitalProtectionManager, ExchangeGateway, NotificationService
```

### 3.2 冻结边界审计

| 模块 | 冻结状态 | 配置来源 | 说明 |
|------|----------|----------|------|
| **Market** (symbol/timeframe/warmup) | ✅ 已冻结 | runtime profile | `main.py:550-569` |
| **Environment** (exchange/PG/feishu) | ✅ 已冻结 | .env + runtime profile | `main.py:294-309` |
| **Strategy** (trigger/filters/direction) | ⚠️ 部分冻结 | runtime profile → StrategyDefinition | `main.py:473-518`，但 SignalPipeline 仍接受 `config_manager` 参数 |
| **Risk** (max_loss/leverage/exposure) | ⚠️ 部分冻结 | runtime profile → RiskConfig | `main.py:479`，但 CapitalProtectionManager 仍读 `config_manager.build_capital_protection_config()` |
| **Execution** (TP/SL/trailing) | ⚠️ 部分冻结 | runtime profile → OrderStrategy | `main.py:488-490` |
| **Asset Polling** | ✅ 已冻结 | runtime profile | `main.py:600-606` |
| **Notification** | ✅ 已冻结 | runtime profile (feishu webhook) | `main.py:274-283` |

### 3.3 仍可运行时改变 runtime 行为的入口

| 入口 | 文件 | 影响 |
|------|------|------|
| `PUT /api/profiles/{name}/switch` | `api_profile_endpoints.py:220` | 切换 ConfigManager 激活 profile，刷新缓存 |
| `PUT /api/backtest/configs` | `api.py:2019` | 修改 `config_entries_v2` 中的回测参数 |
| `ConfigManager.set_instance()` | `config_manager.py:240` | 研究脚本注入新实例替换全局单例 |
| `allow_readonly_update=True` | `runtime_profile_repository.py:98` | 绕过 profile 只读保护直接 upsert |
| YAML 热重载残留 | `config_manager.py` docstring | 文档提及 hot-reload，需确认是否仍存在 |

### 3.4 "看起来冻结，实际上运行中仍会被影响"的路径

1. **ConfigManager 单例共享**：runtime 和研究脚本通过 `ConfigManager.get_instance()` / `set_instance()` 共享同一全局实例。研究脚本运行后，runtime 下次 `get_instance()` 获取到被污染的实例。
2. **config_entries_v2 共享表**：runtime 的 `get_backtest_configs()` 和研究链的 `save_backtest_configs()` 操作同一张表。
3. **runtime_profiles 表**：`seed_sim1_runtime_profile.py` 使用 `allow_readonly_update=True` 直接覆写 `sim1_eth_runtime` profile 的全部内容。

---

## 四、反向污染风险清单

### P0 风险（必须立即修复）

| # | 风险 | 文件 | 污染路径 | 当前防护 |
|---|------|------|----------|----------|
| **R1** | 全组件共享 `data/v3_dev.db` 无物理隔离 | `runtime_profile_repository.py:41`, `config_entry_repository.py:32`, `order_repository.py:45` 等 7+ repo | 研究脚本读写 v3_dev.db → runtime 读取被修改的数据 | `is_readonly`（可被 `allow_readonly_update` 绕过） |
| **R2** | 研究脚本直接 upsert runtime_profiles | `scripts/seed_sim1_runtime_profile.py:87-94` | `upsert_profile("sim1_eth_runtime", ..., allow_readonly_update=True)` → runtime 下次 resolve 读到新内容 | `allow_readonly_update=True` 绕过 |
| **R3** | sim0 脚本直接修改 runtime 内存状态 | `scripts/sim0_runtime_chain_check.py:266-273` | `pipeline._kline_history = {...}`, `pipeline._mtf_ema_indicators.clear()` 等 | testnet 检查（非架构级） |

### P1 风险（Sim-1 前应修复）

| # | 风险 | 文件 | 污染路径 | 当前防护 |
|---|------|------|----------|----------|
| **R4** | Backtester 读取 runtime ConfigManager 单例 | `backtester.py:506-509` | `ConfigManager.get_instance()` → 读取 `config_entries_v2` | try/except 兜底 |
| **R5** | 8 个研究脚本注入 ConfigManager 全局单例 | `scripts/validate_trailing_exit.py:147` 等 | `ConfigManager.set_instance(cm)` → 全局单例被替换 | 无 |
| **R6** | StrategyDefinition/RiskConfig 跨链共享类型 | `domain/models.py`, `strategy_optimizer.py:775-795` | 研究链构造相同类型，`_build_risk_overrides(fallback=runtime_risk_config)` | 按值构造，无架构防护 |
| **R7** | Backtest API KV 参数可间接影响 runtime | `api.py:2019-2108` | `PUT /api/backtest/configs` → `config_entries_v2` → runtime `get_backtest_configs()` | 值范围验证 |
| **R8** | Profile 切换 API 无权限控制 | `api_profile_endpoints.py:220-245` | `PUT /api/profiles/{name}/switch` → ConfigManager 缓存刷新 → runtime 使用新配置 | diff 预览 |

### P2 风险（长期演进中修复）

| # | 风险 | 文件 | 污染路径 | 当前防护 |
|---|------|------|----------|----------|
| **R9** | StrategyOptimizer 共享 connection pool | `strategy_optimizer.py:253` | Optuna → pool → 与 runtime 共享 PRAGMA | DB 文件隔离 |
| **R10** | Research specs 隔离仅文档约定 | `research_specs.py:62-63` | 无门禁防止 "promote candidate to runtime" | 仅文档 |
| **R11** | ReconciliationLock 同步 sqlite3 | `reconciliation_lock.py:54-191` | 同步阻塞 event loop | 独立 DB |

---

## 五、两套防护方案

### 方案 A：最小收口 + 最小防护（推荐 Sim-1 前实施）

**范围**：仅修复 P0 风险 + 关键 P1，不改变架构

**具体措施**：

| # | 措施 | 改动文件 | 工作量 |
|---|------|----------|--------|
| A1 | **移除 `allow_readonly_update=True`**：`seed_sim1_runtime_profile.py` 改为通过正式 API 或在 CI 中显式解锁 | `scripts/seed_sim1_runtime_profile.py` | 0.5h |
| A2 | **研究脚本 ConfigManager 隔离**：8 个脚本改为局部实例化，不调用 `set_instance()` | `scripts/validate_*.py` 等 8 个 | 2h |
| A3 | **Backtester 去除 ConfigManager 单例依赖**：`get_backtest_configs()` 改为参数注入 | `src/application/backtester.py:506-509` | 1h |
| A4 | **Profile 切换 API 加确认锁**：`switch_profile` 增加 `confirm=true` 参数，无确认不执行 | `api_profile_endpoints.py:220` | 1h |
| A5 | **sim0 脚本加架构隔离**：禁止直接操作 `pipeline._*` 私有属性，改为通过公开方法或测试夹具 | `scripts/sim0_runtime_chain_check.py` | 2h |

**收益**：
- 消除 3 个 P0 风险 + 3 个 P1 风险
- Sim-1 启动后 runtime profile 不可被脚本绕过修改
- 研究脚本不再污染 ConfigManager 全局单例

**风险**：
- 不改变共享 DB 架构，研究脚本仍可直接读写 `v3_dev.db`（但 readonly 保护生效）
- 未建立研究链/运行链的物理隔离

**对 Sim-1 的影响**：正面，消除最危险的污染路径

**推荐理由**：最小改动、最大收益，适合 Sim-1 前的稳定窗口

---

### 方案 B：研究链/配置链彻底隔离（长期演进方案）

**范围**：在方案 A 基础上，建立架构级隔离

**具体措施**：

| # | 措施 | 改动文件 | 工作量 |
|---|------|----------|--------|
| B1 | **DB 物理隔离**：runtime 数据（profiles/orders/signals）和 research 数据（backtest/optimization）分到不同 SQLite 文件 | `runtime_profile_repository.py`, `config_entry_repository.py`, `order_repository.py` 等 | 4h |
| B2 | **Runtime Profile 启动校验**：启动时计算 profile content hash，运行期定期校验，不匹配则告警/阻断 | `runtime_config.py`, `main.py` | 3h |
| B3 | **ConfigManager 去单例化**：移除 `set_instance()`/`get_instance()`，改为显式依赖注入 | `config_manager.py`, 所有引用处 | 4h |
| B4 | **研究链独立 ConfigProvider**：研究链使用独立的 `ResearchConfigProvider`，不共享 runtime 的 ConfigManager | 新增 `src/application/research_config_provider.py` | 3h |
| B5 | **Candidate→Runtime 变更门禁**：任何将研究结果写入 runtime 的操作必须经过 `CandidatePromotionService`，带审计日志 | 新增 service | 3h |
| B6 | **配置来源优先级规则**：runtime profile > .env > ConfigManager defaults，禁止反向覆盖 | `runtime_config.py` | 2h |

**收益**：
- 架构级隔离，研究链无法反向污染 runtime
- 配置变更可审计、可追溯
- 为后续多策略/多 profile 演进打基础

**风险**：
- 改动面大，涉及 10+ 文件
- DB 隔离需要迁移脚本
- 可能引入新的兼容性问题

**对 Sim-1 的影响**：中性偏正面，但改动量大，建议 Sim-1 稳定后再实施

**推荐理由**：长期正确方向，但当前阶段不急需

---

## 六、推荐方案与行动项

### 推荐：方案 A（最小收口）

**理由**：
1. Sim-1 当前首要目标是稳定观察，不是架构重构
2. 方案 A 的 5 项措施可在 1 天内完成，风险低
3. 方案 B 的收益在 Sim-1 阶段不紧急，可推迟到 Phase 6 前

### 现在就应该做什么

1. **A1**: 移除 `seed_sim1_runtime_profile.py` 的 `allow_readonly_update=True`
2. **A2**: 8 个研究脚本去掉 `ConfigManager.set_instance()` 调用
3. **A3**: Backtester 的 `get_backtest_configs()` 改为参数注入

### 现在不要做什么

- 不要改 `main.py` 执行主链
- 不要改 PG 执行主链核心实现
- 不要启动 DB 物理隔离迁移
- 不要重构 ConfigManager 单例模式（方案 B 的 B3）

### 明早如果要开实施窗口，最应该先落的 3 项

| 优先级 | 措施 | 理由 |
|--------|------|------|
| **1** | A1: 移除 `allow_readonly_update=True` | 1 行改动，消除 P0 R2 |
| **2** | A2: 研究脚本去掉 `set_instance()` | 8 个文件，消除 P1 R5 |
| **3** | A4: Profile 切换 API 加确认锁 | 1 个文件，消除 P1 R8 |

---

## 七、文件路径索引

### 研究链核心文件

| 文件 | 用途 |
|------|------|
| `src/application/research_specs.py` | BacktestJobSpec / OptunaStudySpec 定义 |
| `src/application/research_artifacts.py` | Git 元数据 helper |
| `src/application/backtester.py` | 回测引擎（v3_pms 模式） |
| `src/application/strategy_optimizer.py` | Optuna 优化器 |
| `src/application/readmodels/candidate_service.py` | Candidate 只读服务 |
| `src/interfaces/api_console_research.py` | Research API 路由 |
| `src/application/readmodels/runtime_config_snapshot.py` | Config snapshot readmodel |

### Runtime 配置链核心文件

| 文件 | 用途 |
|------|------|
| `src/application/runtime_config.py` | RuntimeConfigResolver / Provider / ResolvedRuntimeConfig |
| `src/infrastructure/runtime_profile_repository.py` | runtime_profiles 表 CRUD |
| `src/application/config_manager.py` | ConfigManager（旧路径，含单例） |
| `src/main.py` | 启动流程，Phase 1.1 解析 runtime config |

### 污染风险关键文件

| 文件 | 风险 |
|------|------|
| `scripts/seed_sim1_runtime_profile.py:93` | P0: allow_readonly_update=True |
| `scripts/sim0_runtime_chain_check.py:266-273` | P0: 直接修改 pipeline 私有属性 |
| `scripts/validate_trailing_exit.py:147` 等 8 个 | P1: ConfigManager.set_instance() |
| `src/application/backtester.py:506-509` | P1: 读取 ConfigManager 单例 |
| `src/interfaces/api_profile_endpoints.py:220` | P1: Profile 切换无权限控制 |

---

## 八、未运行测试声明

本审计为**代码静态审计**，未运行任何测试。所有结论基于代码阅读，以代码为准。如需验证，建议：

1. 运行 `pytest tests/unit/ -v` 确认现有测试通过
2. 手动验证 `seed_sim1_runtime_profile.py` 移除 `allow_readonly_update=True` 后的行为
3. 验证 8 个研究脚本移除 `set_instance()` 后仍能正常运行

---

*本审计文档由 PM 安排执行，不覆盖正在活跃改动的 planning 主文档。*
