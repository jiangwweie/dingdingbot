> [!WARNING]
> **SUPERSEDED**: This document is a historical knowledge-pack snapshot and must not be used as the current project baseline.
> Current baseline: `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`.
> The old positioning around "BRC Reset / Opportunity Structure Discovery v0" has been superseded by Owner correction on 2026-05-29:
> "fast trial-and-review research system for small risk-capital Campaigns".
> See `docs/ops/knowledge-pack/DOCUMENT_GOVERNANCE.md` for authority rules.

---

# PROJECT_OVERVIEW.md

Last updated: 2026-05-29
Status: research-only snapshot, not production-ready

---

## 1. 项目一句话定义

本项目是一个 AI-agent 辅助的低频加密衍生品个人杠杆 Campaign 研究与治理系统，当前处于 Bounded Risk Campaign (BRC) 治理框架构建和 Opportunity Structure Discovery 研究阶段，不具备实盘交易能力，不具备自动化策略执行能力。

## 2. 项目当前阶段

当前阶段标签：`RBC Reset / Opportunity Structure Discovery v0`

最近一次业务方向修正（2026-05-29）：项目目标不是全自动通用策略系统，而是一个快速试错-评审的研究系统，用于小风险资本 Campaign。

当前活动轨道：
1. **Opportunity Structure Discovery v0** — 开放研究漏斗、假设注册、最小证伪计划
2. **Bounded Risk Campaign Mainline** — 隔离风险桶、Owner 选择 Playbook、有界尝试、硬风险信封
3. **Runtime Safety Foundation** — Live-safe、OwnerGate、StrategySignalV2、权限状态、执行链安全
4. **Evidence Archive** — Direction A、CPM-1、Direction C/D/E、SSD、VEI 等历史研究

当前工程阶段：`BRC-R4 API Surface Cleanup + Local Operator Console`（已完成），下一步是 `BRC-R5-003 Broad OHLCV-only Directional Smoke Screen` 后续研究推进。

## 3. 核心目标

- 执行安全（execution safety）
- 账户级风控（account-level risk control）
- 研究与运行时隔离（research/runtime isolation）
- 可解释决策（explainable decisions）
- 可追溯行为（traceable behavior）
- 清晰模块边界（clear module boundaries）
- 按需扩展（on-demand extensibility）

长期方向：全自动、低频、多方向、可扩展。当前阶段不追求多策略平台、多资产引擎、数据湖或组合引擎。

## 4. 当前主架构

```text
Domain Layer (纯 Python，无 I/O)
  ├── bounded_risk_campaign.py     BRC 领域模型
  ├── brc_admission.py             准入门领域模型
  ├── personal_campaign.py         PLC 领域合约
  ├── strategy_family_registry.py  策略族注册
  ├── historical_ohlcv.py          历史 OHLCV 数据模型
  ├── historical_signal_evaluation.py  历史信号评估
  ├── models.py / indicators.py    基础模型和指标
  └── matching_engine.py           匹配引擎（回测用）

Application Layer
  ├── bounded_risk_campaign_service.py  BRC 服务
  ├── brc_admission_service.py          准门服务
  ├── brc_operation_layer.py            操作层
  ├── brc_operator_workflow.py           LangGraph LLM 工作流
  ├── campaign_state_service.py          Campaign 状态机
  ├── execution_orchestrator.py          执行编排器 [Codex-owned]
  ├── order_lifecycle_service.py         订单生命周期 [Codex-owned]
  ├── position_projection_service.py     仓位预测 [Codex-owned]
  ├── capital_protection.py              资本保护 [Codex-owned]
  ├── startup_reconciliation_service.py  启动对账 [Codex-owned]
  ├── reconciliation.py                  周期对账 [Codex-owned]
  ├── periodic_reconciliation.py         周期对账
  ├── global_kill_switch.py              全局断路器
  ├── account_risk_service.py            账户风险服务
  ├── backtester.py                      回测引擎
  └── runtime_context.py                 运行时上下文

Infrastructure Layer
  ├── exchange_gateway.py          交易所网关 [Codex-owned, Binance/ccxt]
  ├── pg_models.py                 PG ORM 模型
  ├── pg_brc_*.py                  BRC 相关 PG 仓库
  ├── pg_campaign_state_repository.py
  ├── pg_admission_repository.py
  ├── database.py                  数据库连接
  └── jsonl_trace_sink.py          决策追踪输出

Interfaces Layer
  ├── api.py                       主 API 组装 [BRC-first]
  ├── api_brc_console.py           BRC 控制台 API
  ├── api_console_runtime.py       运行时控制 API
  ├── api_runtime_safety.py        运行时安全 API
  └── operator_auth.py             操作员认证 [TOTP + Password]

Frontend (gemimi-web-front → BRC Operator Console)
  ├── /command-center              指挥中心
  ├── /llm-copilot                 LLM 副驾驶
  ├── /strategy-playbook           策略/Playbook
  ├── /risk-account                风险与账户
  └── /runtime-control             运行时控制
```

## 5. 主要模块

| 模块 | 作用 | 当前状态 | 关键风险 |
|---|---|---|---|
| BRC Domain + Service | Campaign 创建、Playbook 切换、尝试序列、Mock PnL、利润保护、锁损 | 已实现，Binance testnet 验证通过 | mock PnL 不等于真实收益 |
| BRC Admission Gate | 策略族试入准门，PG 持久化，Phase 1-17 元数据操作 | 已实现 Phase 1-17，均为元数据操作 | 无实际运行时执行；signal-to-trade 转换为 future phase |
| Playbook Governance R0 | Playbook 注册、切换决策日志、冷却规则 | 文档/治理级别完成 | 无运行时实现 |
| BRC Operator Console | 本地 Web 控制台，TOTP 登录，5 个 P0 页面 | 已实现，浏览器验证通过 | 本地开发版本，无 cloud hardening |
| Campaign State Machine | PG 持久化状态机、转换表、审计记录、回放证据 | 已实现 | broader reconciliation coverage 为 future work |
| Runtime Safety (GKS/StartupGuard/Reconciliation) | 全局断路器、启动守卫、周期对账、保护健康监控 | 已实现，testnet 验证通过 | 进程本地状态，非持久化断路器 |
| Account Risk Service | 账户级风险检查、清算距离、总敞口 | 已实现 | multi-symbol rehearsal 仍 blocked |
| Backtester | 策略回测引擎（bar-level） | 已实现 | 非完整交易模拟器，无 tick/orderbook |
| Historical Research | 历史 OHLCV 目录、研究采样、信号评估 | 基础实现，migration 已存在 | 尚未完成完整端到端验证 |
| Strategy Family Registry | 策略族注册表、PG 持久化 | Migration 已存在，repository 已实现 | 未确认是否已集成到运行时 |

## 6. 当前已经可用的能力

- BRC Campaign 创建、Playbook 切换、有界尝试、Mock PnL、利润保护、锁损（Binance testnet 验证通过）
- BRC 控制台 Web UI：指挥中心、LLM 副驾驶、策略/Playbook、风险与账户、运行时控制
- 操作员认证：用户名/密码/TOTP
- LangGraph LLM 工作流（只读操作 + 受控 testnet rehearsal）
- 操作层持久化：操作日志、审查决策、工作流运行记录
- 全局断路器 (GKS)、启动守卫、Campaign 状态机
- 周期对账、保护健康监控、外部关闭卫生清理
- 回测引擎（bar-level，含成本模型）
- 历史 OHLCV 数据导入和目录管理
- Admission Gate 元数据操作链（Phase 1-17）

## 7. 当前尚未确认的能力

- 完整的策略信号到执行的端到端链路
- signal-to-trial-trade-intent 转换
- auto_within_budget 实际执行
- observe-only/no-entry 运行时集成
- 任何真实资金操作
- 多符号并行运行时
- 策略池自动路由
- 完整的账户权益实时读取链路（需确认 PG/Exchange 双路径是否完整）
- withdrawal/transfer 接口（明确 out-of-scope）
- 云端部署
- Feishu 集成

## 8. 当前最大风险

1. **无 runtime-eligible 策略候选**：CPM-1 已暂停，Direction A 已归档为 PAUSE_FRAGILE/NON_RUNTIME，当前无任何策略通过 SRR-002 标准
2. **研究与生产边界模糊风险**：系统代码中存在 execution orchestrator、exchange gateway、order lifecycle 等生产级组件，但当前仅在 testnet 受控场景下验证
3. **Mock PnL 与真实收益差异**：BRC 的 mock PnL 是业务状态证据，不代表真实交易结果
4. **进程本地状态**：GKS、startup guard、daily risk stats 等均为进程本地状态，进程重启后依赖 PG 恢复
5. **LLM 安全边界**：LLM 被设计为只读 advisory，但 LangGraph 工作流中存在受控 testnet 操作路径

## 9. 最近一次推进到哪里

2026-05-29：完成 BRC-R5-003 Broad OHLCV-only Directional Smoke Screen，筛选出 3 个 `trial_candidate_with_known_risks`：
- MI-001 BNB long
- MI-001 SOL long
- VI-001 ETH long

当前证据仅为历史 OHLCV-only，有意不完整：无成本/滑点/资金费率/清算建模，无随机/持有基线，无滚动 campaign 破产率。

## 10. 当前最重要的事实

1. 项目当前无实盘交易能力，无任何实盘授权
2. BRC 框架在 Binance testnet 上完成受控验证，但不等于实盘可用
3. 所有策略研究均为 research-only / backtest-only / not production-ready
4. CPM-1 已通过 OOS gate（2021/2022 均为 OOS_NEGATIVE），暂停，停止晋升路径
5. Direction A 已归档为 POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME
6. 当前最优先研究方向是 broad coarse screening，而非 deep TB-001 挖掘
7. 系统采用 testnet-first / production-blocked 运营姿态

## 11. 当前最重要的不确定项

1. 历史研究报告中的信号统计是否仍可复现（需要确认数据完整性）
2. BRC Admission Gate 的完整链路是否已端到端测试（Phase 1-17 均为元数据操作）
3. 历史 OHLCV 数据的完整性（已确认 BTC/ETH/SOL，BNB 需要验证）
4. Strategy Family Registry 的 PG 链路完整性
5. Account Facts 的完整读取链路（exchange + PG 双路径）
6. 广域 smoke screen 的 3 个候选方向是否能通过更严格的 cost/baseline 测试

## 12. 当前建议下一步

| 优先级 | 下一步 | 类型 |
|---|---|---|
| P0 | 对 3 个 trial candidate 补充成本/滑点/资金费率建模 | research-only |
| P0 | 对 3 个 trial candidate 做随机入场/持有基线对比 | research-only |
| P1 | 验证 BRC Admission 完整链路端到端（如有 Owner 授权） | read-only / testnet |
| P1 | 验证 Strategy Family Registry PG 链路 | read-only fact check |
| P2 | 完善 Historical Research Sampling 端到端链路 | research-only |

## 13. 安全边界

**绝对禁止（除非 Owner 明确单独授权）**：
- 实盘交易（real live trading）
- 使用真实资金下单
- 修改 execution permission
- 自动化策略执行
- 提现/转账
- 修改 API key / credentials
- 策略自提升（strategy self-elevation）
- 绕过 Operation Layer
- 无限加仓行为
- 自动扩展 symbol/side/leverage

**当前允许（需 Owner 授权）**：
- Binance testnet 受控操作
- 本地运行时启动和验证
- 只读交易所同步
- 研究报告生成

**默认安全姿态**：
- `TRADING_ENV=simulation`（默认）
- `EXCHANGE_TESTNET=true`（本地验收默认）
- GKS fail-closed
- startup guard 默认 blocked
- campaign state 默认 observe

## 14. 给接手 AI 的阅读顺序

1. **PROJECT_OVERVIEW.md**（本文件）— 全局概览
2. **CURRENT_STATE_AND_NEXT_ACTIONS.md** — 当前状态和下一步
3. **FACT_REGISTRY.md** — 事实注册表，区分已确认/待确认/已否定
4. **MODULE_MAP.md** — 模块地图，含安全边界
5. **STRATEGY_RESEARCH_HISTORY.md** — 策略研究历史和失败方向
6. **PROMPT_LIBRARY.md** — 可复用提示词模板

**关键规则**：
- 所有内容默认 research-only，除非有明确证据证明已验证
- 涉及 execution / order / trade / account / exchange 的内容必须单独审核
- 不要把未确认能力写成已实现
- 不要把研究结果包装成生产可用
