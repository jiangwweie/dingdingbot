# Binance USDⓈ-M TradFi Perpetual M1 Decision Record

**状态：** `OWNER_ADOPTED / M2_M4_IMPLEMENTATION_AUTHORIZED`

**日期：** 2026-08-11

**阶段：** `M1 Venue/Product Decision`

**目标 StrategyGroup：** `SOR-US-EQ-PERP-001`

## 1. 决策摘要

M1 推荐把美股参考资产永续合约作为现有 **Binance USDⓈ-M Venue** 下的
新 Product Family，而不是接入新 Venue 或建设第二套执行链。

```text
Binance USDⓈ-M Venue
├── Crypto Perpetual Product Family
│   └── existing StrategyGroups
└── TradFi Equity Perpetual Product Family
    └── SOR-US-EQ-PERP-001
```

Owner 于 2026-08-11 采纳本记录，并授权在不部署生产、不开放真实 TradFi ENTRY、
不增加资本的边界内实施 M2–M4。最终边界如下：

1. 继续使用 `binance-usdm`、现有 Binance Futures API、CCXT adapter 和
   Ticket/Command/Lifecycle/Reconciliation/Review 链；
2. 保留现有 canonical instrument identity，例如
   `binance-usdm:AAPLUSDT:perpetual`，不把资产类别塞进字符串 identity；
3. 在 Product Profile 中单独冻结 `TRADIFI_PERPETUAL`、`EQUITY`、Session、
   Mark/Index、Funding、交易规则和企业事件覆盖；
4. M1–M5 继续使用现有 USDⓈ-M 账户，以独立 RuntimeProfile、StrategyGroup、
   StrategyVersion、Universe 和证据隔离产品语义；
5. 全时段 Observation，第一版只允许 **U.S. Regular Session** 新 ENTRY；
6. LONG、SHORT 都进入 Observation；首期候选可以相同，但必须拥有独立 Event 和
   独立 StrategyUniverse，任何真实 ENTRY 留到 M6 分方向批准；
7. 首期候选为 **8 个**，QQQ/SPY 只作为市场背景参考，不创建 SOR Ticket；
8. 策略定义和标的成员通过 Product Compatibility 与 StrategyUniverse 解耦；
   Universe 变更不产生新的 StrategyVersion，错误产品不能仅靠编辑 Universe 进入策略；
9. M1–M5 不增加真实资本，不恢复加密 `SOR-001`，本地 M2–M4 实施不授权生产部署。

本记录是规划和后续设计输入，不是 Registry、PostgreSQL Universe、Owner Policy
或生产运行时权威。

## 2. 已知客观事实

### 2.1 官方产品与 API

| 能力 | 官方事实 | M1 含义 |
| --- | --- | --- |
| API 产品线 | TradFi Perps 位于 Binance **USDⓈ-M Futures REST API** 下 | 继续复用 `fapi` 和现有 Venue boundary |
| 合约类型 | 当前目标产品由 `exchangeInfo` 表示为 `TRADIFI_PERPETUAL`、`EQUITY`、`USDT` | Product Profile 必须冻结精确 product facts |
| 交易时间 | Binance Academy 将合约描述为 **24/7 可交易** | Lifecycle 不依赖底层股票开市才能继续保护和退出 |
| 底层 Session | `tradingSchedule` 提供 `PRE_MARKET`、`REGULAR`、`AFTER_MARKET`、`OVERNIGHT`、`NO_TRADING` | Strategy ENTRY policy 必须区分底层价格发现阶段 |
| Mark/Index | `premiumIndex` 同时提供 Mark Price、Index Price、Funding 和下一资金费时间 | 复用现有 Mark/Funding 事实，新增 Product Admission 解释 |
| Index 透明度 | TradFi Perps 的 index constituents price 按官方说明隐藏为 `-1` | 不把完整指数成分价格作为 ENTRY 硬依赖 |
| 账户前置 | 官方提供单独的 `POST /fapi/v1/stock/contract` TradFi agreement 接口 | 系统不得自动签署；缺少资格时报告 Owner action required |
| 订单能力 | 当前候选的 `exchangeInfo` 暴露 LIMIT、MARKET、STOP、STOP_MARKET、TAKE_PROFIT、TAKE_PROFIT_MARKET、TRAILING_STOP_MARKET | 现有 ENTRY、Initial Stop、TP1 和受控退出语义原则上可复用 |

官方来源：

- [Binance USDⓈ-M Futures Market Data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [Binance TradFi Perps Agreement API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade#futures-tradfi-perps-contract)
- [Binance Academy: 29 TradFi Assets You Can Trade on Binance](https://www.binance.com/en/academy/articles/tradfi-assets-you-can-trade-on-binance-futures)
- [Binance Futures exchangeInfo](https://fapi.binance.com/fapi/v1/exchangeInfo)
- [Binance Futures tradingSchedule](https://fapi.binance.com/fapi/v1/tradingSchedule)

### 2.2 当前代码事实

1. 当前 instrument parser 已接受任意 uppercase USDT perpetual symbol，并转换为
   CCXT `BASE/USDT:USDT`；来源：`src/trading_kernel/domain/instrument_identity.py`。
2. 当前 `brc_instruments` 已有 `asset_class` 和 `contract_kind`，因此 Product Family
   不需要进入 canonical ID；来源：`migrations/trading_kernel/v4_schema.py`。
3. 当前 Venue Adapter 已拥有 instrument rules、leverage brackets、position mode、
   positions、regular/algo orders、order book、Mark Price、fills、funding economics
   和 exact order identity；来源：`src/trading_kernel/infrastructure/venue_adapter.py`。
4. 当前 public market source 已通过 Binance USDⓈ-M CCXT `fetch_ohlcv` 读取闭合
   15m/1h/4h K 线；来源：`src/trading_kernel/infrastructure/binance_public_market_source.py`。
5. 2026-08-11 只读核对显示，当前生产依赖的 CCXT 能识别 AAPL、SNDK、GOOGL
   为 active、linear、USDT-settled TradFi contracts，并可读取 AAPL 15m K 线。
6. Owner 已说明自己在 Binance App 观察和交易过该产品；这是账户使用体验输入，
   不是 API credential 已获授权的自动证明。

第 5 项是本次只读调研证据，第 6 项是 Owner 输入；两者都不构成未来运行时资格。
M3/M5/M6 仍需在行动时重新认证 exact account、API permission、product status、
rules、leverage、orders 和 positions。

## 3. 基于事实的分析

### 3.1 为什么 App 看起来与加密永续相似

用户在 App 中观察到的相似性与官方 API 一致：两类产品共享 USDT 结算、永续合约、
Mark Price、Funding、Futures order types、position mode 和 account surface。

因此执行主干不应因资产类别变化而复制。真正需要扩展的是 **ENTRY 前的产品事实和
策略 Session 语义**，不是 Ticket 之后的第二套生命周期。

### 3.2 不能直接等同的部分

| 主题 | Crypto Perpetual | U.S. Equity TradFi Perpetual | Kernel 响应 |
| --- | --- | --- | --- |
| 合约可交易面 | 24/7 | 官方描述为 24/7 | Lifecycle 都持续运行 |
| 底层价格发现 | Crypto venue 连续 | 股票底层分 PRE/REGULAR/AFTER/OVERNIGHT/NO_TRADING | ENTRY 使用 Venue Schedule 分类 |
| Opening Range | 无美股开盘概念 | 依赖当日 REGULAR session open | M4 从 schedule 生成，不硬编码固定 UTC |
| 企业事件 | 通常无 earnings/split | earnings、split、contract adjustment 可能改变价格语义 | 覆盖缺失、过期或冲突时阻断新 ENTRY |
| Index 审计 | 可查询公开 constituents | constituent price 可能隐藏为 `-1` | 使用 Mark/Index deviation，不要求完整 constituent price |
| 产品协议 | Futures 账户权限 | 另有 TradFi agreement | 不自动签署；缺失时以 Owner action required 阻断 ENTRY |
| 流动性状态 | 全天变化 | 与股票 session、新闻和财报明显相关 | M5 按 Session 分桶记录 spread/depth/slippage |
| 产品变更 | 上下架和规则调整 | 另有 split、ticker/contract adjustment 风险 | Product drift fail-closed，既有 Ticket 继续安全工作 |

### 3.3 Session 决策

```text
All Sessions
-> Observation enabled
-> Signal evidence retained

U.S. REGULAR only
-> first-version new ENTRY eligible

PRE_MARKET / AFTER_MARKET / OVERNIGHT / NO_TRADING
-> Observation only
-> new ENTRY blocked by product policy
-> existing Ticket protection, exit and reconciliation continue
```

这个边界优先解决加密 15m SOR 已暴露的流动性和波动率问题，同时保留未来比较不同
Session 的证据。M5 有足够观察后，才能单独讨论扩展 PRE_MARKET 或 AFTER_MARKET，
不能在 M1 预先开放。

## 4. M1 Capability Matrix

| 决策域 | 推荐结果 | 复用能力 | 新增能力 | M1 硬边界 |
| --- | --- | --- | --- | --- |
| Venue | `binance-usdm` | current CCXT/REST boundary | 无新 Venue | 不建设第二套 adapter |
| Product | `TRADIFI_PERPETUAL / EQUITY / USDT` | rules、orders、positions、fills、funding | Product Profile 与 drift classification | exact facts 不得由 symbol 猜测 |
| Account | 现有 USDⓈ-M account | position mode、cross margin、global capacity | 独立 RuntimeProfile/Product capability certification | M1–M5 不增加资本 |
| Instrument ID | `binance-usdm:<SYMBOL>:perpetual` | 现有 parser、Netting Domain、Ticket identity | `asset_class`、`contract_kind` 和 Product Profile | 不迁移现有 Crypto ID |
| Session | 全时段观察、REGULAR ENTRY | persistent Observation/Lifecycle | `tradingSchedule` source 与 session projection | schedule stale/missing 阻断 ENTRY |
| Market data | Binance 15m candles | closed-candle source | spread、depth、Mark/Index、funding session facts | 不引入高频全市场抓取 |
| Direction | LONG/SHORT Observation | independent position sides | 分 Event 的 admission evidence | M6 分方向批准真实 ENTRY |
| Corporate events | fail-closed | Incident、fence、Review lineage | earnings/split/adjustment authority | 未选数据源前不开放 ENTRY |
| Failure | stop new ENTRY | current protection/recovery/reconciliation | product-specific blocker mapping | 不因新产品冻结既有 Ticket safety |
| Frontend | 当前 Owner Console | StrategyGroup、Ticket、Review 路由 | Instrument Center、Product/Session status、Universe Diff | 手动刷新、有界查询 |

## 5. 首期标的规划

### 5.1 Entry 候选

| 标的 | Venue Symbol | 角色 | 纳入原因 | M5 重点观察 |
| --- | --- | --- | --- | --- |
| Apple | `AAPLUSDT` | candidate | 大型科技、Owner 明确关注 | opening spread、财报窗口 |
| Alphabet | `GOOGLUSDT` | candidate | 大型科技、Owner 明确关注 | gap、Mark/Index deviation |
| Microsoft | `MSFTUSDT` | candidate | 大型科技、AI/云代表 | spread、15m bar continuity |
| NVIDIA | `NVDAUSDT` | candidate | AI/半导体高关注度 | 波动率、追价和失败突破 |
| Meta | `METAUSDT` | candidate | 大型科技、广告/AI | funding、财报后路径 |
| Amazon | `AMZNUSDT` | candidate | 大型科技、云与消费 | opening liquidity、slippage |
| Tesla | `TSLAUSDT` | candidate | 高波动、高参与度 | fake breakout、stop distance |
| SanDisk | `SNDKUSDT` | conditional candidate | Owner 明确关注、存储周期代表 | 异常成交量、价格连续性、企业事件 |

### 5.2 参考标的

| 标的 | Venue Symbol | 角色 | 边界 |
| --- | --- | --- | --- |
| Nasdaq 100 ETF | `QQQUSDT` | market context | M1 不创建 SOR Ticket；M4 决定是否进入 regime evidence |
| S&P 500 ETF | `SPYUSDT` | market context | M1 不创建 SOR Ticket；M4 决定是否进入 regime evidence |

候选集合是 M1 推荐，不是当前 Active Universe。安装前必须重新验证 product status、
USDT settlement、rules、15m history、account capability 和企业事件覆盖。

第一期明确排除 leveraged/inverse ETF、Pre-IPO、HK equity、KR equity、commodity 和
非 USDT settlement 产品，避免在一个策略试验中同时引入多个产品语义。

## 6. 账户与资本边界

### 6.1 推荐账户模型

```text
one Binance USDⓈ-M account
└── one existing Venue Adapter instance
    ├── existing Crypto RuntimeProfile
    └── new U.S. Equity Observation RuntimeProfile
```

两个 RuntimeProfile 可以共享同一 `venue_id + account_id`，但必须拥有独立的
StrategyGroup、Event、Universe、instrument certification 和统计身份。由于账户使用
cross margin，M6 如果开放真实 ENTRY，所有产品继续共享全局 account capacity、
gross stop risk、margin utilization 和 global ENTRY serialization。

M1 不要求新子账户。只有以下情况在 M6 前触发重新决策：

1. Binance 要求不同账户或不同 API permission；
2. 同账户无法给出可读的产品级资本边界；
3. TradFi exposure 与 Crypto exposure 的共享 cross-margin 风险无法在现有 Policy
   中被准确表达；
4. Owner 明确要求资金或凭据隔离。

M3 不调用 `POST /fapi/v1/stock/contract` 替 Owner 接受产品协议。产品资格无法通过
只读事实确认时，状态保持 `owner_action_required`；M6 前由 Owner 在官方界面完成，
再通过行动时订单权限和账户事实验收。

## 7. 数据与权威

| 事实 | 首选权威 | 刷新建议 | 缺失行为 |
| --- | --- | --- | --- |
| Product/rules/status | Binance `exchangeInfo` + authenticated rules | 15–30 分钟或 certification 时 | 阻断新 ENTRY |
| Underlying session | Binance `tradingSchedule` | 30 分钟；按 `updateTime` 和 horizon 校验 | 阻断新 ENTRY |
| Closed candles | Binance USDⓈ-M Kline | 每根闭合 15m 增量读取 | 不生成 Signal |
| Mark/Index/Funding | Binance `premiumIndex` / funding endpoints | Observation 有界采样；action time 重读 | 阻断新 ENTRY |
| Spread/depth | Binance order book | 候选有界采样；action time 重读 | 阻断新 ENTRY |
| Earnings/split/adjustment | M3 单独选择的机构或交易所级数据源 | 日级同步 + event window 加密刷新 | 阻断新 ENTRY |
| Position/order/fill | authenticated Binance account facts | 现有 Entry/Lifecycle/Reconciliation cadence | 现有 hard stop |

Binance 当前公开 USDⓈ-M API 资料没有形成可直接替代 earnings/split authority 的完整
企业事件接口。因此 M3 必须单独选择数据源；M1 不用猜测或硬编码未来财报日期。

### 7.1 Runtime ownership

| Worker | M3/M4 推荐职责 | 不新增的职责 |
| --- | --- | --- |
| Reconciliation | 有界刷新 Product/rules/account capability、schedule horizon 和 corporate-event coverage | 不生成策略 Signal，不按标的创建新服务 |
| Observation | 读取闭合 K 线和 current product/session facts，运行 `SOR-US-EQ-PERP-001` detector | 不决定资本，不创建 Ticket |
| Entry | action time 重验证 Product、Session、Mark/Index、spread/depth、corporate-event 和现有 Capacity gates | 不自动签署协议，不绕过 durable Command |
| Lifecycle | 继续安装/维护保护、TP1、退出和受控恢复 | 不因 Session 变化放弃已有 Ticket |

### 7.2 Transaction boundary

Venue 和外部 corporate-event 网络读取必须在 PostgreSQL transaction 之外完成；读取成功后
使用一个短事务更新 exact current projection 和 digest。Entry 在现有原子 Ticket issuance
事务中冻结所使用的 Product、Session 和 corporate-event evidence identity。网络失败只留下
明确 blocker 或 Incident，不允许把半份产品事实写成 eligible。

## 8. 性能边界

面向当前 **2C4G** 主机，M3/M4 采用低频、有界、增量模型：

1. 不为每个标的或 Product Family 新增 Worker；
2. `exchangeInfo` 和 `tradingSchedule` 为共享快照，不按标的重复请求；
3. 8 个候选只在闭合 15m bar 后增量加载，不重拉完整历史；
4. spread/depth 只对当前候选有界采样，action-time 再精确读取目标 instrument；
5. corporate events 采用日级批量同步，不在 2 秒 Entry cadence 调外部日历服务；
6. 前端继续手动刷新，所有列表分页并读取 current projection；
7. M5 Observation 结果写 PostgreSQL current/append-only evidence，不生成周期性文件。

## 9. M2–M4 影响

### 9.1 M2A 可以先做

M1 后可以设计只读的：

- StrategyGroup 驾驶舱中的 Venue、Product Family、RuntimeProfile 和 Entry Window；
- Instrument Center 中的 product status、current session、spread、Mark/Index、funding、
  corporate-event coverage 和 Universe membership；
- 候选详情弹窗、相关 Ticket/Review 路由与返回路径。

### 9.2 M3 范围缩小

M3 不需要新 Venue Adapter 或 instrument identity migration。主要范围为：

1. Product Profile 与 product drift；
2. Binance `tradingSchedule` typed source；
3. Product/Session/Corporate Event admission；
4. 同一 account 下的第二 RuntimeProfile；
5. Instrument Center current projections；
6. exact action-time certification 与 failure mapping。

### 9.3 M4 保持策略专属

M4 再定义 `SOR-US-EQ-PERP-001` 的：

- Opening Range；
- LONG/SHORT Event；
- initial stop、TP1、failure exit、time stop 和 runner；
- Signal expiry；
- Live/Replay parity；
- QQQ/SPY 是否进入 regime evidence。

M1 不提前锁定任何收益参数或恢复加密 SOR 的决定。

## 10. M1 Owner 决策与完成状态

Owner 已明确采纳以下四项，**M1 已完成决策收口**：

1. Venue：`binance-usdm`；
2. Account：同一 USDⓈ-M account，以独立 RuntimeProfile 逻辑隔离；
3. Scope：8 candidates + QQQ/SPY reference；
4. Direction/Session：LONG/SHORT 都观察，第一版仅 REGULAR new ENTRY。

Owner 已另行授权本地实施 M2、M3、M4，包括前向 Schema、Registry、Universe、
Observation-only RuntimeProfile/Policy、Owner API 和 Owner Console 变更。该授权不包含：

1. 生产部署或服务器变更；
2. TradFi API agreement 接受、credential 变更或交易所写入；
3. 开放真实 TradFi ENTRY 或增加资本；
4. 恢复加密 `SOR-001`；
5. MPG、BRF2、CPM、MI 或 RSRVCB 的 TradFi 实施。
