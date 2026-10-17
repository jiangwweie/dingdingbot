# Trades 交易事实修复 — 2026-10-17

基线：eb0ca974；范围仅 Owner Console V2；未部署、未调用业务写 API。

| 问题 | 实现及真实字段 |
| --- | --- |
| 实际价与参考价混用 | CausalityDrawer 独立展示 actual_entry_price 与 entry_reference_price；实际价缺失显示未取得 |
| 活动止损误用计划价 | active_stop_price 与 initial_stop_price 独立展示，不回退；价格及数量使用 API 十进制字符串，不截断 |
| 保护状态 | tradeTruth.protectionFact 根据 AggregateStatus 区分 confirmed/transition/unknown/risk/insufficient；position_protected、runner_protected 才确认保护，不由阶段推断 |
| 活动记录覆盖 | Trades 使用现有 GET overview 的 active_ticket_ids、active_ticket_count 对照已加载非终态 Ticket 集合；freshness 非 fresh、数量或身份不一致均不声明完整 |
| 终态分类 | 父级改为已结束交易；leverage_rejected、entry_rejected、entry_reconciled_absent 为未成交终止，排除经济计算；terminal 经济数据可用才分胜负平保；Review 缺失及其他不可用状态保留未知 |
| 精度 | decimal.js 十进制计算收益及 R，展示最终保留两位；价格、数量保留原始精度；增加超过 JS 安全整数范围及抵消求和测试 |

状态语义来源：只读检查 domain/aggregate.py、application/owner_console/trades.py、causality.py。未修改这些后端文件。

## 验证

- 34 项现有回归通过。
- 16 项原验收契约断言通过。
- test_trade_truth.mjs：价格缺失、runner 保护/转换/未知/异常、拒绝与结算、覆盖不完整及 stale、精确 Decimal 均通过。
- test_trades_pagination.mjs：真实 React Query 配置的第二页失败保留、重试、固定时间窗、追加与汇总通过（仅网络边界替身，不是生产证据）。
- TypeScript/Vite build、脚本语法与 git diff --check 通过。
- Dark/Light：检查改动继续使用现有语义色及 dark 样式，无独立主题分支；本轮未完成实机双主题截图验收。
- 浏览器工具当前仅见管理页及 ChatGPT，未发现已认证 V2 标签页；未读取密码、TOTP seed 或 Cookie，未执行生产 GET 浏览器复验。

## 限制

30 天历史分页不能证明全账户活动覆盖；页面保留缺口提示及缺失身份数，不补造 Ticket。Overview 与 Tickets 属于不同只读快照，身份差异也可能来自时序变化，不自动判为事故。

列表接口未直接提供当前保护单完整证明，也未提供独立 Settlement 完成标记；保护确认仅表示后端聚合状态，已结算标签依据 terminal 与可用经济字段，不宣称完整自然生命周期独立验收。

历史交付报告中的生产浏览器 PASS 不覆盖本次修改。完成本轮修复后停止，不宣称 Trades 整页通过独立验收。
