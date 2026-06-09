> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# 交易控制台前端重构前置事实核验

## Real Control Console Code Fact Reconstruction

**日期**: 2026-06-03
**分支**: dev
**提交**: 51f0085b (fix: govern binance hedge ccxt payload adapter)
**标签**: brc-bnb-prelive-20260601-r35
**范围**: READ-ONLY code fact investigation — no code changes, no migrations, no PG mutation, no exchange actions

---

## Section 1 — Repo / Deployment Baseline

| 项目 | 值 |
|------|-----|
| 当前分支 | `dev` |
| 当前提交 | `51f0085b` |
| 部署标签 | `brc-bnb-prelive-20260601-r35` |
| Tokyo 部署引用 | `.env.tokyo.prelive.example` — `TRADING_ENV=live`, `EXCHANGE_TESTNET=false`, `RUNTIME_CONTROL_API_ENABLED=false`, `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false` |
| 环境模式区分 | 4 个关键环境变量: `TRADING_ENV` (live/testnet), `EXCHANGE_TESTNET` (true/false), `RUNTIME_CONTROL_API_ENABLED`, `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED` |
| 当前本地配置 | `.env.local` 和 `.env` 均为 testnet 模式 |
| 生产环境示例 | `.env.production.example` — `TRADING_ENV=live`, 所有 control/injection 禁用 |
| 前端查询环境 | `GET /api/runtime/safety` 返回 `runtime_bound`, `profile`, `testnet`, `gks_active`, `startup_guard_armed`; `GET /api/brc/readiness` 返回 `environment_boundary` |
| Mock/Testnet 数据混入风险 | **存在**: StrategyCandidatesV2 中 4/5 候选为 `sample_data` 硬编码; StrategyGroupShelf 有 `display_model_only` fallback |
| 数据库验证 | `validate_pg_core_configuration()` 在 production/live 模式下阻止: `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`, `RUNTIME_CONTROL_API_ENABLED=true`, `BRC_EXECUTION_PERMISSION_MAX=order_allowed` |

---

## Section 2 — Current Frontend Inventory

### 2.1 活跃路由总览

| # | 路由 | 组件 | 目的 | API 调用 | 写操作 | 实盘相关 | 可能误导 Owner | 建议 |
|---|------|------|------|----------|--------|----------|---------------|------|
| 1 | `/login` | `Login.tsx` | Owner 认证 (username+password+TOTP) | `brcApi.login()` | 是(session) | 是 | 否 | 复用 |
| 2 | `/home` | `OwnerConsoleV2.tsx:HomeV2` | 工作台仪表盘: 优先事项、流程进度、候选、就绪状态 | 20+ via `useConsoleData()` | 否 | 是 | 可能 — `canExecute` 计算可能误导 | 复用 |
| 3 | `/trial-confirmation` | `OwnerConsoleV2.tsx:TrialConfirmationV2` | 授权前确认流: 风险确认、草案创建、激活、执行触发 | 20+ + 4 写调用 | **是** | **是** | **是** — 执行按钮可触发真实执行 | **重写** |
| 4 | `/strategy-candidates` | `OwnerConsoleV2.tsx:StrategyCandidatesV2` | 策略候选选择 | 20+ | 否 | 低 | **是** — 4/5 硬编码 sample_data | **重写** |
| 5 | `/strategy-groups` | 同上 (别名) | 同上 | 同上 | 否 | 低 | 同上 | 合并 |
| 6 | `/intents` | `OwnerConsoleV2.tsx:IntentsV2` | 执行计划与授权链状态 | 20+ | 否 | 低 | 轻度 — 可能显示过期数据 | 复用 |
| 7 | `/account-orders` | `OwnerConsoleV2.tsx:AccountOrdersV2` | 账户事实与订单 (只读) | 20+ | 否 | 是 | 否 | 复用 |
| 8 | `/analysis` | `OwnerConsoleV2.tsx:AnalysisV2` | 复盘: testnet 证据与结论 | 20+ | 否 | 低 | 否 | 复用 |
| 9 | `/trace` | `OwnerConsoleV2.tsx:TraceV2` | 链路追踪时间线 | 20+ | 否 | 低 | 否 | 复用 |

### 2.2 已退休路由 (25 个，全部重定向到 `/home`)

`command-center`, `markets-orders`, `campaign`, `review-evidence`, `strategy-families`, `fixed-testnet-rehearsal`, `llm-copilot`, `strategy-playbook`, `risk-account`, `runtime-control`, `summary`, `guide`, `dashboard`, `campaigns`, `playbooks-strategy`, `parameters`, `audit-trail`, `ai-investigator`, `operator`, `workflow`, `review`, `ledger`, `audit`, `runtime-safety`, `developer`

组件文件仍存在于 `src/pages/brc/` 但 `main.tsx` 中未导入。

### 2.3 关键前端架构事实

| 项目 | 事实 |
|------|------|
| 主组件文件 | `OwnerConsoleV2.tsx` — 3792 行/182KB 单体文件，包含全部 8 个页面组件 |
| 数据加载 | `useConsoleData()` 在每次刷新时并行调用 20+ API — 所有页面共享 |
| API 客户端 | `api.ts` — 47 个方法 (28 读, 19 写), 67 个导出类型 |
| 类型安全 | 所有响应类型含 `live_ready: false` 字面量类型 (结构性安全) |
| 环境指示 | `PageShell` 永久显示 3 个标签: "环境可见" / "证据优先" / "无交易入口" |
| 状态胶囊 | `AppLayout` 头部: 琥珀色圆点 + "实盘只读 . 记录意图 . 禁止下单" |
| 环境模式 | `EnvironmentMode`: `SIM` / `LIVE` / `UNKNOWN`，LIVE 带脉冲动画 |
| 数据源追溯 | `carrierDecisionView()` 追踪每个字段来源: `backend_api` / `derived_from_backend` / `frontend_local_state` / `sample_data` / `unavailable` |
| 确认对话框 | **无** — 仅有本地复选框和按钮禁用状态 |
| TOTP 重验证 | **无** — 仅登录时验证 TOTP，执行触发前无二次验证 |
| 轮询机制 | **无自动轮询** — 仅手动刷新按钮 (`refreshCount`) |
| 错误处理 | `Promise.all` + 单独 `.catch()`，失败端点返回 `null`，UI 显示 "数据未接入" |
| Mock API | `mockApi.ts` 存在但**未被生产代码导入** — 死代码 |
| 管理页面 | `src/pages/admin/` **不存在** |

### 2.4 TrialConfirmationV2 写操作链 (关键路径)

```
1. createOwnerRiskAcknowledgement()  → POST /api/brc/admission/risk-ack     → PG 写入
2. createOwnerAuthorizationDraft()    → POST /api/brc/admission/draft       → PG 写入
3. activateOwnerLiveAuthorization()   → POST /api/brc/admission/activate    → PG 写入
4. executeOwnerTrialAuthorization()   → (端点路径未在 api.ts 中明确定义)      → 可能触发执行
```

### 2.5 API 方法完整清单 (47 个)

#### 读操作 (28 个)

| 方法 | HTTP | 路径 | 关键响应字段 | 前端使用? |
|------|------|------|-------------|----------|
| `login` | POST | `/api/auth/login` | `authenticated, username, current_stage, live_ready` | 是 |
| `logout` | POST | `/api/auth/logout` | `authenticated: false` | 是 |
| `session` | GET | `/api/auth/session` | `authenticated, username, expires_at_ms` | 是 |
| `dashboard` | GET | `/api/brc/dashboard` | `current_stage, terminology, owner_questions` | 否 |
| `readiness` | GET | `/api/brc/readiness` | `mode, current_conclusion, action_cards, runtime_state, risk_decision, environment_boundary` | 是 |
| `mi001SolReadiness` | GET | `/api/brc/readiness/mi001-sol` | `candidate, evidence, risk_policy, readiness_verdict` | 是 |
| `strategyGroupReviewability` | GET | `/api/brc/strategy-groups/observation/reviewability` | `primary_groups, secondary_groups` | 是 |
| `strategyGroupLiveObservationV1` | GET | `/api/brc/strategy-groups/observation/live-readonly` | `candidates, current_signals, signal_history` | 是 |
| `strategyGroupObservationCasesV1` | GET | `/api/brc/strategy-groups/observation/cases` | `cases, case_count` | 是 |
| `mi001BnbTrialReadinessGap` | GET | `/api/brc/mi001/bnb-trial-readiness-gap` | `gap_matrix, testnet_rehearsal_design` | 是 |
| `strategyTrialReadinessV1` | GET | `/api/brc/strategy-trial/readiness` | `strategy_profile, risk_cap_profile, preflight_result` | 是 |
| `strategyTrialArchitectureGovernance` | GET | `/api/brc/strategy-trial/architecture-governance` | `owner_review_packet, authorization_draft, minimal_live_trial_gate` | 是 |
| `secondCarrierExpansion` | GET | `/api/brc/carriers/second-expansion/bootstrap` | `carriers, warnings` | 是 |
| `multiCarrierBudgetAuthorizationCurrent` | GET | `/api/brc/budget-authorization/current` | `latest_budget_authorization, eligible_carrier_ids` | 是 |
| `ownerTrialFlowCurrent` | GET | `/api/brc/admission/current` | `carrier, strategy_warnings, hard_blockers, authorization_status` | 是 |
| `runtimeSafety` | GET | `/api/runtime/safety` | `runtime_bound, profile, flatness_known, gks_active, startup_guard_armed` | 否 |
| `marketsOrders` | GET | `/api/brc/markets-orders` | `symbols, open_orders, active_positions` | 否 |
| `accountFacts` | GET | `/api/brc/account-facts` | `source, truth_level, positions, open_orders, reconciliation_status` | 是 |
| `auditTrail` | GET | `/api/brc/audit-trail` | `timeline, operation_results` | 否 |
| `askInvestigator` | POST | `/api/brc/ask` | `intent, conclusion, trace` | 否 |
| `reviewPacket` | GET | `/api/brc/operator/review-packet` | (untyped) | 否 |
| `nextEligibility` | GET | `/api/brc/next-eligibility` | (untyped) | 否 |
| `evidence` | GET | `/api/brc/evidence` | (untyped) | 否 |
| `listActions` | GET | `/api/brc/operator/actions` | `actions[]` | 否 |
| `listWorkflows` | GET | `/api/brc/llm/workflows` | `workflows[]` | 否 |
| `listReviewDecisions` | GET | `/api/brc/review-decisions` | `review_decisions[]` | 否 |
| `listStrategyFamilies` | GET | `/api/brc/strategy-families` | `StrategyFamily[]` | 是 |
| `operationCapabilities` | GET | `/api/brc/operations/capabilities` | `capabilities[]` | 否 |
| `listOperations` | GET | `/api/brc/operations` | `operations[]` | 否 |

#### 写操作 (19 个)

| 方法 | HTTP | 路径 | PG 写入? | 交易所操作? | 前端使用? |
|------|------|------|---------|-----------|----------|
| `createOwnerRiskAcknowledgement` | POST | `/api/brc/admission/risk-ack` | 是 | 否 | 是 |
| `createOwnerAuthorizationDraft` | POST | `/api/brc/admission/draft` | 是 | 否 | 是 |
| `activateOwnerLiveAuthorization` | POST | `/api/brc/admission/activate` | 是 | 否 | 是 |
| `executeOwnerTrialAuthorization` | POST | (未确定) | 是 | **可能** | 是 |
| `bnbLiveExecutionBridgeDryRun` | POST | `/api/brc/execution-bridge/dry-run` | 否 | 否 (dry-run) | 是 |
| `armStartupGuardPreflight` | POST | `/api/brc/readiness/startup-guard/preflight-arm` | 是 | 否 | 是 |
| `runStrategyGroupLiveObservationV1Once` | POST | `/api/brc/strategy-groups/observation/live-readonly` | 是 | 否 | 否 |
| `planOperator` | POST | `/api/brc/operator/plan` | 是 | 否 | 否 |
| `runOperatorAction` | POST | `/api/brc/operator/actions/{id}/run` | 是 | **可能** | 否 |
| `createWorkflow` | POST | `/api/brc/llm/workflows` | 是 | 否 | 否 |
| `confirmWorkflow` | POST | `/api/brc/llm/workflows/{id}/confirm` | 是 | **可能** | 否 |
| `createReviewDecision` | POST | `/api/brc/review-decisions` | 是 | 否 | 否 |
| `preflightOperation` | POST | `/api/brc/operations/preflight` | 是 (draft) | 视 op_type | 否 |
| `confirmOperation` | POST | `/api/brc/operations/confirm` | 是 | **可能** | 否 |
| `cancelOperation` | POST | `/api/brc/operations/{id}/cancel` | 是 | 否 | 否 |
| `getAdmissionDecision` | GET | `/api/brc/admission-decisions/{id}` | 否 | 否 | 否 |
| `getTrialBinding` | GET | `/api/brc/admission-trial-bindings/{id}` | 否 | 否 | 否 |
| `listAdmissionDecisions` | GET | `/api/brc/admission/decisions` | 否 | 否 | 否 |
| `listTrialBindings` | GET | `/api/brc/admission/trial-bindings` | 否 | 否 | 否 |

### 2.6 未被活跃 V2 页面调用的 API 方法 (26 个)

`dashboard`, `runtimeSafety`, `marketsOrders`, `auditTrail`, `askInvestigator`, `planOperator`, `runOperatorAction`, `listActions`, `createWorkflow`, `confirmWorkflow`, `listWorkflows`, `listReviewDecisions`, `createReviewDecision`, `operationCapabilities`, `preflightOperation`, `confirmOperation`, `cancelOperation`, `listOperations`, `operationDetail`, `runStrategyGroupLiveObservationV1Once`, `armStartupGuardPreflight`, `nextEligibility`, `currentCampaign`, `evidence`, `getAdmissionDecision`, `getTrialBinding`

---

## Section 3 — Backend API Inventory

### 3.1 挂载路由器

| 路由器 | 文件 | 前缀 | 端点数 | 挂载状态 |
|--------|------|------|--------|---------|
| auth_router | `operator_auth.py` | `/api/auth` | 3 | 已挂载 |
| runtime_safety_router | `api_runtime_safety.py` | `/api/runtime` | 1 | 已挂载 |
| brc_router | `api_brc_console.py` | `/api/brc` | 44 | 已挂载 |
| operator_router | `api_brc_console.py` | `/api/brc/operator` | 6 | 已挂载 |
| workflow_router | `api_brc_console.py` | `/api/brc/llm/workflows` | 4 | 已挂载 |
| dev_testnet_router | `api_brc_console.py` | `/api/dev/testnet/brc` | 7 | 已挂载 |
| **合计已挂载** | | | **69** | |

### 3.2 未挂载路由器 (潜在可用)

| 路由器 | 文件 | 前缀 | 估计端点数 | 状态 |
|--------|------|------|-----------|------|
| `api_console_runtime.py` | `api_console_runtime.py` | `/api/runtime` | ~40 | **未挂载** — 仅内部调用 |
| `api_v1_config.py` | `api_v1_config.py` | `/api/v1/config` | ~35 | **未挂载** |
| `api_console_research.py` | `api_console_research.py` | `/api/research`, `/api/config` | ~10 | **未挂载** |
| `api_research_jobs.py` | `api_research_jobs.py` | `/api/research` | ~5 | **未挂载** |
| `api_profile_endpoints.py` | `api_profile_endpoints.py` | N/A | N/A | **死代码** — 无 `app` 对象 |

### 3.3 认证与安全

| 机制 | 详情 |
|------|------|
| 密码 | PBKDF2-SHA256, 210,000 次迭代 |
| TOTP | 6 位码, 30 秒窗口, 1 窗口漂移 |
| 会话 | HMAC 签名 cookie (`brc_operator_session`), 默认 8 小时 TTL |
| 凭证来源 | 环境变量: `BRC_OPERATOR_USERNAME`, `BRC_OPERATOR_PASSWORD_HASH`, `BRC_OPERATOR_TOTP_SECRET`, `BRC_OPERATOR_SESSION_SECRET` |
| 主机限制 | `_require_internal_runtime_control()` 拒绝非 localhost 请求 (127.0.0.1, ::1, localhost) |
| CORS | `localhost:3000`, `127.0.0.1:3000`, `localhost:5173`, `127.0.0.1:5173` |

### 3.4 能触及交易所的路径

**已挂载端点中没有直接下单/撤单/平仓的端点。** 间接路径:

| 路径 | 触发方式 | 交易所操作 | 安全守卫 |
|------|---------|-----------|---------|
| Operation Layer → `fixed_testnet_rehearsal` → `api_console_runtime._execute_brc_fixed_testnet_rehearsal` | `POST /api/brc/operations/confirm` with `operation_type="fixed_testnet_rehearsal"` | 下单 | 确认短语 + preflight + 8+ 安全门 |
| Admission campaign shell creation | `POST /api/brc/operations/confirm` with `operation_type="admission_campaign_creator"` | 否 (仅 PG) | 确认短语 |
| Runtime start | `POST /api/brc/operations/confirm` with `operation_type="admission_runtime_start_from_handoff_starter"` | 否 (仅 PG) | 确认短语 |
| Strategy state activation | `POST /api/brc/operations/confirm` with `operation_type="admission_strategy_state_activator"` | 否 (仅 PG) | 确认短语 |

### 3.5 端点安全门汇总

| 安全门 | 适用端点 | 机制 |
|--------|---------|------|
| `require_operator_session` | 所有非 health/auth 端点 | Cookie 认证 |
| `require_internal_runtime_control` | 所有 BRC mutation 端点 | localhost 检查 |
| `RUNTIME_CONTROL_API_ENABLED` | mutation 端点 | 环境变量检查 |
| `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED` | controlled entry/close | 环境变量检查 |
| Confirmation phrase | Operation confirm | 短语匹配 |
| Preflight required | Operation confirm | preflight_id 匹配 |
| Idempotency key | Operation confirm | 幂等键去重 |

### 3.6 错误响应格式

```json
{"error_code": "<status_code>", "message": "<detail>"}
```

| HTTP 状态码 | 含义 |
|------------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求错误/验证失败 |
| 401 | 未认证 |
| 403 | localhost 限制 / 环境变量禁用 / 错误 profile |
| 404 | 未找到 |
| 409 | 冲突/被阻止 / 确认不匹配 / 规则违反 / 已执行 |
| 422 | Pydantic 验证错误 |
| 500 | 内部错误 |
| 502 | 交易所获取失败 |
| 503 | 服务不可用 / PG 不可用 |

---

## Section 4 — PG Entity / Schema Map

### 4.1 核心执行链表

| 实体 | 表名 | 仓库 | 关键字段 | 状态枚举 | 关系 | 时间戳 | 迁移链 | API 使用 | 前端可显示 |
|------|------|------|---------|---------|------|--------|--------|---------|-----------|
| Order | `orders` | 内联 | id, signal_id, symbol, direction, order_type, order_role, status, price, trigger_price, requested_qty, filled_qty, average_exec_price, reduce_only, exchange_order_id | CREATED, SUBMITTED, PENDING, OPEN, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED | self FK (parent_order_id), 1:N child orders | created_at, updated_at, filled_at | 008+ | 是 | 是 |
| ExecutionIntent | `execution_intents` | 内联 | id, signal_id, symbol, status, order_id, authorization_id, exchange_order_id, blocked_reason, blocked_message, failed_reason | pending, blocked, submitted, failed, protecting, partially_protected, completed | FK → authorizations, 1:N → recovery_tasks | created_at, updated_at | 038 | 是 | 部分 |
| Position | `positions` | 内联 | id, signal_id, symbol, direction, quantity, entry_price, mark_price, leverage, unrealized_pnl, realized_pnl, is_closed | N/A (is_closed bool) | 独立 | opened_at, closed_at, updated_at | 008 | 是 | 是 |
| RecoveryTask | `execution_recovery_tasks` | 内联 | id, intent_id, related_order_id, symbol, recovery_type, status, error_message, retry_count | pending, retrying, resolved, failed | FK → execution_intents | created_at, updated_at, resolved_at | 原始 PG | 是 | 部分 |

### 4.2 授权链表

| 实体 | 表名 | 关键字段 | 状态枚举 | 关系 | 迁移链 |
|------|------|---------|---------|------|--------|
| OwnerRiskAcknowledgement | `brc_owner_risk_acknowledgements` | acknowledgement_id, carrier_id, acknowledged_warning_codes, owner_id | N/A (source=owner_console) | 1:N → drafts, authorizations | 035 |
| AuthorizationDraft | `brc_bounded_live_trial_authorization_drafts` | draft_id, carrier_id, symbol, side, max_notional, quantity, leverage, protection_plan_type, status, consumed, expires_at_ms | `pending_owner_live_authorization` (唯一值) | FK → acknowledgements, 1:1 → authorizations | 035 |
| BoundedLiveTrialAuthorization | `brc_bounded_live_trial_authorizations` | authorization_id, draft_id, carrier_id, symbol, side, status, consumed, hard_blockers | `owner_live_authorized_pending_final_preflight` (唯一值) | FK → drafts (unique), FK → acknowledgements, 1:N → clearances, intents, plans | 036 |
| MultiCarrierBudgetAuthorization | `brc_multi_carrier_budget_authorizations` | budget_authorization_id, status, carrier_ids | `draft_disabled_pending_owner_authorization` (唯一值) | FK → acknowledgements, FK → authorizations | 037 |

**PG 强制约束 (CHECK constraints)**:
- Draft: `single_use IS TRUE`, `live_ready IS FALSE`, `order_permission_granted IS FALSE`, `execution_permission_granted IS FALSE`, `non_live_metadata_only IS TRUE`
- Authorization: `single_use IS TRUE`, `live_authorized IS TRUE`, `live_ready IS FALSE`, `final_preflight_required IS TRUE`, `next_executable IS FALSE`, `metadata_only IS TRUE`

### 4.3 安全/控制表

| 实体 | 表名 | 关键字段 | 状态枚举 | 迁移链 |
|------|------|---------|---------|--------|
| GKS State | `global_kill_switch_state` | state_key(='global'), active(bool), reason, updated_by | active: true/false | 039 |
| Scoped Clearance | `brc_scoped_runtime_safety_clearances` | clearance_id, clearance_type(gks/startup_guard), authorization_id, symbol, side, max_notional, status | active, revoked, expired | 040 |
| Campaign State | `runtime_campaign_state` | scope_key, status, reason, updated_by | observe, armed, paused, profit_protect, loss_locked, hard_locked, closed | 015 |
| Campaign Transitions | `runtime_campaign_state_transitions` | scope_key, sequence_number, previous_status, target_status, trigger, accepted | (同上 + accepted bool) | 016 |
| Protection Price Plan | `brc_protection_price_plans` | plan_id, authorization_id, carrier_id, symbol, side, phase, tp_price, sl_price, quantity | valid, blocked | 042 |
| Daily Risk Stats | `daily_risk_stats_aggregates` | scope_key, stats_date, realized_pnl, trade_count | N/A | 012 |
| Daily Risk Events | `daily_risk_stats_events` | event_key, position_id, exit_order_id, delta_realized_pnl | N/A | 012 |

### 4.4 BRC Campaign / Operation 表

| 实体 | 表名 | 关键字段 | 状态枚举 | 迁移链 |
|------|------|---------|---------|--------|
| BRC Campaign | `brc_campaigns` | campaign_id, status, current_playbook_id, realized_pnl, attempt_count | observe, active, profit_protect, loss_locked, ended | 017 |
| BRC Operation | `brc_operations` | operation_id, operation_type, status, risk_level | draft, awaiting_confirmation, executing, executed, blocked, failed, cancelled, expired, noop | 022 |
| Preflight Snapshot | `brc_preflight_snapshots` | preflight_id, operation_id, decision, warnings, blockers | allow, warn, block, unavailable, expired | 022 |
| Execution Result | `brc_execution_results` | operation_id, status, rechecked | executed, blocked, failed, cancelled, expired, noop | 022 |
| Operator Action | `brc_operator_actions` | action_id, draft_action, executable, mutation_executed(CHECK=false), live_ready(CHECK=false) | planned, executed, blocked | 018 |
| Review Decision | `brc_review_decisions` | review_id, decision, testnet_only(CHECK=true), real_live_authorized(CHECK=false) | accepted, needs_followup, next_campaign_blocked, testnet_rehearsal_authorized | 019 |
| Workflow Run | `brc_workflow_runs` | workflow_run_id, status, mutation_executed(CHECK=false), live_ready(CHECK=false) | awaiting_confirmation, running, completed, blocked, failed | 021 |
| LLM Intent | `brc_llm_intents` | intent_id, action, live_ready(CHECK=false) | planned, executed, blocked | 020 |

### 4.5 Strategy Family / Admission 表

| 实体 | 表名 | 关键字段 | 状态枚举 | 迁移链 |
|------|------|---------|---------|--------|
| Strategy Family | `brc_strategy_families` | strategy_family_id, family_key, name, status | active, intake, parked, rejected | 023 |
| Family Version | `brc_strategy_family_versions` | version_id, version, hypothesis, supported_symbols | N/A | 023 |
| Family Registry | `brc_strategy_family_registry` | family_id, version_id, status, family_type | registered_hypothesis_only, active_observation_candidate, live_readonly_observation, parked, retired | 027 |
| Admission Request | `brc_admission_requests` | admission_request_id, trial_env, trial_stage | trial_env: testnet/live; trial_stage: development_validation/funded_validation | 023 |
| Admission Decision | `brc_admission_decisions` | admission_decision_id, decision, execution_mode | admit, admit_with_constraints, reject, park | 023 |
| Trial Binding | `brc_admission_trial_bindings` | binding_id, binding_status | planned, binding_reserved, cancelled, expired, invalidated, campaign_created, runtime_constraints_installed, runtime_installed | 024 |
| Owner Risk Acceptance | `brc_owner_risk_acceptances` | owner_risk_acceptance_id, trial_env, trial_stage | N/A | 023 |
| Admission Audit Log | `brc_admission_audit_log` | audit_id, event_type, ref_type, ref_id | 18 event types | 023 |
| Trial Constraint | `brc_trial_constraint_snapshots` | trial_constraint_snapshot_id, status | pending_risk_capital_resolution, installable, installed, expired, invalidated | 023 |
| Trial Trade Intent | `brc_trial_trade_intents` | intended_action, decision | intended: entry/increase/exit/reduce/hold/unknown; decision: recorded/blocked/unavailable | 026 |

### 4.6 审计/对账表

| 实体 | 表名 | 关键字段 | 迁移链 |
|------|------|---------|--------|
| Order Audit Log | `order_audit_logs` | id, order_id, signal_id, old_status, new_status, event_type, triggered_by, metadata | 原始 PG |
| Reconciliation Report | `reconciliation_reports` | report_id, is_consistent, actions_taken | 008 |
| Reconciliation Detail | `reconciliation_details` | report_id, local_data, exchange_data, action_result | 008 |
| Read Model Report | `reconciliation_read_model_reports` | report_id | 013 |
| Read Model Mismatch | `reconciliation_read_model_mismatches` | report_id, type, local_data, exchange_data, metadata | 013 |

### 4.7 迁移链概览

**41 个迁移文件**，所有 ORM 模型均有对应迁移。无孤立迁移。

### 4.8 外键关系链

```
brc_owner_risk_acknowledgements
  └─ brc_bounded_live_trial_authorization_drafts (linked_acknowledgement_id)
  │    └─ brc_bounded_live_trial_authorizations (draft_id, unique)
  │         ├─ brc_scoped_runtime_safety_clearances (authorization_id)
  │         ├─ brc_protection_price_plans (authorization_id)
  │         └─ execution_intents (authorization_id)
  │              └─ execution_recovery_tasks (intent_id)
  └─ brc_bounded_live_trial_authorizations (linked_acknowledgement_id)
  └─ brc_multi_carrier_budget_authorizations (linked_acknowledgement_id, nullable)

orders (parent_order_id → orders.id, self-referential)
signal_take_profits (signal_id → signals.signal_id, CASCADE)
```

### 4.9 JSONB 使用模式

- `metadata` — 通用元数据袋 (clearances, transitions, campaigns, reviews)
- `signal_payload` / `strategy_payload` — 执行意图载荷
- `current_state_snapshot` / `target_state` / `account_snapshot` / `order_snapshot` / `runtime_snapshot` / `campaign_snapshot` / `playbook_snapshot` / `risk_result` — preflight 快照
- `bucket` / `risk_envelope` / `attempts` — campaign 状态
- `rounding` / `filters` / `blockers` — protection plan
- 所有 BRC JSONB 列使用 `.with_variant(JSON(), "sqlite")` 兼容测试

---

## Section 5 — Carrier / Candidate Support

### 5.1 Carrier 定义位置

Carrier **不是 PG 实体**。Carrier 是代码中的配置/概念对象，通过 `carrier_id` 字符串引用在各表中关联。

| 项目 | 状态 |
|------|------|
| Carrier PG 表 | **NOT_FOUND** — 无独立表 |
| Carrier 列表 API | **NOT_FOUND** — 无独立列表端点 |
| 当前/活跃 Carrier API | **PARTIAL** — `GET /api/brc/admission/current` 返回 `carrier` 对象 (从 trial flow 构建) |
| Carrier symbol/side/cap/leverage/protection 配置 | **SUPPORTED** — 在 `brc_bounded_live_trial_authorization_drafts` 和 `brc_bounded_live_trial_authorizations` 中作为字段存储 |
| Carrier 可用性/阻止状态 | **PARTIAL** — `GET /api/brc/strategy-trial/architecture-governance` 返回 carrier 相关 gate 信息 |
| Carrier 关联到 authorization/execution/review | **SUPPORTED** — 通过 `carrier_id` 字段在各表中关联 |
| Carrier Shelf 可从当前 API 构建 | **NOT_FOUND** — 无 carrier shelf API |
| 第二 Carrier 扩展 | **PARTIAL** — `GET /api/brc/carriers/second-expansion/bootstrap` 返回候选但非完整 shelf |

### 5.2 Carrier 支持矩阵

| Carrier Shelf 功能 | 支持程度 | 依赖 |
|-------------------|---------|------|
| 列出所有可用 carriers | NOT_FOUND | 需要新 API |
| 显示 carrier 当前状态 | PARTIAL | `admission/current` + `architecture-governance` |
| 显示 carrier 配置详情 | SUPPORTED | 从 draft/authorization 字段读取 |
| 显示 carrier 阻止原因 | PARTIAL | `architecture-governance` 返回 gate 信息 |
| Carrier 选择 → 授权流 | SUPPORTED | `admission/risk-ack` → `admission/draft` → `admission/activate` |
| Carrier 关联执行结果 | PARTIAL | `authorization_id` 关联存在，但无 carrier-level 聚合查询 |
| Carrier 历史表现 | NOT_FOUND | 需要新查询 |

---

## Section 6 — Authorization Lifecycle Facts

### 6.1 生命周期阶段

```
[Owner 确认风险] → [创建草案] → [激活授权] → [消费授权]
   ①                ②            ③            ④
```

| 阶段 | 状态值 | 模型 | 触发 API | PG 写入 |
|------|--------|------|---------|---------|
| ① 风险确认 | N/A (确认记录) | `OwnerRiskAcknowledgement` | `POST /api/brc/admission/risk-ack` | 是 |
| ② 草案 | `pending_owner_live_authorization` | `BoundedLiveTrialAuthorizationDraft` | `POST /api/brc/admission/draft` | 是 |
| ③ 活跃授权 | `owner_live_authorized_pending_final_preflight` | `BoundedLiveTrialAuthorization` | `POST /api/brc/admission/activate` | 是 |
| ④ 已消费 | `consumed=True` | `BoundedLiveTrialAuthorization` | 仓库方法 | 是 |

### 6.2 状态转换条件

**① → ②**: `create_authorization_draft()` 要求:
- `linked_acknowledgement_id` 指向已存在的确认记录
- carrier 匹配
- 所有必需警告已确认

**② → ③**: `activate_live_authorization()` 要求:
- 草案状态 == `pending_owner_live_authorization`
- 未消费 (`consumed=False`)
- 未过期 (`expires_at_ms > now`)
- 草案无执行状态
- 该草案无现有授权

**③ → ④**: `mark_live_authorization_consumed()` 设置 `consumed=True`

### 6.3 范围匹配 (`_validate_draft_scope()`)

| 检查项 | 条件 |
|--------|------|
| symbol | 必须匹配 carrier.symbol 或 carrier.runtime_symbol |
| side | 必须匹配 carrier.side |
| max_notional | 不得超过 carrier.max_notional |
| quantity | 不得超过 carrier.quantity |
| leverage | 不得超过 carrier.max_leverage_allowed |
| protection_plan_type | 必须匹配 carrier.protection_plan_type |

### 6.4 关键特性验证

| 特性 | 支持程度 | 详情 |
|------|---------|------|
| 取消/作废未执行授权 | **NOT_FOUND** | 无 API 端点。生命周期仅: 创建 → 消费/过期。过期后需重新创建 |
| 阻止新授权 (有持仓/订单/未解决敞口) | **NOT_FOUND** — 授权层 | **SUPPORTED** — 执行层 (execute_signal 门检查) |
| 防止已消费授权显示为可执行 | **SUPPORTED** | `consumed` 布尔值 + BNB bridge 检查 `consumed`, `execution_intent_created`, `order_created` |
| 单次使用强制 | **SUPPORTED** | `single_use: Literal[True]` + `consumed` 检查 |
| 重复授权防止 | **SUPPORTED** | `activate_live_authorization()` 检查 `live_authorization_for_draft()` |
| 过期支持 | **PARTIAL** | `expires_at_ms` 字段存在但未在当前前端流中设置 |
| 关联到执行意图/订单/复盘 | **SUPPORTED** | `authorization_id` FK 在 execution_intents 和 protection_price_plans 中 |

### 6.5 所有授权对象强制属性

| 属性 | 值 | 含义 |
|------|-----|------|
| `live_ready` | `False` | 永不就绪 (结构性) |
| `order_permission_granted` | `False` | 永不授权下单 |
| `execution_permission_granted` | `False` | 永不授权执行 |
| `execution_intent_created` | `False` | 授权本身不创建意图 |
| `order_created` | `False` | 授权本身不创建订单 |
| `auto_execution_enabled` | `False` | 永不自动执行 |
| `metadata_only` / `non_live_metadata_only` | `True` | 仅为元数据记录 |
| `source` | `owner_console` | 来源固定 |

---

## Section 7 — Final Hard Gate Facts

### 7.1 执行门检查链 (`execute_signal()`, `execution_orchestrator.py`)

8 个严格顺序检查，任一失败立即阻止执行:

| # | 门 | 代码位置 | 条件 | 真相来源 | 阻止码 | 人类含义 | 阻止类型 |
|---|-----|---------|------|---------|--------|---------|---------|
| 1 | BRC 执行权限 | line 1071-1092 | `permission < ExecutionPermission.ORDER_ALLOWED` | 配置/环境 | `BRC_EXECUTION_PERMISSION_NOT_ORDER_ALLOWED` | "BRC 执行权限低于 order_allowed" | 硬阻止 |
| 2 | 启动交易守卫 | line 1116-1145 | `not startup_trading_guard.is_armed()` | 进程内存状态 | `STARTUP_TRADING_GUARD_NOT_ARMED` | "重启后新入场被阻止，需手动激活" | 硬阻止 |
| 3 | 全局终止开关 | line 1148-1174 | `global_kill_switch.is_active()` | PG 持久化 (fail-closed) | `KILL_SWITCH` | "全局新入场被阻止" | 硬阻止 |
| 4 | 保护健康阻止 | line 1177-1195 | `_protection_health_blocks.get(symbol)` 存在 | 内存集合 (来自 reconciliation) | `PROTECTION_HEALTH_BLOCK` 或具体码 | "该 symbol 存在保护健康问题" | 硬阻止 |
| 5 | 断路器 | line 1197-1210 | `symbol in _circuit_breaker_symbols` | 内存集合 (来自 recovery tasks) | `CIRCUIT_BREAKER` | "Symbol 因 recovery task 进入断路器" | 硬阻止 |
| 6 | 账户风险 | line 1212-1232 | `not account_risk.allowed_new_entry` | 交易所持仓/余额/清算价 | `ACCOUNT_RISK_NOT_HEALTHY` | "账户健康度降级/严重或余额不可用" | 硬阻止 |
| 7 | Campaign 状态 | line 1234-1254 | `not campaign_gate.allowed_new_entry` | Campaign 状态机 | 动态 | "Campaign 状态阻止新入场" | 硬阻止 |
| 8 | 资本保护 | line 1257-1281 | `not check_result.allowed` | 余额、日统计、最小名义值、精度 | 多个 (见下) | 各种资本保护违规 | 硬阻止 |

### 7.2 资本保护子检查 (`CapitalProtectionManager.pre_order_check()`)

| # | 检查 | 代码位置 | 阻止码 | 含义 |
|---|------|---------|--------|------|
| 1 | 日风险统计持久化可用 | line 243-256 | `DAILY_RISK_STATS_UNAVAILABLE` | 统计不可用 |
| 2 | 余额可获取 | line 258-264 | `CANNOT_GET_BALANCE` | 余额获取失败 |
| 3 | 价格可获取 | line 267-289 | `PRICE_UNAVAILABLE` | 无法获取价格 |
| 4 | 最小名义值 (qty*price >= 5 USDT) | line 291-306 | `BELOW_MIN_NOTIONAL` | 低于最小名义值 |
| 5 | 数量精度 | line 308-322 | `QUANTITY_PRECISION` | 数量精度不合规 |
| 6 | 价格合理性 (LIMIT: <=10% 偏差) | line 324-354 | `PRICE_UNREASONABLE` | 价格偏差过大 |
| 7 | 单笔交易损失 | line 356-374 | `SINGLE_TRADE_LOSS_LIMIT` | 超过单笔损失限制 |
| 8 | 仓位限制 | line 376-392 | `POSITION_LIMIT` | 超过仓位限制 |
| 9 | 日损失 | line 394-408 | `DAILY_LOSS_LIMIT` | 超过日损失限制 |
| 10 | 日交易次数 | line 410-426 | `DAILY_TRADE_COUNT_LIMIT` | 超过日交易次数 |
| 11 | 最小余额 | line 228-447 | `INSUFFICIENT_BALANCE` | 余额不足 |

### 7.3 ExecutionPermission 解析器 (`execution_permission.py`)

6 个贡献者取最小值:

| 贡献者 | 来源 | 默认值 |
|--------|------|--------|
| `configured_max_permission` | 环境变量 `BRC_EXECUTION_PERMISSION_MAX` | `READ_ONLY` |
| `api_key_capability` | 显式或 INTENT_RECORDING (未知时) | INTENT_RECORDING |
| `account_facts_permission` | 过期/不可用/不匹配/未知敞口 → 阻止 | 视情况 |
| `risk_capital_permission` | 不完整约束或缺失快照 → 阻止 | 视情况 |
| `runtime_safety_permission` | hard_locked/emergency_stopped → 阻止 | 视情况 |
| `operation_permission` | Operation 层 | 视情况 |

权限级别 (IntEnum): `READ_ONLY=0`, `SIGNAL_ONLY=1`, `INTENT_RECORDING=2`, `EXECUTION_INTENT_ALLOWED=3`, `ORDER_ALLOWED=4`

### 7.4 警告 vs 硬阻止

**所有门均为硬阻止** — 无"仅警告"门。每个失败的门都设置 `ExecutionIntentStatus.BLOCKED` 并返回。

### 7.5 前端可获取的门状态

| 门 | 前端可获取? | API |
|----|-----------|-----|
| GKS | 是 | `GET /api/runtime/safety` → `gks_active` |
| 启动守卫 | 是 | `GET /api/runtime/safety` → `startup_guard_armed` |
| 账户风险 | 是 | `GET /api/brc/account-facts` → `truth_level` |
| 保护健康 | 部分 | `GET /api/brc/account-facts` → `reconciliation_status` |
| 资本保护 | 部分 | dry-run bridge 可返回部分信息 |
| BRC 权限 | 不直接 | 需要从 readiness 响应推断 |
| 断路器 | 不直接 | 无专用端点 |
| Campaign 状态 | 是 | `GET /api/brc/readiness` → `runtime_state` |

---

## Section 8 — ExecutionIntent Lifecycle Facts

### 8.1 状态枚举

| 状态 | 含义 | 终态? | 可恢复? |
|------|------|-------|---------|
| `pending` | 等待执行 | 否 | 是 |
| `blocked` | 被门检查阻止 | **是** | 否 |
| `submitted` | 已提交到交易所 | 否 | 是 |
| `failed` | 提交失败 | **是** | 否 |
| `protecting` | 入场已成交，正在挂 TP/SL | 否 | 是 |
| `partially_protected` | 部分成交，已为已成交部分挂保护 | 否 | 是 |
| `completed` | 执行完成 (订单+保护) | **是** | 否 |

### 8.2 状态转换矩阵

```
PENDING → BLOCKED | FAILED | SUBMITTED | PROTECTING | COMPLETED
SUBMITTED → PROTECTING | PARTIALLY_PROTECTED | FAILED | COMPLETED
PROTECTING → FAILED | COMPLETED
PARTIALLY_PROTECTED → PROTECTING | FAILED | COMPLETED
BLOCKED → (终态)
FAILED → (终态)
COMPLETED → (终态)
```

允许同状态转换 (幂等)。

### 8.3 关键字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 意图标识符 |
| `signal_id` | str | 信号标识符 |
| `status` | ExecutionIntentStatus | 默认 PENDING |
| `order_id` | Optional[str] | 本地订单 ID |
| `exchange_order_id` | Optional[str] | 交易所订单 ID |
| `authorization_id` | Optional[str] | Owner 授权 ID |
| `blocked_reason` | Optional[str] | 阻止原因码 |
| `blocked_message` | Optional[str] | 人类描述 |
| `failed_reason` | Optional[str] | 失败原因 |
| `signal_payload` | JSONB | 原始信号载荷 |
| `strategy_payload` | JSONB | 冻结策略快照 (用于 TP/SL 生成) |

### 8.4 幂等性

- `_has_existing_protection_orders()` 防止重复保护订单挂载
- 部分成交处理器使用 `delta_qty = filled_qty_total - protected_qty_total` — 零增量则无操作
- 单 SL 约束强制 (line 1837-1843)

### 8.5 失败与重试

- SL 挂载失败触发 `_place_protection_order_with_single_retry()` (一次同步重试)
- 重试仍失败 → `_trigger_unprotected_recovery()`: 创建 PG recovery task + 触发断路器 + P0 告警
- `best_effort_restore_previous_sl()`: 替换 SL 失败时尝试重新挂载旧 SL

### 8.6 前端显示影响

| 意图状态 | 前端应显示 | 前端应允许的操作 |
|---------|----------|----------------|
| pending | "等待执行" | 无 (内部状态) |
| blocked | "被阻止" + blocked_message | 查看原因 |
| submitted | "提交中" | 无 |
| protecting | "挂保护中" | 无 |
| partially_protected | "部分保护" (警告) | 查看详情 |
| completed | "完成" | 查看复盘 |
| failed | "失败" + failed_reason | 查看原因 + 可能重试 |

---

## Section 9 — Order Lifecycle Facts

### 9.1 Order 模型字段

| 字段 | 类型 | 可空 | 默认 | 说明 |
|------|------|------|------|------|
| `id` | String(64) PK | 否 | - | 本地订单 ID (格式: `ord_{8hex}`) |
| `signal_id` | String(64) | 否 | - | 信号 ID |
| `exchange_order_id` | String(128) | 是 | - | 交易所订单 ID (UNIQUE partial index) |
| `symbol` | String(64) | 否 | - | 交易对 |
| `direction` | String(16) | 否 | - | LONG/SHORT |
| `order_type` | String(32) | 否 | - | MARKET/LIMIT/STOP_MARKET/STOP_LIMIT/TRAILING_STOP |
| `order_role` | String(16) | 否 | - | ENTRY/EXIT/TP1-TP5/SL |
| `status` | String(32) | 否 | PENDING | 见 OrderStatus 枚举 |
| `price` | Numeric(36,18) | 是 | - | 限价单价格 |
| `trigger_price` | Numeric(36,18) | 是 | - | 条件触发价 |
| `requested_qty` | Numeric(36,18) | 否 | - | 计划数量 |
| `filled_qty` | Numeric(36,18) | 否 | 0 | 已成交数量 |
| `average_exec_price` | Numeric(36,18) | 是 | - | 平均成交价 |
| `reduce_only` | Boolean | 否 | False | 减仓标志 |
| `exchange_reduce_only_param_sent` | Boolean | 是 | - | 是否发送了 reduceOnly 参数 |
| `exchange_reduce_only_omit_reason` | String(128) | 是 | - | 未发送 reduceOnly 的原因 |
| `parent_order_id` | String(64) | 是 | - | 父订单 (FK → orders.id) |
| `oco_group_id` | String(64) | 是 | - | OCO 组 ID |
| `exit_reason` | Text | 是 | - | INITIAL_SL/BREAKEVEN_STOP/TRAILING_PROFIT |
| `filled_at` | BIGINT | 是 | - | 成交时间戳 |
| `created_at` | BIGINT | 否 | _now_ms | 创建时间戳 |
| `updated_at` | BIGINT | 否 | _now_ms | 更新时间戳 |

### 9.2 OrderStatus 状态枚举

| 状态 | 含义 | 终态? | 前端显示 |
|------|------|-------|---------|
| CREATED | 本地创建 | 否 | "已创建" |
| SUBMITTED | 已发送到交易所 | 否 | "提交中" |
| PENDING | 未发送 (遗留) | 否 | "等待中" |
| OPEN | 交易所活跃 | 否 | "活跃" |
| PARTIALLY_FILLED | 部分成交 | 否 | "部分成交 {filled}/{requested}" |
| FILLED | 完全成交 | 是 | "已成交" |
| CANCELED | 已取消 | 是 | "已取消" |
| REJECTED | 交易所拒绝 | 是 | "已拒绝" + reason |
| EXPIRED | 交易所过期 | 是 | "已过期" |

### 9.3 状态转换矩阵

```
CREATED → SUBMITTED | CANCELED
SUBMITTED → OPEN | REJECTED | CANCELED | EXPIRED
PENDING → OPEN | REJECTED | CANCELED | SUBMITTED
OPEN → PARTIALLY_FILLED | FILLED | CANCELED | REJECTED | EXPIRED
PARTIALLY_FILLED → FILLED | CANCELED
FILLED, CANCELED, REJECTED, EXPIRED → (终态)
```

### 9.4 Reduce-Only 处理 (对冲模式)

- TP/SL 订单创建时 `reduce_only=True`
- 所有保护订单传递 `reduce_only=True` 给网关
- `execute_controlled_close()` 传递 `reduce_only=True`
- `exchange_reduce_only_param_sent` 和 `exchange_reduce_only_omit_reason` 追踪参数是否实际发送
- Binance 对冲模式: `positionSide` 参数 (LONG/SHORT) 与 `reduceOnly` 的交互

### 9.5 调和逻辑

| 场景 | 处理 |
|------|------|
| 终态订单收到更新 | 忽略 (line 815-843) |
| 过期更新 (低时间戳+低排名+低成交量) | 忽略 (line 845-862) |
| 退化更新 (低状态排名+低成交量) | 忽略 (line 864-879) |
| 未知订单更新 (本地行不存在) | 缓冲并重试 (最多 5 次，间隔 0.1s) |
| 交易所独有订单 | reconciliation 标记为 ORPHAN_ORDER |
| PG 独有订单 | reconciliation 标记为 GHOST_ORDER |

### 9.6 订单归因

| 归因维度 | 字段 | 值 |
|---------|------|-----|
| 订单角色 | `order_role` | ENTRY, EXIT, TP1-TP5, SL |
| 父订单 | `parent_order_id` | 保护订单 → 入场订单 |
| 退出原因 | `exit_reason` | INITIAL_SL, BREAKEVEN_STOP, TRAILING_PROFIT |
| 信号来源 | `signal_id` | 原始信号 |
| 审计触发源 | `triggered_by` | USER, SYSTEM, EXCHANGE |

---

## Section 10 — Protection / TP-SL Facts

### 10.1 保护链流程

```
入场订单成交 → 生成保护计划 → 提交 TP → 提交 SL → 确认 SL → 监控
                      ↓              ↓        ↓
                   预览计算      可能失败   可能失败
```

### 10.2 保护计划类型

当前仅支持 `single_tp_plus_sl`。

### 10.3 Protection Price Plan 表 (`brc_protection_price_plans`)

| 字段 | 说明 |
|------|------|
| `plan_id` | 计划 ID |
| `authorization_id` | 关联授权 |
| `carrier_id` | 关联 carrier |
| `symbol`, `side` | 交易对和方向 |
| `phase` | `pre_entry_reference` 或 `post_entry_fill` |
| `status` | `valid` 或 `blocked` |
| `reference_price` | 参考价格 |
| `fill_price` | 实际成交价 |
| `tp_price`, `sl_price` | 止盈止损价 |
| `tp_quantity`, `sl_quantity` | 止盈止损数量 |
| `tick_size`, `amount_step`, `min_amount`, `min_notional` | 交易所精度信息 |
| `blockers` | JSONB 阻止原因列表 |

### 10.4 Fill-Based 生成

- 保护订单在入场成交后动态生成，不预先创建
- 完整成交: `_protect_filled_entry()` → `_mount_protection_orders()` → 成功则 COMPLETED，失败则 FAILED
- 部分成交: `_handle_entry_partially_filled()` → 计算增量 → 仅对增量生成 TP → SL 覆盖全部已成交量

### 10.5 保护状态组合

| TP 状态 | SL 状态 | 整体保护状态 | 前端应显示 | 下一步 |
|---------|---------|-------------|----------|--------|
| 已接受 | 已接受 | 完全保护 | "已保护" | 监控 |
| 已接受 | 失败 | 部分保护 | "部分保护" (警告) | **恢复页面为主** |
| 失败 | 已接受 | 部分保护 | "部分保护" (警告) | 重试 TP |
| 失败 | 失败 | 未保护 | **"未保护" (危险)** | **恢复页面为主** |
| 待提交 | 待提交 | 保护中 | "保护中" | 等待 |
| N/A | N/A | 未知 | "保护状态未知" | 检查 |

### 10.6 SL 确认机制

SL 挂载后，`_confirm_sl_order_or_fail_safe()` 查询交易所确认 SL 订单确实存在。确认失败时:
1. Symbol 通过 `block_symbol_for_protection_health()` 阻止
2. 触发未保护 recovery task
3. SL 订单本地标记为 REJECTED

### 10.7 重试支持

| 场景 | 机制 |
|------|------|
| SL 挂载失败 | 单次同步重试 (`_place_protection_order_with_single_retry()`) |
| 替换 SL 失败 | 最佳努力恢复旧 SL (`_best_effort_restore_previous_sl()`) |
| 持久性失败 | PG recovery task (指数退避) |
| TP 失败 | 无自动重试 (需人工介入) |

### 10.8 Recovery 触发条件

`_trigger_unprotected_recovery()` 被调用当:
1. SL 挂载失败且单次重试也失败
2. SL 挂载抛异常且重试失败
3. SL 已挂载但在交易所未确认
4. 替换过程中旧 SL 取消失败

动作:
1. 创建 PG recovery task
2. Symbol 加入断路器集合
3. 发送 P0 告警通知

### 10.9 Binance 对冲模式载荷治理

| 项目 | 事实 |
|------|------|
| positionSide | `LONG`/`SHORT` 通过 `_position_side_for_authorization()` 确定 |
| reduceOnly | TP/SL 订单传递 `reduce_only=True` 给网关 |
| exchange_reduce_only_param_sent | 追踪是否实际发送 |
| exchange_reduce_only_omit_reason | 追踪未发送原因 (对冲模式下可能被省略) |
| 审计字段 | `exchange_reduce_only_param_sent`, `exchange_reduce_only_omit_reason` 在 orders 表中 |

### 10.10 前端保护状态显示影响

| 前端需区分 | 代码支持 |
|-----------|---------|
| 保护预览 vs 实际交易所保护订单 | `brc_protection_price_plans` (phase=pre_entry_reference vs post_entry_fill) |
| 已保护/部分保护/未保护/未知 | intent.status + protection_price_plans.status |
| 何时恢复页面应为主操作 | protection_health_blocks 存在时 |

---

## Section 11 — Account Facts / Reconciliation Facts

### 11.1 支持清单

| 功能 | 支持程度 | API |
|------|---------|-----|
| 全账户持仓 | SUPPORTED | `GET /api/brc/account-facts` → `positions` |
| 全交易所挂单 | SUPPORTED | `GET /api/brc/account-facts` → `open_orders` |
| 条件/算法订单 | PARTIAL | `GET /api/brc/account-facts` 可能包含，取决于交易所响应 |
| 钱包权益 | SUPPORTED | `GET /api/brc/account-facts` → `account_summary` |
| 可用保证金 | SUPPORTED | `GET /api/brc/account-facts` → `account_summary` |
| 账户 profile/environment | SUPPORTED | `GET /api/runtime/safety` → `profile`, `testnet` |
| 数据新鲜度时间戳 | PARTIAL | `GET /api/brc/account-facts` → `source` + `truth_level`，但无精确 `fetched_at` |
| 过期/未知状态 | PARTIAL | `truth_level` 可表示，但语义不明确 |
| PG 订单/意图 | SUPPORTED | `GET /api/brc/account-facts` → `reconciliation_status` |
| PG vs Exchange 不匹配 | SUPPORTED | reconciliation read model: `GHOST_ORDER`, `ORPHAN_ORDER`, `POSITION_MISMATCH` |
| 调和状态 | SUPPORTED | `GET /api/brc/account-facts` → `reconciliation_status` |
| 未解决敞口 | PARTIAL | 从 positions + open_orders 推断，但无专用字段 |
| 外部/手动订单 | PARTIAL | reconciliation 可检测 ORPHAN_ORDER，但无归因 |
| 订单归因 (当前行动/旧行动/手动/未知) | NOT_FOUND | 无归因字段 |

### 11.2 Account Facts Source / Truth Level

| Source 枚举 | 含义 |
|------------|------|
| `backend_api` | 直接从后端 API 获取 |
| `derived_from_backend` | 从后端数据推导 |
| `exchange` | 直接从交易所获取 |

| Truth Level 枚举 | 含义 |
|-----------------|------|
| `real_time` | 实时数据 |
| `recent` | 最近数据 (可能略过期) |
| `stale` | 过期数据 |
| `unavailable` | 数据不可用 |
| `unknown` | 未知 |

### 11.3 调和不匹配类型

| 类型 | 含义 | 解决动作 |
|------|------|---------|
| `GHOST_ORDER` | PG 有但交易所无 | MARK_CANCELLED |
| `ORPHAN_ORDER` | 交易所有但 PG 无 | IMPORTED_TO_DB 或 CANCEL_ORDER |
| `POSITION_MISMATCH` | 仓位大小不一致 | SYNC_POSITION |

### 11.4 保护健康检测原因码

| 原因码 | 严重性 | 动作 |
|--------|--------|------|
| `PROTECTION_MISSING_EXCHANGE_SL` | CRITICAL | 阻止新入场 |
| `PROTECTION_EXCHANGE_POSITION_UNTRACKED` | CRITICAL | 阻止新入场 |
| `PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE` | CRITICAL | 阻止新入场 |
| `PROTECTION_ORPHAN_REDUCE_ONLY_ORDER` | non-CRITICAL | 仅报告 |
| `DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE` | non-CRITICAL | 仅报告 |
| `POSITION_CLOSED_ON_EXCHANGE_NOT_PROJECTED` | CRITICAL | 阻止新入场 |
| `PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE` | CRITICAL | 阻止新入场 |

### 11.5 前端处理未知/过期数据

| 情况 | 前端应 |
|------|--------|
| `truth_level: stale` | 显示警告标记，禁用执行操作 |
| `truth_level: unavailable` | 显示 "数据未接入"，禁用所有操作 |
| `reconciliation_status: mismatch` | 显示不匹配详情，优先引导到恢复页面 |
| 交易所连接失败 | 显示连接状态，标记所有交易所数据为不可信 |

---

## Section 12 — Recovery / Exception Action Facts

| 行为 | API 端点 | 服务方法 | 类型 | 安全守卫 | 需 Owner 确认? | 适合前端按钮? | 响应 | 差距 |
|------|---------|---------|------|---------|---------------|-------------|------|------|
| 刷新账户事实 | `GET /api/brc/account-facts` | 无 (只读刷新) | 只读 | session | 否 | 是 | 事实快照 | 无 |
| 运行调和 | 无专用端点 | `reconciliation.build_read_model()` | 只读 | 内部 | 否 | 需新端点 | 调和报告 | **需要新 API** |
| 取消过期挂单 | 无前端端点 | `exchange_gateway.cancel_order()` | 交易所取消 | 8+ 门 | 是 | **需要新 API + 确认** | 取消结果 | **需要新 API** |
| 取消保护订单 | 无前端端点 | `exchange_gateway.cancel_order()` | 交易所取消 | 8+ 门 | 是 | **需要新 API + 确认** | 取消结果 | **需要新 API** |
| 平仓 (scoped position) | 无前端端点 | `execute_controlled_close()` | 交易所下单 (reduce-only) | 8+ 门 | 是 | **需要新 API + 确认** | 关闭结果 | **需要新 API** |
| 重试缺失 TP/SL | 无前端端点 | `_mount_protection_orders()` | 交易所下单 | 保护链 | 是 | **需要新 API + 确认** | 挂载结果 | **需要新 API** |
| 作废未执行授权 | **NOT_FOUND** | **NOT_FOUND** | N/A | N/A | N/A | **不可用** | N/A | **需要新功能** |
| 标记人工复审 | **NOT_FOUND** | **NOT_FOUND** | N/A | N/A | N/A | **不可用** | N/A | **需要新功能** |
| 关闭/过期执行意图 | **NOT_FOUND** | **NOT_FOUND** | N/A | N/A | N/A | **不可用** | N/A | **需要新功能** |
| 清理过期草案 | **NOT_FOUND** | **NOT_FOUND** | N/A | N/A | N/A | **不可用** | N/A | **需要新功能** |
| 阻止新授权 (有未解决敞口) | **PARTIAL** — 执行层有检查 | `execute_signal()` 门检查 | 门检查 | 自动 | 否 | 是 (显示阻止状态) | 阻止原因 | 授权层无显式检查 |

### 12.1 恢复操作分类

| 分类 | 包含操作 |
|------|---------|
| 只读 | 刷新账户事实 |
| 仅 PG | (当前无) |
| 交易所取消 | 取消挂单、取消保护订单 |
| 交易所下单 | 平仓、重试 TP/SL |
| 需要新功能 | 作废授权、标记复审、关闭意图、清理草案 |

---

## Section 13 — Review / PnL Facts

| 字段 | 支持程度 | 来源 |
|------|---------|------|
| 入场价格 | SUPPORTED | `order.average_exec_price` |
| 出场价格 | SUPPORTED | exit order `average_exec_price` |
| 已成交数量 | SUPPORTED | `order.filled_qty` |
| 手续费 | SUPPORTED | `order.close_fee`, `position.total_fees_paid` |
| 资金费率 | SUPPORTED | `position.total_funding_paid` |
| 滑点 | DERIVABLE | `average_exec_price` vs `price` (LIMIT) 或 `trigger_price` (STOP) |
| 已实现 PnL | SUPPORTED | `position.realized_pnl`, `order.close_pnl` |
| MFE/MAE | NOT_FOUND | 无字段，需 tick 级数据 |
| 最终仓位 | SUPPORTED | `position` 表 (is_closed, quantity) |
| 最终挂单 | SUPPORTED | `order` 表 (status != terminal) |
| TP/SL 结果 | SUPPORTED | TP/SL 订单 status |
| 恢复结果 | PARTIAL | `execution_recovery_tasks` status |
| 失败原因 | SUPPORTED | `intent.failed_reason`, `intent.blocked_reason` |
| 根因 | PARTIAL | 从 blocker codes 和 audit log 推断 |
| 人工干预 | NOT_FOUND | 无字段 |
| 问题已治理/已修复 | NOT_FOUND | 无字段 |
| 关联到授权/意图/订单 | SUPPORTED | `authorization_id`, `signal_id`, `parent_order_id` |

### 13.1 PnL 计算链

```
Entry Order (filled) → Position (realized_pnl, total_fees_paid, total_funding_paid)
Exit Order (filled) → order.close_pnl, order.close_fee
Daily Stats → daily_risk_stats_aggregates (realized_pnl, trade_count)
Capital Protection → record_projected_realized_pnl_delta(), record_closed_trade()
```

### 13.2 复盘数据分类

| 分类 | 字段 |
|------|------|
| SUPPORTED | entry_price, exit_price, filled_qty, fees, funding, realized_pnl, TP/SL result, position, open_orders, failure_reason, authorization_link |
| PARTIAL | slippage (可推导), recovery_result, root_cause |
| NOT_FOUND | MFE/MAE, manual_intervention, issue_governed_fixed |
| DERIVABLE_FROM_EXISTING_DATA | slippage |
| SHOULD_NOT_BE_FRONTEND_DERIVED | realized_pnl (应使用 position.realized_pnl) |

---

## Section 14 — Audit / Trace Facts

### 14.1 审计数据来源

| 来源 | 表 | 格式 |
|------|-----|------|
| 订单审计 | `order_audit_logs` | 结构化 (PG) |
| 授权审计 | `brc_admission_audit_log` | 结构化 (PG) |
| 决策追踪 | `TraceSink` | JSONL 文件 |
| Operation 审计 | `brc_operations` + `brc_preflight_snapshots` + `brc_execution_results` | 结构化 (PG) |
| Campaign 事件 | `brc_campaign_events` | 结构化 (PG) |

### 14.2 追踪事件字段

| 字段 | 说明 |
|------|------|
| `trace_id` | UUID |
| `lifecycle_id` | e.g., `intent:{id}`, `control:startup_trading_guard` |
| `event_type` | e.g., `risk.pre_order_check`, `risk.global_kill_switch_check` |
| `decision` | `allow` 或 `deny` |
| `reason` | 人类可读原因 |
| `metadata` | 附加数据 |
| `config_hash` | 配置哈希 |
| `emitted_at_ms` | 时间戳 |

### 14.3 审计查询能力

| 查询维度 | 支持程度 | 来源 |
|---------|---------|------|
| 按 authorization_id | SUPPORTED | `execution_intents.authorization_id` + `brc_protection_price_plans.authorization_id` |
| 按 execution_intent_id | SUPPORTED | `execution_intents.id` + `execution_recovery_tasks.intent_id` |
| 按 exchange_order_id | SUPPORTED | `orders.exchange_order_id` (UNIQUE partial index) |
| 按 client_order_id | NOT_FOUND | 无 client_order_id 字段 |
| 按 carrier_id | PARTIAL | `brc_scoped_runtime_safety_clearances.carrier_id`, `brc_protection_price_plans.carrier_id` |
| 按 symbol | SUPPORTED | `orders.symbol`, `positions.symbol`, `execution_intents.symbol` |
| 按时间范围 | SUPPORTED | `created_at`, `updated_at`, `emitted_at_ms` |
| 按 gate_code | PARTIAL | `execution_intents.blocked_reason`, `brc_preflight_snapshots.blockers` |
| 按 blocker_code | PARTIAL | 同上 |
| 按 status | SUPPORTED | 各表 status 字段 |
| 敏感字段排除 | SUPPORTED | 凭证不在审计日志中 |

### 14.4 订单审计事件类型

| 事件类型 | 触发源 |
|---------|--------|
| ORDER_CREATED | SYSTEM |
| ORDER_SUBMITTED | SYSTEM |
| ORDER_CONFIRMED | EXCHANGE |
| ORDER_PARTIAL_FILLED | EXCHANGE |
| ORDER_FILLED | EXCHANGE |
| ORDER_CANCELED | USER/SYSTEM/EXCHANGE |
| ORDER_REJECTED | EXCHANGE |
| ORDER_EXPIRED | EXCHANGE |
| ORDER_UPDATED | EXCHANGE |

---

## Section 15 — Status Enum Catalog

### 15.1 Order Status

| 值 | 含义 | 终态? | 可恢复? | 严重性 | 允许下一步 | 前端注释 |
|----|------|-------|---------|--------|----------|---------|
| CREATED | 本地创建 | 否 | 是 | info | SUBMITTED, CANCELED | 内部状态 |
| SUBMITTED | 已发送交易所 | 否 | 是 | info | OPEN, REJECTED, CANCELED, EXPIRED | 显示 "提交中" |
| PENDING | 未发送 (遗留) | 否 | 是 | info | OPEN, REJECTED, CANCELED, SUBMITTED | 显示 "等待" |
| OPEN | 交易所活跃 | 否 | 是 | info | PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED | 显示 "活跃" |
| PARTIALLY_FILLED | 部分成交 | 否 | 是 | warning | FILLED, CANCELED | 显示成交进度 |
| FILLED | 完全成交 | 是 | 否 | info | 无 | 显示 "已成交" |
| CANCELED | 已取消 | 是 | 否 | info | 无 | 显示 "已取消" |
| REJECTED | 交易所拒绝 | 是 | 否 | error | 无 | 显示 "已拒绝" + 原因 |
| EXPIRED | 已过期 | 是 | 否 | warning | 无 | 显示 "已过期" |

### 15.2 ExecutionIntent Status

| 值 | 含义 | 终态? | 严重性 | 前端注释 |
|----|------|-------|--------|---------|
| pending | 等待执行 | 否 | info | - |
| blocked | 被阻止 | 是 | warning | 显示阻止原因 |
| submitted | 已提交 | 否 | info | - |
| failed | 失败 | 是 | error | 显示错误 |
| protecting | 挂保护中 | 否 | info | - |
| partially_protected | 部分保护 | 否 | warning | - |
| completed | 完成 | 是 | info | - |

### 15.3 Recovery Task Status

| 值 | 含义 | 终态? | 严重性 |
|----|------|-------|--------|
| pending | 等待重试 | 否 | info |
| retrying | 重试中 | 否 | info |
| resolved | 已恢复 | 是 | info |
| failed | 恢复失败 | 是 | error — 需人工介入 |

### 15.4 BRC Campaign Status

| 值 | 含义 | 终态? | 严重性 | 允许下一步 |
|----|------|-------|--------|----------|
| observe | 仅监控 | 否 | info | active |
| active | 交易活跃 | 否 | info | profit_protect, loss_locked, ended |
| profit_protect | 利润保护模式 | 否 | warning | ended |
| loss_locked | 损失锁定 | 否 | error | ended |
| ended | Campaign 结束 | 是 | info | 无 |

### 15.5 Runtime Campaign Status

| 值 | 含义 | 终态? | 严重性 |
|----|------|-------|--------|
| observe | 监控 | 否 | info |
| armed | 就绪 | 否 | info |
| paused | 暂停 | 否 | info |
| profit_protect | 利润保护 | 否 | warning |
| loss_locked | 损失锁定 | 否 | error |
| hard_locked | 硬锁定 | 否 | error |
| closed | 关闭 | 是 | info |

### 15.6 Operation Status

| 值 | 含义 | 终态? | 严重性 |
|----|------|-------|--------|
| draft | 草案 | 否 | info |
| awaiting_confirmation | 等待确认 | 否 | info |
| executing | 执行中 | 否 | info |
| executed | 已执行 | 是 | info |
| blocked | 被阻止 | 是 | warning |
| failed | 失败 | 是 | error |
| cancelled | 已取消 | 是 | info |
| expired | 已过期 | 是 | warning |
| noop | 无操作 | 是 | info |

### 15.7 Preflight Decision

| 值 | 含义 | 严重性 |
|----|------|--------|
| allow | 安全继续 | info |
| warn | 谨慎继续 | warning |
| block | 无法继续 | error |
| unavailable | 无法评估 | error |
| expired | 快照过期 | warning |

### 15.8 Clearance Status

| 值 | 含义 | 终态? | 严重性 |
|----|------|-------|--------|
| active | 有效 | 否 | info |
| revoked | 已撤销 | 是 | warning |
| expired | 已过期 | 是 | info |

### 15.9 Admission / Strategy Family Status

| 领域 | 值 | 终态? |
|------|-----|-------|
| StrategyFamilyStatus (admission) | active, intake, parked, rejected | rejected 终态 |
| StrategyFamilyStatus (registry) | registered_hypothesis_only, active_observation_candidate, live_readonly_observation, parked, retired | retired 终态 |
| AdmissionDecision | admit, admit_with_constraints, reject, park | 大部分终态 |
| TrialConstraintStatus | pending_risk_capital_resolution, installable, installed, expired, invalidated | installed/expired/invalidated 终态 |
| AdmissionTrialBindingStatus | planned, binding_reserved, cancelled, expired, invalidated, campaign_created, runtime_constraints_installed, runtime_installed | 大部分终态 |

### 15.10 GKS / Startup Guard

| 领域 | 值 | 含义 | 严重性 |
|------|-----|------|--------|
| GKS active | true | 全局终止 — 所有新入场被阻止 | critical |
| GKS active | false | 正常运行 | info |
| Startup Guard armed | false | 重启后未激活 — 新入场被阻止 | blocker |
| Startup Guard armed | true | 已激活 — 可继续 | info |

---

## Section 16 — Execution Chain Branch Matrix

| 阶段 | 成功分支 | 失败分支 | 部分分支 | 未知/过期分支 | 前端所需状态 | 下一步动作 | 代码/API 支持 | 缺失支持 |
|------|---------|---------|---------|-------------|------------|----------|-------------|---------|
| Carrier 选择 | 选定 carrier | 无可用 carrier | - | carrier 数据过期 | 候选列表 + 选中状态 | 进入授权流 | `admission/current` | Carrier Shelf API |
| 风险确认 | 确认记录创建 | 创建失败 | - | - | 确认状态 | 创建草案 | `admission/risk-ack` | 无 |
| 授权草案 | 草案创建 | 验证失败 (范围不匹配) | - | 草案过期 | 草案状态 | 激活授权 | `admission/draft` | 取消草案 API |
| 活跃授权 | 授权激活 | 激活失败 (已消费/过期/已有) | - | 授权过期 | 授权状态 + hard_blockers | 最终门检查 | `admission/activate` | 作废授权 API |
| 最终门 | 全部通过 | 任一门阻止 | 部分门警告 | 门状态未知 | 门状态表 (8+ 行) | 执行意图 | `execution-bridge/dry-run` | 门状态实时 API |
| 执行意图 | 意图创建 (PENDING) | 被门阻止 (BLOCKED) | - | - | 意图状态 | 入场订单 | `execute_signal()` | 前端无直接触发 |
| 入场订单 | 订单创建 | 资本保护拒绝 | - | 订单状态未知 | 订单状态 | 等待成交 | 内部 | 无 |
| 入场成交 | 完全成交 | 被拒绝 | 部分成交 | 交易所未知 | 订单状态 + filled_qty | 保护计划 | 内部 | 无 |
| 保护计划 | 计划生成 | 生成失败 | - | - | 计划详情 | TP/SL 提交 | 内部 | 无 |
| TP/SL 提交 | 两者均接受 | 两者均失败 | 一个成功一个失败 | 提交状态未知 | 保护状态 | 监控/恢复 | 内部 | 前端需区分保护状态 |
| 保护监控 | 正常运行 | SL 未确认 | 部分保护 | 状态未知 | 保护健康 | 继续/恢复 | `protection_health_monitor` | 前端保护健康 API |
| 恢复 | 恢复成功 | 恢复失败 | 部分恢复 | 恢复状态未知 | recovery task 状态 | 人工介入 | `execution_recovery_tasks` | 前端恢复操作 API |
| 复盘 | 记录完成 | 记录失败 | - | - | 复盘数据 | 查看详情 | `review_decisions` | 真实 PnL 复盘 |
| 审计 | 记录完成 | - | - | - | 审计轨迹 | 技术审查 | `order_audit_logs`, `admission_audit_log` | 审计查询 API |

---

## Section 17 — Future 交易控制台 Page-to-Fact Matrix

### 17.1 Dashboard / 首页

| 项目 | 详情 |
|------|------|
| 产品目的 | 一眼看到当前状态: 安全吗? 有持仓吗? 有授权吗? 下一步是什么? |
| 需要的事实 | GKS 状态, 启动守卫, 账户风险, 当前持仓, 当前挂单, 活跃授权, 保护健康, campaign 状态, 环境模式 |
| 现有 API | `GET /api/runtime/safety`, `GET /api/brc/readiness`, `GET /api/brc/account-facts` |
| 缺失 API | 聚合 dashboard API (当前需要多次调用) |
| 现有字段 | 大部分存在 |
| 缺失字段 | 聚合视图, 数据新鲜度精确时间戳 |
| 支持的操作 | 查看, 手动刷新 |
| 不支持的操作 | 无 |
| 安全风险 | 无 (只读) |
| 可实现? | **部分** — 需要新聚合 API 或前端多次调用 |

### 17.2 Carrier Shelf

| 项目 | 详情 |
|------|------|
| 产品目的 | 展示所有可用 carrier，每个的状态、配置、阻止原因 |
| 需要的事实 | carrier 列表, 每个 carrier 的配置 (symbol/side/cap/leverage/protection), 可用性状态, 阻止原因 |
| 现有 API | `GET /api/brc/admission/current` (单个 carrier), `GET /api/brc/carriers/second-expansion/bootstrap` |
| 缺失 API | **Carrier 列表 API**, carrier 详细状态 API |
| 现有字段 | carrier 配置字段存在于 draft/authorization |
| 缺失字段 | carrier 可用性计算, carrier 历史表现 |
| 支持的操作 | 查看当前 carrier |
| 不支持的操作 | 选择 carrier, 查看 carrier 历史 |
| 安全风险 | 无 |
| 可实现? | **阻塞** — 需要新 Carrier API |

### 17.3 Authorization / 有界实盘授权

| 项目 | 详情 |
|------|------|
| 产品目的 | 风险确认 → 草案 → 授权 → 消费的完整生命周期管理 |
| 需要的事实 | 授权链状态, 风险确认, 草案, 活跃授权, hard_blockers, 消费状态 |
| 现有 API | `GET /api/brc/admission/current`, `POST /api/brc/admission/risk-ack`, `POST /api/brc/admission/draft`, `POST /api/brc/admission/activate` |
| 缺失 API | 取消/作废授权, 阻止新授权 (有未解决敞口) |
| 现有字段 | 大部分授权字段 |
| 缺失字段 | 授权 TTL 管理, 显式 cancel/void |
| 支持的操作 | 创建确认, 创建草案, 激活授权 |
| 不支持的操作 | 取消授权, 作废草案 |
| 安全风险 | **高** — 执行按钮可触发真实交易所操作 |
| 可实现? | **部分** — 核心流程支持，取消/作废缺失 |

### 17.4 Execution Control / 实盘执行控制

| 项目 | 详情 |
|------|------|
| 产品目的 | 执行前门检查展示, 执行触发, 执行状态追踪 |
| 需要的事实 | 8+ 门状态, 执行意图状态, 入场订单状态, 保护订单状态 |
| 现有 API | `POST /api/brc/execution-bridge/dry-run` |
| 缺失 API | 门状态实时查询 API, 执行触发 API (前端), 执行状态追踪 API |
| 现有字段 | dry-run 返回部分门状态 |
| 缺失字段 | 每个门的独立状态, 实时门更新 |
| 支持的操作 | dry-run 门检查 |
| 不支持的操作 | 前端直接触发执行, 实时状态追踪 |
| 安全风险 | **极高** — 执行触发涉及真实交易所 |
| 可实现? | **部分** — 门检查 dry-run 支持，执行触发和追踪缺失 |

### 17.5 Account & Orders / 账户与订单

| 项目 | 详情 |
|------|------|
| 产品目的 | 全账户视图: 持仓, 挂单, 账户余额, 调和状态 |
| 需要的事实 | positions, open_orders, account_summary, reconciliation_status |
| 现有 API | `GET /api/brc/account-facts` |
| 缺失 API | 无 (现有 API 基本够用) |
| 现有字段 | 大部分 |
| 缺失字段 | 订单归因 (当前行动/旧行动/手动), 数据新鲜度精确时间 |
| 支持的操作 | 查看 |
| 不支持的操作 | 取消订单, 平仓 |
| 安全风险 | 低 (只读) |
| 可实现? | **可以** — 现有 API 支持 |

### 17.6 Recovery & Exception / 异常恢复

| 项目 | 详情 |
|------|------|
| 产品目的 | 异常检测, 恢复操作, 保护健康, 调和不匹配处理 |
| 需要的事实 | protection_health_blocks, recovery_tasks, reconciliation_mismatches, 断路器状态 |
| 现有 API | `GET /api/brc/account-facts` (reconciliation_status) |
| 缺失 API | **恢复操作 API** (取消订单, 重试保护, 平仓), 保护健康查询 API, 断路器状态 API |
| 现有字段 | reconciliation_status, recovery_tasks (PG) |
| 缺失字段 | 保护健康详情, 断路器状态 |
| 支持的操作 | 查看调和状态 |
| 不支持的操作 | 取消订单, 重试保护, 平仓, 作废授权 |
| 安全风险 | **高** — 恢复操作涉及交易所 |
| 可实现? | **阻塞** — 几乎所有恢复操作 API 缺失 |

### 17.7 Review / 实盘复盘

| 项目 | 详情 |
|------|------|
| 产品目的 | 执行结果查看, PnL 分析, 失败原因, 保护结果 |
| 需要的事实 | entry/exit prices, PnL, fees, TP/SL results, failure reasons, recovery results |
| 现有 API | `GET /api/brc/review-decisions` |
| 缺失 API | 聚合复盘 API (从 orders + positions + intents 构建) |
| 现有字段 | 分散在 orders, positions, intents, recovery_tasks |
| 缺失字段 | MFE/MAE, 人工干预标记, 问题治理标记 |
| 支持的操作 | 查看 review decisions |
| 不支持的操作 | 标记人工干预, 标记问题已治理 |
| 安全风险 | 低 (只读) |
| 可实现? | **部分** — 数据分散但可聚合 |

### 17.8 Technical Audit / 技术审计

| 项目 | 详情 |
|------|------|
| 产品目的 | 技术级审计轨迹, 门决策追踪, 载荷审计, 时间线重建 |
| 需要的事实 | order_audit_logs, admission_audit_log, decision_trace, preflight_snapshots |
| 现有 API | `GET /api/brc/audit-trail`, `GET /api/brc/audit-writable` |
| 缺失 API | 按维度查询审计 API (authorization_id, intent_id, carrier_id 等) |
| 现有字段 | 分散在多个审计表 |
| 缺失字段 | 聚合查询, 维度过滤 |
| 支持的操作 | 查看 timeline |
| 不支持的操作 | 维度过滤查询 |
| 安全风险 | 低 (只读) |
| 可实现? | **部分** — 基础审计支持，高级查询缺失 |

---

## Section 18 — Safety Risk Findings

| # | 风险 | 严重性 | 详情 |
|---|------|--------|------|
| 1 | 执行按钮可触及交易所 | **CRITICAL** | `executeOwnerTrialAuthorization()` 可通过 Operation Layer 间接触发真实交易所下单。虽然有多重门，但前端无确认对话框、无 TOTP 二次验证 |
| 2 | 恢复操作 API 完全缺失 | **HIGH** | 取消订单、重试保护、平仓等恢复操作无前端可用 API。异常发生时 Owner 无法从控制台恢复 |
| 3 | 授权不可取消/作废 | **HIGH** | 已创建的授权草案和活跃授权无法通过 API 取消。过期是唯一终止途径 |
| 4 | 4/5 策略候选为 sample_data | **MEDIUM** | StrategyCandidatesV2 中 4 个候选为硬编码示例数据，与真实后端数据在同一 UI 中展示 |
| 5 | 无自动数据刷新 | **MEDIUM** | 仅手动刷新按钮，无 WebSocket/SSE/轮询。过期数据可能长时间不被发现 |
| 6 | 门状态无实时前端 API | **MEDIUM** | 8+ 门检查仅在 dry-run 时返回，无独立实时查询端点 |
| 7 | 数据新鲜度不精确 | **MEDIUM** | `truth_level` 枚举粗粒度，无精确 `fetched_at` 时间戳 |
| 8 | 无 TOTP 重验证 | **MEDIUM** | 危险操作前无二次认证。仅登录时验证 TOTP |
| 9 | Carrier 不是 PG 实体 | **LOW** | Carrier 作为概念对象但无独立存储和查询能力，限制 Carrier Shelf 功能 |
| 10 | MFE/MAE 不支持 | **LOW** | 需要 tick 级数据，当前架构不支持 |

---

## Section 19 — Final Summary

### SUPPORTED NOW

| 能力 | API |
|------|-----|
| Owner 认证 (密码+TOTP) | `POST /api/auth/login` |
| 会话管理 | `GET /api/auth/session`, `POST /api/auth/logout` |
| 安全状态概览 | `GET /api/runtime/safety` |
| 就绪状态 + 行动卡 | `GET /api/brc/readiness` |
| 账户事实 (持仓/订单/余额) | `GET /api/brc/account-facts` |
| 授权生命周期 (确认→草案→激活) | `POST /api/brc/admission/{risk-ack,draft,activate}` |
| 授权当前状态 | `GET /api/brc/admission/current` |
| 执行门 dry-run | `POST /api/brc/execution-bridge/dry-run` |
| 策略家族 CRUD | `GET/POST /api/brc/strategy-families` |
| 审计轨迹基础 | `GET /api/brc/audit-trail` |
| Operation preflight→confirm 链 | `POST /api/brc/operations/{preflight,confirm}` |
| 全局终止开关 (PG 持久化) | `global_kill_switch` 服务 |
| 启动交易守卫 | `startup_trading_guard` 服务 |
| 订单审计日志 | `order_audit_logs` 表 |
| 决策追踪 | `TraceSink` (JSONL) |

### SUPPORTED BUT NEEDS FRONTEND REMAPPING

| 能力 | 当前位置 | 需要 |
|------|---------|------|
| Campaign 状态 | `GET /api/brc/readiness` → `runtime_state` | 独立显示组件 |
| 环境模式 | `GET /api/runtime/safety` → `profile`, `testnet` | 持久指示器 |
| 保护计划预览 | dry-run bridge → `execution_plan_preview` | 独立保护预览面板 |
| 调和状态 | `GET /api/brc/account-facts` → `reconciliation_status` | 独立调和面板 |
| 订单列表 | `GET /api/brc/account-facts` → `open_orders` | 独立订单表 |
| 持仓列表 | `GET /api/brc/account-facts` → `positions` | 独立持仓表 |

### PARTIAL / NEEDS API GAP FILL

| 能力 | 缺失 | 需要 |
|------|------|------|
| Carrier Shelf | 无 carrier 列表 API | 新 carrier 端点 |
| 门状态实时查询 | 仅 dry-run 返回 | 独立门状态端点 |
| 数据新鲜度 | `truth_level` 粗粒度 | 精确 `fetched_at` 时间戳 |
| 审计维度查询 | 仅 timeline | 按 authorization_id, intent_id, carrier_id 查询 |
| 复盘聚合 | 数据分散 | 聚合复盘 API |
| 订单归因 | 无归因字段 | attribution 字段 |

### NOT SUPPORTED

| 能力 | 影响 |
|------|------|
| 取消/作废未执行授权 | Owner 无法终止已创建的授权 |
| 恢复操作 API (取消订单/重试保护/平仓) | 异常发生时 Owner 无法从控制台恢复 |
| 标记人工复审 | 无工作流标记 |
| 关闭/过期执行意图 | 意图可能永久停留在中间状态 |
| 清理过期草案 | 过期草案无清理机制 |
| MFE/MAE | 无法评估入场质量 |
| 人工干预标记 | 无法记录人工介入 |
| 问题治理标记 | 无法跟踪问题修复 |
| 自动数据刷新 | 数据可能长时间过期 |
| TOTP 重验证 | 危险操作无二次认证 |
| 确认对话框 | 无模态确认机制 |

### SAFETY RISKS

| 风险 | 严重性 | 建议 |
|------|--------|------|
| 执行按钮可触及真实交易所 | CRITICAL | 添加确认对话框 + TOTP 重验证 |
| 恢复操作 API 缺失 | HIGH | 实现恢复操作 API |
| 授权不可取消 | HIGH | 实现 cancel/void API |
| Sample data 混入策略候选 | MEDIUM | 移除或明确标注 |
| 无自动数据刷新 | MEDIUM | 添加 WebSocket/SSE |
| 门状态非实时 | MEDIUM | 添加门状态端点 |
| 无 TOTP 重验证 | MEDIUM | 危险操作前二次认证 |

### QUESTIONS FOR PRODUCT OWNER

1. 交易控制台是否需要支持取消/作废已创建但未执行的授权?
2. 恢复操作 (取消订单、重试保护、平仓) 是否应从控制台触发，还是有其他恢复流程?
3. 执行触发前是否需要 TOTP 二次验证?
4. Carrier 是从代码配置定义还是需要 PG 持久化?
5. 数据刷新策略: 手动刷新、自动轮询、还是 WebSocket 推送?
6. MFE/MAE 是否是交易控制台的必要功能?
7. 策略候选是否应全部来自后端 API，还是允许前端示例数据?
8. 交易控制台是否需要管理员角色区分?

### QUESTIONS FOR CHATGPT PRODUCT CONTROLLER

1. `api_console_runtime.py` (40+ 端点) 和 `api_v1_config.py` (35+ 端点) 是否应挂载到主 API? 哪些端点对交易控制台有价值?
2. Carrier 作为概念对象不存储在 PG 中 — 是否需要设计 carrier 管理表?
3. `live_ready: false` 结构性保证是否应继续保留，还是应允许条件性 `true`?
4. Operation Layer 的 `confirm_operation()` 是否可以作为交易控制台的统一执行入口?
5. 前端是否应使用 `useConsoleData()` 的 20+ 并行调用模式，还是按页面拆分?
6. OwnerConsoleV2.tsx (3792 行) 的拆分策略: 按页面拆分还是按功能层拆分?
7. 审计查询是否需要新的聚合端点，还是前端直接查询各审计表?
8. 断路器和保护健康状态是否需要独立的前端 API?

---

*报告生成时间: 2026-06-03*
*分支: dev @ 51f0085b*
*标签: brc-bnb-prelive-20260601-r35*
