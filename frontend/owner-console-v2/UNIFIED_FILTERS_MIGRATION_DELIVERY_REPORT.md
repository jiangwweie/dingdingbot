# Trades / Strategies 历史筛选迁移与缺口闭环

日期：2026-10-20（Asia/Shanghai）

基线：`5a8673446d1f5a3089224540f82113bdf31ecd29`。分支：`codex/owner-console-v2-dev`。
范围仅为 `frontend/owner-console-v2/`，包含原工作区的迁移实现及此次补齐。

## 最终行为

| 能力 | 实现与事实来源 |
| --- | --- |
| Trades 历史筛选 | `/tickets` GET 接收固定 `from_ms/to_ms`、strategy_group_id、exchange_instrument_id、position_side、aggregate_status；切换条件使用独立 Query Key 与首页 Cursor |
| Strategies 统一窗口 | `/strategies`、版本 Tickets、版本 Observations 继承相同起止时间；Drawer 从当前查询结果派生，刷新、深链接与前进后退恢复 URL 状态 |
| 实时在管 | 独立读取 `/overview.active_ticket_ids`，逐身份使用现有 `/tickets/{ticket_id}/causality` GET；不受历史时间或业务筛选影响，不读取全部历史来凑实时集合 |
| 实时覆盖限制 | identity、terminal_at_ms、Overview 数量和 freshness 必须满足核验条件；缺失、错误、已终止或身份不匹配时不宣称完整，不将失败解释为空仓 |
| 历史版本 | 经济指标仍按 StrategyVersion 隔离；历史版本不显示当前运行占用；账户在管总数直接取 `/controls.account_capacity.active_ticket_count`，不逐版本累加 |
| 日期编辑 | 自定义起止时间先保留草稿，点击“应用时间范围”一次性验证并提交；倒置、缺失或超过 90 天不发查询 |
| 上海时区 | 日期输入固定 UTC+8；策略窗口、Drawer 日期和 Tickets / Observations 时间显示显式使用 Asia/Shanghai；表头使用“查询范围”而非固定 30 天 |
| 错误及分页 | Trades 刷新失败保留旧快照并显示错误、STALE 与重试；历史请求失败不隐藏实时持仓；跨页按 ticket_id 去重；Natural 筛空首页后，下一页失败重试该 Cursor |

此前已验证的 P1-3 后退筛选残留与 P2 重复历史记录继续保持关闭。本次保留原 URL Hook 的原子更新，不重新实现该逻辑。

## 回归证据

新增 `node frontend/owner-console-v2/verify_filter_closure.mjs` 使用独立浏览器上下文与纯合成数据。
先在原实现运行，6 项场景全部失败；修复后 6 项通过，另补两项身份失败/历史失败隔离负例，最终 8 项通过。
此脚本不读生产快照、不加载 Owner Cookie，所有 API 被本地拦截，断言请求只能为 GET。

1. 自定义历史日期草稿与应用、90 天拒绝。
2. 刷新失败保留旧数据、披露旧快照与错误。
3. 历史查询为空仍展示实时活动 Ticket。
4. 历史首屏失败不隐藏实时卡片。
5. 实时身份读取失败不能显示账户空仓。
6. 重叠分页去重、第二页失败保留、Cursor 重试、固定窗口及条件变化重置。
7. 历史版本不重复计入账户占用，UTC 浏览器仍显示上海时间。
8. Natural 首页全为 not_terminal 时，失败的第二页使用原 Cursor 重试。

| 命令（V2 目录） | 实际结果 | 类型 |
| --- | --- | --- |
| `pnpm build` | PASS，1961 modules，747.40 kB 主 JS（gzip 216.79 kB） | TS / Vite |
| `node test_time_range_filter.mjs` | 12 PASS | 单元 |
| `node test_url_search_params.mjs` | 8 PASS | 单元 |
| `node test_unified_filters_integration.mjs` | 19 PASS | 工具与契约 |
| `node test_defect_regressions.mjs` | 34 PASS | 既有回归 |
| `node test_trade_truth.mjs` | PASS | 真实映射与十进制 |
| `node test_trades_pagination.mjs` | PASS | 查询引擎分页 |
| `node test_chart_adapter.mjs` | 23 PASS | 图表适配与 QueryObserver |
| `node test_strategies_regressions.mjs` | 49 PASS | 策略回归 |
| `node test_verification_contracts.mjs` | 16 PASS | 验收契约 |
| `node test_live_auth_verification.mjs` | 12 PASS | 认证评定 |
| `node verify_filter_closure.mjs` | 8 PASS | 合成数据隔离 UI |
| `node verify_unified_filters_browser.mjs` | PASS | Mock UI，非生产 E2E |
| `node verify_k_line_e2e.mjs` | PASS | Mock UI，非生产 E2E |
| `node verify_k_line_component_race.mjs` | PASS | 真实挂载组件、合成 API |

既有 K 线 E2E 调整了 fixture 的 terminal_at_ms，使活动身份与账本一致，并通过 Ticket ID 选择首个测试对象。
保留不同 Ticket / 周期、零提前请求、真实方向及全屏 / Escape 断言，没有以清缓存或放松断言规避失败。

保留原迁移的 `chunkSizeWarningLimit: 1000`。无构建告警仅表示未超过该阈值，不代表完成 bundle 体积优化。

## 真实生产 GET 浏览器补验

Owner 现有已认证浏览器，未读取认证秘密，未注入此节的业务响应。

| 场景 | 本轮实测结果 |
| --- | --- |
| 6/1—6/2 历史范围加 LONG 筛选 | 历史 0 条，仍加载与 Overview 一致的全部 3 个活动 Ticket（包括 SHORT） |
| 历史版本 view=all | 13 个版本，账户在管数为 3，与 controls 一致；历史 BRF2 v2 不归属当前运行占用 |
| 实时 Ticket 因果与 K 线 | 切图表前蜡烛请求 0；点击后行情 GET 200，48 根 |
| 10 秒空闲窗口 | 新增业务请求 0；本轮未处理页面异常 0；业务写请求 0 |

截图存于本机 `.local/unified-filters-closure-20261020/live-independent-active.png` 与 `live-history-account-count.png`，不作为运行时权威或提交的生产数据。
Overview 本轮 freshness 为 unavailable，因此即使活动身份集合一致也继续披露覆盖未确认，未绕过 freshness 条件。
所有本地故障拦截、监听已移除，未遗留登录拦截。

## 保留限制

- 真生产数据未自然触发的分页失败、重叠分页与重试，仅有隔离测试证据。
- 生产关联实际 Ticket 的 Observation 样本、Chrome 原生 125% / 150% 缩放仍为 NOT TESTED。
- 本次验证由实施者执行，不将其称为新一轮独立全站验收。
- 未修改 Kernel、API、数据库、生产配置，未调用业务写 API，未推送、合并或部署。
