# 策略独立标的池与美股合约完整接入验收矩阵

**状态：** `IMPLEMENTATION_TRACKING`

**日期：** 2026-07-27

**设计基线：** `docs/superpowers/specs/2026-07-27-us-equity-perpetual-rsr-vcb-15m-design.md`

**执行基线：** `docs/superpowers/plans/2026-07-27-strategy-universe-us-equity-full-live.md`

## 1. 使用规则

### 1.1 证据等级

| 等级 | 含义 | 可否完成验收 |
|---|---|---|
| `UNIT` | 纯领域公式或边界测试 | 否 |
| `INTEGRATION` | 真实 application/repository/PostgreSQL 或 adapter contract | 否 |
| `FULL_CHAIN` | 真实内核链 + PostgreSQL + 仅外部边界 mock | 是，且仍需全回归 |
| `STATIC` | Ruff、Mypy、architecture、file-I/O audit | 是，作为补充硬门 |
| `DEPLOYMENT_TIME` | 生产行动时事实与 Owner 确认 | 只能部署时完成 |

### 1.2 状态

- `PLANNED`：设计和测试位置已锁定，尚未实现；
- `RED`：目标测试已按预期失败；
- `GREEN_LOCAL`：目标测试已通过；
- `GREEN_FULL`：全套回归与静态门已通过；
- `DEPLOYMENT_BLOCKED`：代码已完成，但生产动作等待 Owner 确认。

## 2. 需求覆盖矩阵

| ID | 需求与不变量 | 设计章节 | 主要生产文件 | 核心测试 | 证据等级 | 当前状态 |
|---|---|---|---|---|---|---|
| U-01 | Strategy/Event 语义与 Universe 成员身份分离 | 3.2–3.3 | `domain/strategy_plugin.py`, `domain/strategy_universe.py` | `unit/test_strategy_plugin.py`, `unit/test_strategy_universe.py` | UNIT + INTEGRATION | PLANNED |
| U-02 | 六个 Event 使用精确独立加密池 | 4.1 | `infrastructure/strategy_universe_seed.py` | `integration/test_strategy_universe_seed.py` | INTEGRATION | PLANNED |
| U-03 | 总计 36 个加密 scope，AVAX 为零 | 4.1 | `infrastructure/runtime_authority_seed.py` | `integration/test_runtime_authority_seed.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| U-04 | 美股 13 candidate + 2 reference，reference 不产生 Ticket scope | 4.2 | `infrastructure/strategy_universe_seed.py` | `integration/test_strategy_universe_seed.py` | INTEGRATION | PLANNED |
| U-05 | Universe install/warm/activate/retire 状态机 | 4.3 | `application/install_strategy_universe.py`, `application/activate_strategy_universe.py` | `integration/test_strategy_universe_activation.py` | INTEGRATION | PLANNED |
| U-06 | current pointer 与 scope 状态原子切换 | 4.4 | `infrastructure/pg_universe_repository.py` | `integration/test_strategy_universe_activation.py` | PostgreSQL INTEGRATION | PLANNED |
| U-07 | 无重启候选替换，旧 Ticket 身份不变 | 4.3–4.4 | workers、runtime repositories | `full_chain/test_universe_replacement_certification.py` | FULL_CHAIN | PLANNED |
| P-01 | 静态插件注册七个 Event，不动态执行数据库代码 | 3.2 | `domain/strategy_plugin.py` | `architecture/test_strategy_universe_boundaries.py` | UNIT + STATIC | PLANNED |
| P-02 | 所有策略只产生标准 StrategySignal | 1.1、5.1 | `application/produce_strategy_signal.py` | `full_chain/test_us_equity_strategy_certification.py` | FULL_CHAIN | PLANNED |
| R-01 | 4h QQQ/SPY Regime 精确且 fail-closed | 5.3 | `domain/detectors/rsr_vcb.py` | `unit/detectors/test_rsr_vcb.py` | UNIT + FULL_CHAIN | PLANNED |
| R-02 | 1h 24h/72h RSR、volume、EMA 资格 | 5.4 | `domain/universe_projection.py` | `unit/test_universe_projection.py` | UNIT | PLANNED |
| R-03 | 确定性 top-2，tie-break 稳定 | 5.4 | `domain/universe_projection.py` | `unit/test_universe_projection.py` | UNIT + INTEGRATION | PLANNED |
| R-04 | 每个闭合 1h 周期仅一次 projection | 10.1、10.3 | `application/project_strategy_universe.py` | `integration/test_strategy_universe_query_bounds.py` | INTEGRATION | PLANNED |
| V-01 | BB20 sample std 与 shifted quantile 无前视 | 5.5 | `domain/detectors/rsr_vcb.py` | `unit/detectors/test_rsr_vcb.py` | UNIT | PLANNED |
| V-02 | compression、EMA50、prior 72h high armed | 5.5 | `domain/detectors/rsr_vcb.py` | `unit/detectors/test_rsr_vcb.py` | UNIT + INTEGRATION | PLANNED |
| V-03 | rank、Regime、Universe 变化使 armed 失效 | 5.5 | projection/armed repositories | `integration/test_rsr_vcb_observation.py` | INTEGRATION | PLANNED |
| T-01 | 第一根闭合 15m cross + bullish + volume 1.80 | 5.6 | `domain/detectors/rsr_vcb.py` | `unit/detectors/test_rsr_vcb.py` | UNIT + FULL_CHAIN | PLANNED |
| T-02 | Trigger 晚于 armed，24h cooldown，重放幂等 | 5.6 | detector、signal repository | `integration/test_rsr_vcb_observation.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| T-03 | Signal 冻结 projection/armed/universe/product/session lineage | 5.6、8.2 | signal/ticket models/repositories | `integration/test_issue_ticket.py` | INTEGRATION | PLANNED |
| M-01 | 744×1h 多页闭合 K 线 | 5.2、10.2 | market port、Binance public source | `integration/test_market_window_pagination.py` | INTEGRATION | PLANNED |
| M-02 | 重复、乱序、缺口、未闭合尾 K fail-closed | 10.2 | `application/load_closed_candle_window.py` | `unit/test_closed_candle_window.py` | UNIT + INTEGRATION | PLANNED |
| M-03 | 15m 深度数据只拉 top-2 | 10.3 | observation/project use cases | `integration/test_strategy_universe_query_bounds.py` | INTEGRATION | PLANNED |
| S-01 | regular/premarket/afterhours/overnight/weekend 分类 | 6.2 | `domain/us_equity_session.py` | `unit/test_us_equity_session.py` | UNIT + FULL_CHAIN | PLANNED |
| S-02 | multiplier 为 1/0.5/0.5/0.25/0.25 | 6.2 | Session policy | `integration/test_cross_asset_capacity.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| S-03 | DST、节假日、提前收市、未知日历 | 6.2 | calendar seed/classifier | `integration/test_us_market_calendar_seed.py` | INTEGRATION | PLANNED |
| S-04 | 2026–2028 版本日历，horizon 外 fail-closed | 6.2 | `infrastructure/us_market_calendar_seed.py` | `integration/test_us_market_calendar_seed.py` | INTEGRATION | PLANNED |
| A-01 | 产品必须为 TRADIFI_PERPETUAL/EQUITY/USDT/TRADING | 6.1 | `domain/product_admission.py` | `unit/test_product_admission.py` | UNIT + FULL_CHAIN | PLANNED |
| A-02 | spread、mark-index、top-5 depth 分 Session 准入 | 6.3 | ProductAdmission policy/snapshot | `integration/test_product_admission_snapshot.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| A-03 | funding/product facts stale 或缺失 fail-closed | 6.3 | ProductAdmission snapshot | `integration/test_product_admission_snapshot.py` | INTEGRATION | PLANNED |
| C-01 | earnings -4h 与 +2 根闭合 15m | 6.4 | `domain/corporate_events.py` | `unit/test_corporate_events.py` | UNIT + FULL_CHAIN | PLANNED |
| C-02 | date-only earnings 整日冻结 | 6.4 | corporate event policy | `unit/test_corporate_events.py` | UNIT | PLANNED |
| C-03 | coverage 缺失/过期/冲突 fail-closed | 6.4 | corporate event repository | `integration/test_product_admission_snapshot.py` | INTEGRATION | PLANNED |
| C-04 | split/adjustment 触发 freeze/reprofile/rewarm | 6.4 | product/universe services | `full_chain/test_us_equity_strategy_certification.py` | FULL_CHAIN | PLANNED |
| K-01 | 加密与美股共享 max 3 active Tickets | 7.1 | capacity policy/use case | `full_chain/test_cross_asset_strategy_certification.py` | FULL_CHAIN | PLANNED |
| K-02 | 组合 gross risk at stop 不超过 9% equity | 7.1、7.3 | `domain/capacity.py` | `integration/test_cross_asset_capacity.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| K-03 | 总 initial margin 不超过 90% | 7.1、7.3 | capacity sizing | `integration/test_cross_asset_capacity.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| K-04 | 美股固定 5x，Session 只缩 stop-risk | 7.1–7.2 | runtime policy/capacity sizing | `unit/test_capacity_sizing.py` | UNIT + FULL_CHAIN | PLANNED |
| K-05 | action-time Session/product drift 重验证 | 7.3 | capacity/preflight | `unit/test_entry_dispatch_preflight.py` | UNIT + INTEGRATION | PLANNED |
| E-01 | fast breakout failure | 8.3 | `domain/exit_policy.py` | `full_chain/test_registered_strategy_exit_matrix.py` | FULL_CHAIN | PLANNED |
| E-02 | 1R TP1 50%、BE、structural runner | 8.3 | exit policy/lifecycle | `full_chain/test_us_equity_strategy_certification.py` | FULL_CHAIN | PLANNED |
| E-03 | TP1 前 24h time stop 与 72h max holding | 8.3 | `domain/exit_policy.py` | `full_chain/test_registered_strategy_exit_matrix.py` | FULL_CHAIN | PLANNED |
| E-04 | protective stop 优先、cadence 幂等 | 8.3 | lifecycle state machine | `integration/test_ticket_lifecycle_maintenance.py` | INTEGRATION + FULL_CHAIN | PLANNED |
| D-01 | `0001 -> 0002` upgrade/downgrade/upgrade | 9.1 | Alembic 0002 | `integration/test_schema_migration_postgres.py` | PostgreSQL INTEGRATION | PLANNED |
| D-02 | 新约束、索引、外键、append-only 语义 | 9.2–9.4 | migration/pg models | schema/repository integration tests | PostgreSQL INTEGRATION | PLANNED |
| D-03 | 前向 DML 保留历史并关闭 current blocking state | 12 | cutover repository/script | `integration/test_strategy_universe_cutover_dml.py` | PostgreSQL INTEGRATION | PLANNED |
| D-04 | DML 单事务、精确 identity、重放幂等 | 12 | cutover repository/script | `integration/test_strategy_universe_cutover_dml.py` | PostgreSQL INTEGRATION | PLANNED |
| F-01 | projection/worker lease 崩溃后重领 | 10.1、11 | workers/repositories | `full_chain/test_fault_matrix.py` | FULL_CHAIN | PLANNED |
| F-02 | Signal/Ticket/Command 重放不重复 | 9.4、11 | repositories/state machines | `full_chain/test_fault_matrix.py` | FULL_CHAIN | PLANNED |
| F-03 | ENTRY unknown outcome 不盲目重发 | 11 | existing recovery chain | `full_chain/test_fault_matrix.py` | FULL_CHAIN | PLANNED |
| F-04 | partial fill 继续 cancel/flatten/release | 11 | existing recovery chain | `full_chain/test_fault_matrix.py` | FULL_CHAIN | PLANNED |
| X-01 | domain 纯净、单执行链、无文件权威 | 2.1、14 | architecture boundaries | architecture tests | STATIC | PLANNED |
| X-02 | 无旧 schema fallback 或 dual write | 2.2、9.1 | all runtime code | `architecture/test_strategy_universe_boundaries.py` | STATIC | PLANNED |
| X-03 | 当前 runtime 不实现相关性 | 2.2、15 | all runtime code | `architecture/test_no_correlation_runtime.py` | STATIC | PLANNED |
| X-04 | no-signal cadence 零文件输出 | 10.3、14 | workers/runtime | file-I/O audit + full-chain | STATIC + FULL_CHAIN | PLANNED |
| G-01 | 全部 trading_kernel 回归通过 | 13.4 | all | `pytest tests/trading_kernel -q` | FULL_CHAIN aggregate | PLANNED |
| G-02 | Ruff、Mypy、architecture、diff check 通过 | 13.4 | all | exact static commands | STATIC | PLANNED |
| G-03 | disposable PostgreSQL 全新建库/seed/certify | 13.4 | scripts/migrations | exact acceptance commands | PostgreSQL INTEGRATION | PLANNED |
| O-01 | 提交后不部署，等待 Owner 确认 | 1.2、12、16 | process boundary | mutation audit | DEPLOYMENT_TIME | PLANNED |

## 3. 基线证据

| 日期 | Commit | 命令 | 结果 | 用途 |
|---|---|---|---|---|
| 2026-07-27 | `49b87b5f9c3e4c74d5bfb6baa34448146a2ea961` | `python3 -m pytest tests/trading_kernel -q` | **421 passed in 110.43s** | 实施前回归基线 |

## 4. 部署时独立硬门

以下事实不会被本地测试替代，完成代码后保持 `DEPLOYMENT_BLOCKED`：

1. 目标 release commit/tag 与本分支验收 commit 完全一致；
2. Tokyo PostgreSQL schema、systemd、旧/新 writer facts 当场刷新；
3. Owner 手动平仓后，交易所逐 instrument/position side 精确为 flat；
4. 目标订单为零，unknown outcome 为零；
5. Entry 已 fenced，四个服务按部署合同停止；
6. DML dry-run before/after 计数被复核；
7. Owner 对真实 migration、DML、release switch 与受控实盘重新确认。
