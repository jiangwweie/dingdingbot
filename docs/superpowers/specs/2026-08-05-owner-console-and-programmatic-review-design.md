# Owner Console 与程序化复盘读模型设计

> 日期：2026-08-05
>
> 状态：APPROVED_FOR_SPEC_REVIEW
>
> 适用范围：Tokyo Trading Kernel 的单 Owner 只读运营、交易因果查看与程序化复盘表面

## 1. 决策

建设一个单 Owner 的 **Owner Console**，首版使用四个一级页面：

```text
总览
信号
交易
复盘
```

单笔交易因果工作台是交易模块的二级详情，不是第五个一级页面。

首版 Console 的业务能力保持只读：

- 从 PostgreSQL 读取运行真相、Signal、AdmissionDecision、Ticket、Event、Command、Incident、Settlement 与当前有效 Review；
- 从 Binance USD-M 公共 OHLCV 接口按需读取 TradingView K 线背景；
- 通过确定性规则生成逐 Ticket 的程序化复盘读模型；
- 不计算策略排名，不根据小样本给出策略有效性结论；
- 不下单、不改单、不撤单、不改变策略、Policy 或 StrategyUniverse；
- 不自动刷新，不增加后台分析 Worker、行情采集 Worker、WebSocket、SSE、Redis 或持久化分析投影。

Console 通过公网 HTTPS 域名访问，身份模型固定为一个 Owner 账号：

```text
用户名 + 密码
-> Google Authenticator TOTP
-> Owner Session
```

未来可以在独立的 **Owner Control Plane** 中增加暂停/恢复 StrategyGroup、StrategyUniverse 版本管理和受控退出，但这些能力不属于首版实现。任何受控退出都必须进入 Kernel 现有的 durable EXIT Command 链，不能成为前端直连交易所的旁路。

## 2. 已知客观事实

### 2.1 权威边界

当前权威顺序为：

```text
Owner 明确决策
-> 当前代码与 Git 状态
-> 当前 PostgreSQL 与交易所只读事实
-> docs/current
-> 历史材料
```

PostgreSQL 保存当前运行真相与追加式生命周期事实。交易所只读事实拥有外部订单、仓位和成交真相。生成内容仅用于展示，不能拥有生产决策权。

### 2.2 当前只读表面

`src/trading_kernel/interfaces/readonly_api.py` 当前只支持按精确键读取 Monitor 与单 Ticket Owner Projection。它不是页面级 HTTP API，也不提供总览、列表、因果详情或复盘中心读模型。

### 2.3 当前 Review 事实

当前 Trade Review：

- 使用追加式 revision 链；
- Aggregate `review_id` 指向唯一当前有效 Review；
- 保存 `outcome`、`metrics` 与 `decision_impact`；
- 能保存成交归因、Gross PnL、Fees、Funding、Net PnL、计划与实际风险、Net R 和经济证据完整性；
- Funding 或外部退出事实缺失时记录显式不可用原因，不按零处理。

### 2.4 当前 K 线来源

现有 `CcxtBinancePublicMarketSource` 已通过无凭证 Binance USD-M 公共接口读取有界闭合 K 线：

- 使用规范化 Instrument 到 CCXT Symbol 的映射；
- 网络调用有超时；
- 排除尚未闭合的 K 线；
- 不需要交易所 API Key；
- 当前没有 Owner Console 专用 K 线表或后台采集服务。

### 2.5 当前运行资源

Tokyo 主机只有 2C4G。Observation、Entry、Lifecycle 与 Reconciliation 四个持久 Worker 已共享一个 1 CPU、1GB 内存资源切片。Owner Console 必须保持低常驻成本，并与四个交易 Worker 的资源和失败边界隔离。

## 3. 产品目标

Owner Console 首版解决三个日常任务：

1. **运营扫描**：快速确认系统是否正常、是否需要 Owner 介入；
2. **交易因果**：理解一笔 Signal 如何进入或未进入 Ticket，以及 Ticket 如何完成保护、退出、结算和 Review；
3. **事实复盘**：把一笔终态 Ticket 的执行链、经济结果、退出原因和关注项压缩成可追溯结论。

Console 不把 Owner 变成内部 Gate 操作者，不要求 Owner 手工拼装事实，也不把交易执行流程迁移到前端。

## 4. 范围

### 4.1 首版范围

- 公网 HTTPS 域名；
- 单 Owner 用户名、密码与 TOTP 登录；
- 总览、信号、交易、复盘四个一级页面；
- 单笔交易因果详情；
- TradingView Lightweight Charts；
- PostgreSQL 类型化 Read Model；
- Binance 公共 K 线按需读取；
- 首次进入与手动刷新；
- Last Known Good 与局部错误状态；
- 逐 Ticket 规则型程序化复盘。

### 4.2 明确不在首版

- 自动刷新；
- WebSocket 或 SSE；
- SSR 或常驻 Node.js 服务；
- Redis；
- K 线持久化；
- 分析投影表和刷新 Worker；
- 策略排名、评分、推荐加仓或 Kill；
- 策略暂停/恢复 API；
- StrategyUniverse 修改 API；
- 受控平仓 API；
- 任何交易所写入入口。

## 5. 信息架构

### 5.1 一级导航

使用单层顶部导航：

```text
BRC OWNER   总览   信号   交易   复盘          PROD · 正常 · 数据时间
```

- 高度 40–44px；
- 当前页面使用黄色下划线；
- 不使用左侧导航栏；
- 不加入头像中心、租户切换、消息中心或工作区选择等 SaaS 元素；
- Owner Action 留在总览内容区，不进入全局导航。

### 5.2 二级页面

单笔 Ticket 使用：

```text
交易 / BNBUSDT LONG / ticket:4d927e…c4f48
```

提供：

- 返回交易列表；
- 上一笔 / 下一笔；
- 保留列表筛选上下文；
- 浏览器前进与后退语义。

## 6. 视觉系统

采用币安式暗色 Owner Console：

| Token | 值 | 用途 |
|---|---|---|
| 背景 | `#0B0E11` | 页面底色 |
| 内容层 | `#181A20` | 导航与主要内容面 |
| 次内容层 | `#11141A` | 表头、展开区和层级分组 |
| 分隔线 | `#2B3139` | 卡片与表格分隔 |
| 主文字 | `#EAECEF` | 主要信息 |
| 次文字 | `#848E9C` | 辅助信息 |
| 强调 | `#F0B90B` | 导航、选中与关注 |
| 正常/盈利 | `#0ECB81` | 正常、确认和正收益 |
| 异常/亏损 | `#F6465D` | 异常、阻断和负收益 |

字体规则：

- 正文采用 Inter / IBM Plex Sans 风格；
- 中文业务标签优先；
- Event、状态码和精确内部名保留英文；
- 金额、价格、时间、R 倍数和精确 ID 使用等宽数字。

布局规则：

- 常规页面最大内容宽度 1160px；
- 统一 12 列网格；
- 卡片上下边缘对齐；
- 间距主要使用 8px、12px、16px；
- 不使用大圆角、阴影和过量留白；
- 不使用右侧超长抽屉；
- 表格详情使用行内横向展开。

## 7. 页面设计

### 7.1 总览

首屏顺序：

```text
系统结论 + Owner Action
-> 账户权益 / 可用保证金 / Ticket 容量
-> 今日 Net PnL / Net R / Signals
-> 活动 Ticket
-> 机会与准入
-> 执行质量
-> 自动关注摘要
```

总览只区分：

- **需要介入**：安全、政策或恢复动作必须由 Owner 处理；
- **值得关注但无需介入**：需要复盘，但系统仍能正常完成流程；
- **无需操作**：当前运行与证据一致。

请求失败、数据陈旧或事实矛盾时，不允许继续生成新的“系统正常”结论。

### 7.2 信号

删除 Event × Instrument 当前机会矩阵。页面聚焦实际 Signal 与 AdmissionDecision：

```text
准入漏斗
-> AdmissionDecision 表格
-> 点击 Signal 行内展开
-> Admitted 跳转 Ticket
-> Rejected 展示第一阻塞点与 Shadow 摘要
```

行内展开固定回答：

1. 发生了什么；
2. 为什么没有 Ticket；
3. Shadow Outcome 摘要。

完整 Facts 和完整 Shadow 图表进入二级详情，不放入长抽屉。

### 7.3 交易

活动和终止 Ticket 使用同一张表。顶部汇总：

- Ticket 数；
- 活动数；
- Net PnL；
- Net R；
- Fees；
- Funding。

表格比较：

- 状态；
- 生命周期完成度；
- 退出原因；
- 经济结果；
- 关注项。

点击行先展示行内快速摘要，再进入独立单笔因果详情。

### 7.4 单笔交易因果工作台

采用三栏因果工作台：

```text
左侧：双层生命周期
中央：TradingView Lightweight Charts
右侧：当前阶段精确事实
底部：订单、经济结果、Incident、Event、Signal Facts
```

生命周期默认显示八个业务阶段：

```text
信号
准入与 Ticket
入场
保护
TP / Runner
退出
对账与结算
复盘
```

点击阶段后展开原始 Event、Command、耗时与异常。图表默认显示 Signal、ENTRY、Stop、TP 和 Exit；阶段切换时只补充当前阶段相关价格线与证据。

TradingView K 线只提供价格背景。Signal、订单与生命周期标记必须来自 PostgreSQL 精确身份。

### 7.5 复盘

复盘中心首版展示：

- 已完成 Ticket；
- Net PnL 与 Net R；
- Fees 与 Funding；
- 退出原因；
- 执行质量；
- Review 完整性；
- StrategyGroup 真实样本状态。

不显示全宽“样本不足”提示。证据限制仅在 StrategyGroup 局部显示 `Observe Only` 或 `No Evidence`。

首版不生成策略排名，也不把单笔交易结果提升为策略有效性判断。

## 8. 前端技术边界

首版建议：

```text
React + TypeScript + Vite 静态构建
TradingView Lightweight Charts
```

约束：

- 无 SSR；
- 生产环境无常驻 Node.js 进程；
- 静态资源由 HTTPS 反向代理提供；
- 浏览器只消费类型化 JSON API；
- 前端不计算 PnL、Net R、退出原因、Incident 状态或复盘分类；
- 浏览器不持有 PostgreSQL、交易所或系统管理凭证。

## 9. 只读 API 架构

```text
Owner Console
      ↓ JSON/HTTPS
单进程 Owner Read API
      ↓
类型化 Read Model Assembler
      ↓
有界 PostgreSQL 查询
```

K 线使用独立网络边界：

```text
图表请求
-> Owner Read API
-> CcxtBinancePublicMarketSource
-> Binance USD-M 公共 OHLCV
```

数据库读取与 Binance 网络 I/O 不在同一个数据库事务中等待。

### 9.1 页面接口

| 页面 | 接口 | 返回内容 |
|---|---|---|
| 总览 | `GET /api/owner/v1/overview` | 系统结论、资金、容量、今日结果、活动 Ticket、关注项 |
| 信号 | `GET /api/owner/v1/signals` | 准入漏斗、Signal、第一阻塞点、Shadow 摘要 |
| 信号详情 | `GET /api/owner/v1/signals/{signal_id}` | Facts、AdmissionDecision、Shadow Outcome |
| 交易列表 | `GET /api/owner/v1/tickets` | 活动与终止 Ticket、状态、经济结果、退出原因 |
| 因果详情 | `GET /api/owner/v1/tickets/{ticket_id}/causality` | 生命周期、命令、订单、结算、Review、图表标记 |
| 复盘 | `GET /api/owner/v1/review` | 完成交易、执行质量、退出原因、证据状态 |
| K 线 | `GET /api/owner/v1/market/candles` | 有界展示型 OHLCV |

### 9.2 查询边界

- 列表默认每页 50 条，硬上限 100 条；
- K 线默认最多 300 根，硬上限 500 根；
- Ticket 详情使用精确 `ticket_id`；
- Signal 详情使用精确 `signal_event_id`；
- 列表使用游标分页；
- 时间范围、StrategyGroup、Instrument、Side 和状态作为有界筛选；
- 不提供无边界全历史 API。

### 9.3 Read Model

首版核心类型：

```text
OwnerOverview
SignalListItem
SignalAdmissionDetail
TradeListItem
TradeCausalityDetail
LifecycleStageView
ChartAnnotation
ProgrammaticTradeReview
ReviewCenterSummary
```

每个页面主接口返回内部一致的页面快照。前端不分别获取多个指标后自行拼装业务结论。

页面 Read Model Assembler 使用一个短 PostgreSQL 只读事务读取该页面所需的内部事实，事务结束后再返回序列化结果。K 线等外部网络读取使用独立接口，不得在该数据库事务中等待。

### 9.4 响应信封

```json
{
  "snapshot_id": "01J...",
  "generated_at": "2026-08-05T10:42:08+08:00",
  "source_watermark": "2026-08-05T02:42:06.381Z",
  "freshness": "fresh",
  "data": {}
}
```

`freshness` 允许：

```text
fresh
stale
unavailable
contradictory
```

## 10. 手动刷新

Console 不执行任何自动刷新：

| 用户行为 | 请求行为 |
|---|---|
| 首次进入页面 | 请求一次页面数据 |
| 页面持续打开 | 不请求 |
| 返回已访问页面 | 显示浏览器内已有数据 |
| 点击“刷新当前页” | 重新请求当前页面 Read Model |
| 首次展开图表 | 请求一次 K 线 |
| 点击“刷新图表” | 重新请求 K 线 |
| 浏览器不可见 | 不请求 |

页面持续显示数据时间。数据年龄增加只改变时间文字或局部状态颜色，不触发后台请求，不出现全宽干扰提示。

请求失败时保留 Last Known Good。失败不能把一个活动 Ticket 显示成零，也不能把数据不可用解释为无 Signal、无 Incident 或系统正常。

## 11. K 线所有权

K 线首版采用后端按需读取 Binance 公共 OHLCV：

- 不持久化 PostgreSQL；
- 不创建行情 Worker；
- 不创建本地文件缓存；
- 浏览器内保留当前页面已加载 K 线，直到手动刷新或页面关闭；
- 同一页面同时最多一个 K 线请求；
- 网络超时建议 5 秒；
- K 线失败只影响图表背景，不影响 PostgreSQL 生命周期事实。

## 12. 程序化复盘模型

### 12.1 决策

首版使用确定性规则与固定文本模板：

```text
Ticket / Event / Command / Incident / Settlement / 当前 Review
-> 类型化事实
-> 确定性分类
-> 中文结论模板
```

不使用 LLM 生成自由文本，不把结论写回 Trade Review，不修改 Review revision 链。

### 12.2 前置条件

- 活动 Ticket 不生成最终复盘结论；
- Settlement 尚未完成时只显示当前阶段；
- Aggregate 没有当前有效 `review_id` 时显示“等待 Review”；
- Review 经济证据缺失或矛盾时不补造数值；
- 只有终态 Ticket 与当前有效 Review 才能生成完整结论。

### 12.3 固定问题

每笔复盘只回答：

1. 执行链是否按设计完成；
2. 经济结果由什么构成；
3. 退出由什么明确事实触发；
4. 是否存在需要关注的执行偏差。

### 12.4 执行链分类

| 分类 | 条件 | 结论 |
|---|---|---|
| 完整执行 | ENTRY、保护、退出、对账、结算、Review 完整且无 Incident | 执行链完整，无异常 |
| 已恢复异常 | 有 Incident，但已按官方路径恢复并终态 | 列出异常与恢复事实 |
| 证据不完整 | Review、Funding、外部退出成交或关键命令事实缺失 | 不生成完整经济结论 |
| 仍在进行 | Ticket 尚未终态 | 只显示当前阶段 |

### 12.5 经济结果

```text
Gross PnL
- Fees
± Funding
= Net PnL

Net PnL / 冻结初始止损风险
= Net R
```

Funding 不可归因时，显示明确原因，不把 Funding 当作零，也不计算依赖完整 Funding 的 Net PnL 和 Net R。

### 12.6 退出原因

退出原因必须来自明确的 Lifecycle Event、EXIT Command 或外部平仓事实。K 线形态不能独立产生退出原因。

允许的事实性标签包括：

```text
Initial Stop
TP1 + Runner Exit
Controlled Exit
External Flat / Exit Fills Unavailable
```

`Failed Breakout`、`Failed Breakdown` 等策略结构标签，只有冻结策略事实或生命周期事实已明确记录时才展示。

### 12.7 关注项

允许提示：

- 保护确认超过其已有命令时限或形成 Incident；
- 实际止损风险高于冻结计划；
- Funding 不可归因；
- Unknown Outcome 或 Incident；
- 在订单归因完整时，Runner 净贡献小于或等于零。

不允许提示：

- 策略有效或无效；
- 应增加或减少仓位；
- 下一笔应继续使用；
- 单笔结果支持 Kill；
- 未由权威事实支持的价格行为解释。

### 12.8 结论示例

完整交易：

```text
执行链完整。ENTRY 后初始保护已确认；退出由 TP1 后 Runner EXIT 触发。
Net PnL 为 +3.51 U，Net R 为 +0.48R；订单、费用、Funding 与 Review 证据完整。
```

证据不完整：

```text
Ticket 已终态，但外部平仓成交事实不可获得；因此不计算 Net PnL 与 Net R。
生命周期事实保留，经济结论标记为不完整。
```

## 13. 登录与 Session

### 13.1 身份模型

只有一个 Owner 身份：

```text
用户名
+ Argon2id 密码哈希验证
+ RFC 6238 TOTP 验证
= Owner Session
```

Google Authenticator 是 TOTP 客户端，不使用 Google OAuth。

### 13.2 凭证存储

为避免首版因登录引入 Trading Kernel 数据库 Migration：

- Owner 用户名、Argon2id 密码哈希、TOTP Seed 和 Session 签名密钥通过独立 systemd encrypted credentials 提供；
- 不放入仓库、前端构建产物或普通日志；
- Read API 使用 PostgreSQL 只读数据库账号；
- Read API 不加载 Binance 私有 API Key。

首版不提供公网找回密码或跳过 TOTP 的恢复入口。Owner 丢失认证设备时，必须通过服务器运维路径替换 encrypted credentials、旋转 Session 签名密钥并重启 Read API；该操作使全部现有 Session 失效。

### 13.3 Session 安全

- `HttpOnly`；
- `Secure`；
- `SameSite=Strict`；
- 登录成功后旋转 Session ID；
- Session 空闲 30 分钟失效，绝对有效期最长 12 小时；
- 服务重启或 Session 签名密钥轮换使现有 Session 失效；
- TOTP 使用 30 秒时间步，只接受当前时间步及相邻一个时间步；
- 同一账号或来源 IP 在 15 分钟内最多失败 5 次，达到上限后冷却 15 分钟；
- 错误提示不暴露用户名是否存在；
- 所有 API 请求验证 Owner Session；
- HTTPS 反向代理向 API 传递可信来源信息，API 不信任公网客户端自行提供的转发头。

未来控制操作必须支持重新输入 TOTP，并记录不可变 Owner Authorization。

## 14. 部署与资源

首版运行模型：

```text
HTTPS 反向代理
├── 静态前端文件
└── 单进程 Owner Read API

Trading Kernel
├── Observation
├── Entry
├── Lifecycle
└── Reconciliation
```

Owner Read API 与四个交易 Worker 使用独立 systemd unit 和资源边界。初始设计预算：

| 资源 | 上限 |
|---|---:|
| API 进程 | 1 |
| CPUQuota | 25% |
| MemoryMax | 256MB |
| TasksMax | 32 |
| PostgreSQL 连接池 | 最多 2 个连接 |
| 后台任务 | 0 |

这些是实施阶段必须验证的预算，不是当前实测结果。若 API 超出预算，首选减少依赖、查询和常驻对象，不扩大交易 Worker 的共享资源切片。

## 15. 未来 Owner Control Plane

该章节只冻结边界，不授权首版实现。

### 15.1 StrategyGroup 暂停与恢复

暂停仅阻断该 StrategyGroup 的新准入，不停止 Observation，也不影响已有 Ticket 的保护、退出、对账、Settlement 与 Review。全局 `new_entry_submit_enabled` 继续只表示全局新 ENTRY 权限，不能代替单 StrategyGroup 暂停语义。

### 15.2 Instrument / StrategyUniverse 变更

不允许原地修改 Active StrategyUniverse：

```text
创建新版本
-> 只读认证
-> Warming（零 Signal）
-> 原子激活
-> 旧版本退休
```

已有 Signal 与 Ticket 保持冻结 Universe version/digest。

### 15.3 受控退出

受控退出虽然不是人工指定订单，但最终会产生交易所 reduce-only EXIT Command，因此属于高风险交易 mutation。

未来默认边界：

```text
Owner 重新输入 TOTP
-> 写入不可变 Owner Authorization
-> 对完整有界 Active Ticket 集执行只读分类
-> 通过 request_exit() 请求退出
-> Lifecycle Worker 持久化并派发 EXIT Command
-> Reconciliation 确认外部全平并完成清理、Settlement、Review
```

前端与 Control API 不允许提供数量、价格、订单类型或直接交易所写入。扩展现有 `deployment_drain` 之外的授权 purpose 需要独立设计、测试与 Owner 明确批准。

## 16. 错误处理

### 16.1 页面数据失败

- 保留 Last Known Good；
- 显示最后成功时间与错误时间；
- 不自动重试；
- 用户手动刷新时重新请求；
- 无有效快照时显示局部 `Unavailable`，不伪造空列表。

### 16.2 K 线失败

- 图表区域显示公共行情不可用；
- 保留 Signal、订单、生命周期、Settlement 和 Review 标记；
- 不把图表失败提升为交易系统异常。

### 16.3 事实矛盾

- 标记 `Contradictory`；
- 不生成程序化业务结论；
- 展示精确矛盾来源与身份；
- 只读请求不修复或刷新任何 Runtime Projection。

### 16.4 认证失败

- 不建立 Session；
- 登录失败次数有界记录与限速；
- TOTP 时间窗口保持最小兼容范围；
- 认证故障不能影响交易 Worker。

## 17. 测试设计

### 17.1 架构测试

- 前端不存在数据库、Binance 私有凭证或交易所 mutation 代码；
- Read API 不导入或调用交易所写入边界；
- 首版除登录与登出外不存在业务 write endpoint；
- 不存在自动刷新 timer、WebSocket、SSE、Redis 或行情 Worker；
- 不创建生成式 JSON/Markdown Runtime 文件。

### 17.2 Read Model 单元测试

- 金额、Decimal、时间与 identity 精确序列化；
- 活动 Ticket 不生成最终复盘；
- Review revision 使用 Aggregate 当前指针；
- Funding 缺失不按零处理；
- 外部退出成交缺失不生成 PnL；
- Exit reason 不能由 K 线猜测；
- Incident 恢复与未恢复状态分类正确；
- `fresh`、`stale`、`unavailable`、`contradictory` 映射正确。

### 17.3 PostgreSQL 集成测试

- 页面查询有界；
- 列表游标稳定；
- 页面快照内部一致；
- 精确 Ticket 与 Signal 身份隔离；
- 查询无写副作用；
- 读请求不创建或刷新 Owner Projection；
- 连接池不超过配置上限。

### 17.4 前端测试

- 顶部导航与二级路由；
- 行内展开；
- 列表筛选上下文返回；
- 手动刷新；
- Last Known Good；
- 响应式降级；
- 无自动网络请求；
- 复盘页无全局样本不足横幅；
- 活动 Ticket 无最终复盘文案。

### 17.5 认证测试

- 正确密码仍需 TOTP；
- 错误密码和错误 TOTP 使用相同外部错误语义；
- Session Cookie 属性正确；
- Session fixation 防护；
- 登录限速；
- 服务重启或 Session 密钥轮换后 Session 失效；
- 缺失或错误 systemd credential 时 fail closed；
- 未认证请求不能读取任何 Owner API。

### 17.6 性能验证

- API idle RSS 不超过配置 `MemoryMax` 的 80%；
- 空闲 CPU 接近零且没有轮询；
- 手动页面读取使用有界 SQL；
- K 线请求最多一个外部调用和 500 根数据；
- 静态前端不需要 Node.js 常驻进程；
- Read API 失败或资源限制触发不影响四个 Trading Kernel Worker。

## 18. Migration、部署与回退

### 18.1 首版 Migration

首版读模型和认证不新增 PostgreSQL 表：

- Read Model 按需生成；
- 登录凭证使用 systemd encrypted credentials；
- K 线按需读取；
- 无分析投影；
- 无双写或兼容 Reader。

### 18.2 部署顺序

```text
本地测试与静态构建
-> 部署 Read API（仅 loopback / 私网）
-> 验证只读数据库身份
-> 部署静态资源
-> 配置 HTTPS 与域名
-> 安装 Owner encrypted credentials
-> 验证登录、TOTP 和未认证阻断
-> 验证资源边界与 Trading Kernel 无影响
```

部署 Owner Console 不要求停止、迁移或修改四个 Trading Kernel Worker。

### 18.3 回退

- 停止并禁用 Owner Read API；
- 从反向代理移除 Console 路由；
- 保留或删除静态资源均不影响运行权威；
- 无数据库回滚；
- 不恢复任何旧 Frontend 或替代执行链。

## 19. 实施分期

### Phase 1：只读 Owner Console

- HTTPS、密码、TOTP 与 Session；
- 四个一级页面与交易详情；
- 页面级 Read Model；
- 手动刷新；
- Binance 公共 K 线；
- 规则型逐 Ticket 复盘；
- 测试与 2C4G 资源验证。

### Phase 2：Owner 运营控制

- StrategyGroup 暂停与恢复；
- StrategyUniverse 新版本草稿、认证、Warming 与激活；
- 不包含受控退出。

### Phase 3：受控退出

- 新 Owner Authorization purpose；
- TOTP 重新认证；
- 完整 Active Ticket 集分类；
- Kernel `request_exit()` 边界；
- EXIT、Reconciliation、Settlement 与 Review 全链测试；
- 独立 Owner 批准与生产安全评审。

## 20. 验收标准

首版完成必须同时满足：

1. 四个一级页面和单 Ticket 因果详情可通过公网 HTTPS 登录后访问；
2. 未认证用户无法读取任何 Owner 数据；
3. 登录必须同时通过密码与 TOTP；
4. 页面无自动刷新，所有后续更新由 Owner 手动触发；
5. 所有列表、详情与 K 线请求有明确硬上限；
6. 前端不计算业务结论；
7. 每句程序化复盘都能回链至 Ticket、Event、Command、Incident、Settlement 或当前 Review；
8. 缺失经济事实不被解释为零；
9. K 线失败不影响 PostgreSQL 因果事实；
10. 首版除登录与登出外不存在策略控制、运行状态修改或交易所写入 API；
11. API 资源消耗符合独立 systemd 预算；
12. Owner Console 故障不影响 Observation、Entry、Lifecycle 与 Reconciliation；
13. 不新增 PostgreSQL Migration、后台 Worker、Redis、WebSocket、SSE 或文件权威；
14. 复盘页不显示全宽样本不足提示，不生成小样本策略排名。

## 21. 已拒绝方案

- 左侧 SaaS 导航；
- Event × Instrument 当前机会矩阵；
- 右侧超长详情抽屉；
- 全宽小样本提示；
- 前端直连 PostgreSQL；
- 前端直接请求 Binance 私有接口；
- PostgreSQL K 线表和后台采集；
- 自动刷新、WebSocket 和 SSE；
- Next.js SSR 常驻服务；
- 持久化分析投影与刷新 Worker；
- LLM 自由文本复盘；
- 前端根据 K 线推断退出原因；
- 首版策略控制和受控退出；
- 前端或 Control API 直接创建交易所订单。
