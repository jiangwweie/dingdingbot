# AMT-01 M0 协议与实现证据

日期：2026-11-06。状态：**本地实施已启动，真实新账户协议验收未完成，不可发布。**
本记录区分官方协议、当前SDK源码和本地合成测试；没有调用生产账户接口或发出订单。

## 已核实来源

1. [Binance USD-M REST Trade](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade#get-order-modify-history)：
   `GET /fapi/v1/orderAmendment`要求symbol及精确orderId/clientOrderId，最大100条，
   时间边界inclusive，修改历史不超过3个月；包含amendmentId、前后price/origQty及count。
   `PUT /fapi/v1/order`目前文档只支持LIMIT修改。
2. 同页allOrders/allAlgoOrders：订单列表不是修改日志；取消/过期无成交订单创建超过3天可能
   不可查，创建超过90天不可查；查询窗口小于7天，最大1000条。不能把空结果当完整历史。
3. [官方 User Data Streams](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/user-data-streams.md)：
   `ORDER_TRADE_UPDATE`包括AMENDMENT；未成交挂单/撤单不触发ACCOUNT_UPDATE。
   `ALGO_UPDATE`涵盖NEW/CANCELED/TRIGGERING/TRIGGERED/FINISHED/REJECTED/EXPIRED。
   EXPIRED可由交易所因仓位已平自动发生，不等于Owner取消。
4. [官方 Change Log](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log.md)，
   2026-08-21：trailing订单NEW后可能再发NEW且ia由false变true，属于自然激活。
5. 当前固定CCXT4.5.56源码：REST暴露orderAmendment、algoOrder、allAlgoOrders；
   Pro已有ORDER_TRADE_UPDATE/ALGO_UPDATE处理。它会归一化和缓存订单，不能仅凭最终缓存
   声称保留了所有同ID修改；新识别器需要保留原始事件/历史的标准化变化。

直接urllib访问部分旧页面得到202空响应，不算读取成功。通过官方新文档网页及其Markdown
入口取得以上内容；本地原始材料在忽略的 `.local/app-manual-takeover-v1/m0/`。

## 能力覆盖与未完成项

| 动作 | 已有协议证据 | 本地状态 | 实盘/协议缺口 |
| --- | --- | --- | --- |
| 普通订单未成交新增/取消 | ORDER_TRADE_UPDATE与allOrders | 严格解析与识别测试 | 新账户真实App响应未验 |
| 普通LIMIT同ID修改/改回 | AMENDMENT与orderAmendment before/after | 单次读取和条款判定测试 | 跨页完整性与游标待实现 |
| 条件订单新增/取消 | ALGO_UPDATE与allAlgoOrders | NEW/触发/自然状态区分测试 | App修改stop究竟换ID还是原地修改待只读样本核实 |
| 条件单触发实际订单 | algo actualOrderId与ORDER_TRADE_UPDATE | 复用原归属边界的设计 | 新采集关联尚未接入 |
| 断线期间改回原值 | 普通订单修改历史可补采 | 不完整时REVIEW_REQUIRED | 没有已证实的条件单原地修改历史接口，不得声明补采完整 |
| 超出保留窗口/无法解释状态 | 官方文档明确保留限制 | 不能从快照推断未干预 | 必须持续保留gap，不自动恢复管理 |

**M0尚不能宣称全部App动作已获新账户直接证明。**可以继续不依赖该外部验证的纯模型、
本地协议和持久化约束开发，但真实账户启用及发布必须通过完整操作覆盖验收。
若App条件改单实际支持无法回溯的原地变更，须如实报告，不降级为“等成交才接管”。

## 当前实现边界

新增纯Domain管理权模型与外部订单证据判定、严格原始事件parser、精确订单修改历史
有界只读接口。已增加0016本地迁移、Aggregate持久化、原子接管用例和发送/生命周期检查。
尚未接入真实账户事件采集，未启用任何服务器人工接管运行。
新增测试为合成protocol fixtures，不是实盘成交或账户能力证明。

识别器不凭brc前缀推断来源；自身操作还需精确命令结果、条款与时间匹配。
相同毫秒不同事件不因时间戳去重而丢弃；缺字段、断档和未知命令不自动授予接管或恢复。
MANUAL保持不可逆；当前单个自然事件不能解除已有REVIEW_REQUIRED。


## 本地阶段结果

- 新管理权模型、精确条款/namespace身份、普通/条件事件严格解析、有界修改历史读取。
- 数据库MANUAL不可逆约束和事件原子约束，重读/回滚测试通过。
- 识别用例核对Ticket范围和时间，重复证据幂等；已核实接管时原始Ticket/仓位/交易所挂单不变。
- 未发命令同事务superseded；发送入口拒绝人工/待确认交易，旧超时/未知结果仅记录观察事件。
- 本地Schema升级保全现有源行，源revision证据读取排除新字段，未开发运行时旧schema fallback。
- 1858项Unit/Architecture通过；72项受影响Integration通过；历史迁移切片3项通过。
- Ruff通过，Mypy212个源文件通过；未运行完整R4、API/Static或实盘认证。

## 阶段审查和明确未完成项

当前仅为基础实现，**不是发布候选**：

1. 真实账户事件订阅、持久化补采游标和条件单App改单实际形态尚未验证/接入。
2. 接管用例尚未构建完整durable系统动作归因，只对已完整核实的外部操作走接管；
   系统ID不匹配或未决命令保持待核实，不得直接挂到运行Worker。
3. 多档人工订单current、人工仓只读数量/保护更新、残留订单终结与基础账务尚未完成。
4. 同标的双向唯一占用、人工风险预算重新核算及完整所有写入口审计尚未完成。
5. 初始保护后尚占Lane的接管、待确认恢复AUTO、已平仓接管等特殊路径仍待完整处理。
6. Owner页面目前只补状态映射；完整展示/通知、产品身份防错部署和新环境演练未完成。
7. 当前低层接管事件允许测试/内部构造，生产采集接入前须完成不可伪造的持久证据绑定
   与所有入口统一授权验证，不能将部分约束当完整证据闭环。

测试日志保存在忽略的任务目录，全部为本地可丢弃环境；Tokyo与原账户未修改。
