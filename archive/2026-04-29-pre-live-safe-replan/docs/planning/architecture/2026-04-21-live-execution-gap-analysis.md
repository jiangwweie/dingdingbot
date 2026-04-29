# 实盘执行链风险与缺失功能分析

> 日期：2026-04-21
> 阶段定位：当前仍为**回测优化阶段**，本文档为后续测试盘/实盘准备的架构备忘
> 使用方式：当前不作为主任务执行清单，只作为后续进入实盘阶段前的专项核对材料

---

## 一、结论摘要

当前系统已经具备较完整的实盘组件基础：

- `ExchangeGateway`：真实下单/撤单、订单推送、成交数量推进
- `OrderLifecycleService`：订单状态机、审计日志、状态推进
- `OrderRepository`：订单持久化与订单链追踪
- `ReconciliationService`：启动对账、孤儿单/幽灵单处理
- `CapitalProtectionManager`：下单前资金保护与参数合理性检查

但系统当前的主要风险不在“有没有这些组件”，而在：

**自动执行主链尚未完全收口为单一、稳定、可验证的闭环。**

换句话说，当前更像：

- 回测链路完整
- 实盘组件齐备
- 但“信号 -> 下单 -> 成交 -> 保护单 -> 仓位 -> 对账”的统一编排器不够清晰

因此，后续一旦从回测优化切到测试盘准备，优先级应先落在执行链收口，而不是继续扩展更多策略参数。

---

## 二、当前观察到的系统风险

### 2.1 执行入口分裂

当前至少存在两条较明显的主线：

- `main.py -> SignalPipeline`
  - 偏实时监控、信号处理、通知、状态更新
- `api.py -> ExchangeGateway / OrderLifecycleService`
  - 偏订单管理、手工/接口下单、订单生命周期

风险在于：

- 系统可能同时具备“会看信号”和“会下订单”的能力
- 但未必由同一条主链统一驱动
- 一旦未来接自动执行，容易出现逻辑散落在多个入口中，难以保证一致性

### 2.2 API 下单路径可能先打交易所，再补本地状态

当前 API 下单入口 `POST /api/v3/orders` 看起来直接调用：

- `gateway.place_order(...)`

而不是明确先走：

- `OrderLifecycleService.create_order()`
- 本地落库
- `submit_order()`
- 再提交交易所

风险在于：

- 交易所已有订单，但本地状态链未必完整
- 后续 WebSocket 回写、订单树、审计日志、对账恢复都会依赖“本地先存在订单”

### 2.3 WebSocket 回写协议需要专项核对

当前架构里：

- `ExchangeGateway` 注册了全局订单回调
- `OrderLifecycleService` 提供 `update_order_from_exchange(...)`

但需要重点核对：

- `ExchangeGateway` 回调给出的对象/参数格式
- 是否与 `OrderLifecycleService.update_order_from_exchange()` 的签名完全匹配
- 中间是否存在适配层

### 2.4 ENTRY 成交后保护单闭环不清晰

回测里这一段是完整的：

- ENTRY 成交
- 基于实际成交价生成 TP/SL
- OCO 与剩余数量同步

实盘里需要同样明确的链路：

- ENTRY fill event
- 读取实际成交均价/成交量
- 生成 TP/SL
- 提交 TP/SL 到交易所
- 等待 TP/SL 被交易所确认挂单

当前风险不是“系统做不到”，而是：

- 这条链的统一入口和主控点还不够清晰

### 2.5 Position / Order / Reconciliation 的单一真源不足够明确

当前系统同时存在：

- OrderRepository
- PositionManager
- ExchangeGateway WebSocket 更新
- ReconciliationService

这些组件各自都在推进状态，但需要更清楚地定义：

- 订单状态以谁为准
- 仓位状态由谁主导更新
- 对账是“兜底修复”还是“日常常态同步”

### 2.6 CapitalProtection 可能只覆盖 API 下单，而未必覆盖未来内部自动执行

`CapitalProtectionManager` 的能力本身较完整，但当前主要看到它挂在 API 下单前置检查。

如果未来自动执行链不是通过 API 触发，而是内部服务直接下单，则存在风险：

- API 受保护
- 自动执行链却可能绕开保护

### 2.7 订单与信号的绑定协议较脆弱

当前系统里订单、信号、交易所订单可能通过以下字段关联：

- `signal_id`
- `client_order_id`
- `exchange_order_id`

其中 `clientOrderId -> signal_id` 的映射尤其关键。若协议不统一，会影响订单树、TP/SL 继承关系、对账导入与归因一致性。

---

## 三、当前缺失的关键功能

### 3.1 统一的自动执行编排器

系统当前缺少一个明确的 orchestrator，把以下流程统一起来：

1. Signal Fired
2. Capital Protection Check
3. Create Local Order
4. Submit to Exchange
5. Receive WS/REST Update
6. ENTRY Filled
7. Generate TP/SL
8. Submit TP/SL
9. Update Position State
10. Reconcile if needed

### 3.2 实盘版 `handle_order_filled` 闭环

回测里已经有：

- `ENTRY filled -> handle_order_filled -> TP/SL`

实盘需要同样明确的一条自动链，而不是散在 WebSocket 回调、API 层、手工触发、对账补偿之间。

### 3.3 保护单提交状态机

不仅要“生成 TP/SL 订单对象”，还需要完整状态：

- generated
- submitted
- open
- partially_filled
- filled
- canceled
- rejected
- recovered_after_restart

### 3.4 自动执行模式的运行时入口

当前系统建议后续明确区分运行模式，例如：

- `monitor_only`
- `paper_execution`
- `live_execution`

这样可以避免 `main.py` 既像监控器又像执行器，API 与后台任务对系统边界理解不一致。

---

## 四、对当前阶段的建议

### 4.1 当前不切主线

当前仍处于回测优化阶段，因此建议：

- 不把这些实盘风险问题直接上升为当前主任务
- 只做文档化与风险清单沉淀
- 保留到“测试盘准备阶段”集中处理

### 4.2 进入测试盘前的最低门槛

后续如果进入测试盘准备，建议最低先补齐：

1. 统一执行入口
2. ENTRY fill -> TP/SL 自动挂载闭环
3. WS 回写协议核对
4. Local Order / Position / Reconciliation 单一真源规则
5. CapitalProtection 在自动执行链上的统一接入

---

## 五、建议的后续收口顺序（未来阶段）

### 阶段 L1：协议核对

- 核对 API 下单、本地生命周期、WebSocket 回写三者协议
- 确认 `signal_id / client_order_id / exchange_order_id` 的单一规则

### 阶段 L2：执行 orchestrator

- 增加统一执行编排器
- 把 Signal -> Entry -> Protection -> Position 串起来

### 阶段 L3：保护单闭环

- ENTRY fill 后自动生成并提交 TP/SL
- 明确保护单空窗监控

### 阶段 L4：状态一致性

- 明确 Order / Position / Reconciliation 的真源关系
- 定义恢复优先级

### 阶段 L5：测试盘验收

- 再开始按真实成交表现校准回测参数

---

## 六、数据库迁移评估（SQLite -> PostgreSQL）

### 6.1 当前数据库形态不是单一栈，而是双栈过渡态

当前代码库并不是“全部 SQLite”或“已经全部 ORM 化”，而是明显处于双栈并存阶段：

- 一批历史/配置/回测相关仓库仍大量使用 `aiosqlite + 原始 SQL`
- 一批 v3 / 实盘关键链路已经开始使用 `SQLAlchemy async + DATABASE_URL` 抽象

具体观察：

- `src/infrastructure/database.py`
  - 已明确把开发默认值设置为 `sqlite+aiosqlite:///./data/v3_dev.db`
  - 注释里已预留“生产环境使用 PostgreSQL”的方向
- `src/infrastructure/v3_orm.py`
  - 已建立 SQLAlchemy 2.0 async ORM 模型
- `src/application/position_manager.py`
  - 已显式区分 SQLite / PostgreSQL，并在 PostgreSQL 下使用 `SELECT ... FOR UPDATE`
- 但以下模块仍深度依赖 SQLite 语义：
  - `src/infrastructure/connection_pool.py`
  - `src/application/reconciliation_lock.py`
  - `src/infrastructure/order_repository.py`
  - `src/infrastructure/signal_repository.py`
  - `src/infrastructure/backtest_repository.py`
  - `src/application/config_manager.py`
  - `src/application/config/config_repository.py`
  - 多个 `config_*_repository.py`

结论：

**数据库层已经为 PostgreSQL 预留了方向，但尚未完成从 SQLite 主导到 SQLAlchemy/PG 主导的收口。**

### 6.2 当前切库成本判断：中等，可控，但不适合现在就全面切

如果问“SQLite 切 PostgreSQL 成本高不高”，我的判断是：

- **不是低成本换连接串**
- **也不是灾难级重构**
- 更准确地说，是一次**中等成本的渐进式基础设施迁移**

成本主要不在 ORM 模型本身，而在 SQLite 特有假设已经渗入不少基础模块：

1. **连接池完全是 SQLite 专用实现**
- `src/infrastructure/connection_pool.py`
- 这里的核心是 `aiosqlite.Connection` 复用 + `PRAGMA journal_mode=WAL / busy_timeout / cache_size`
- 这些优化和语义都不能直接迁移到 PostgreSQL

2. **对账锁实现直接绑定 `sqlite3`**
- `src/application/reconciliation_lock.py`
- 当前锁机制依赖本地 SQLite 表 + `INSERT OR REPLACE` + 过期时间抢锁
- 这部分迁移到 PostgreSQL 时，应该重新设计为：
  - 行锁方案
  - 或 advisory lock 方案
- 这不是“兼容性修补”，而是需要重写

3. **多个仓库显式使用 SQLite 元信息与行对象**
- 多处使用：
  - `aiosqlite.Row`
  - `PRAGMA table_info(...)`
  - `sqlite_master`
- 这些都说明仓库层并未完全数据库无关化

4. **历史上对 SQLite 锁冲突做过专门优化**
- 例如集中连接池、WAL、busy timeout
- 这些优化在 PostgreSQL 中不再成立，反而需要切换到新的连接池与事务设计

### 6.3 为什么我更建议 PostgreSQL，而不是 MySQL

如果未来进入自动执行测试盘阶段，需要从 SQLite 升级，我仍然更建议：

- **优先 PostgreSQL**
- **不是优先 MySQL**

原因不是抽象的“PG 更高级”，而是和当前仓库结构更贴合：

1. `SQLAlchemy async` 路径已经成形
- 当前 v3 关键链路已经在朝 SQLAlchemy async 收敛
- PostgreSQL 会更顺滑地承接事务、行锁、状态机型写入

2. 系统后续重点是状态一致性，不是普通 CRUD
- 订单生命周期
- 仓位并发更新
- 对账恢复
- 审计日志
- 这些场景天然更依赖明确事务边界和锁语义

3. 现有代码已经显式预留 PostgreSQL 分支
- `PositionManager` 中已经对 PostgreSQL 的 `with_for_update()` 做了判断
- 这说明当前设计思路本身就在向 PG 靠拢

结论：

**如果未来要升库，MySQL 不会显著降低当前迁移成本；PostgreSQL 更符合现有代码的演进方向。**

### 6.4 好消息：现在迁移比以后迁移更容易

虽然当前不能说“切库很便宜”，但也有一个很重要的正面判断：

**现在做迁移规划，成本明显低于等自动执行链彻底铺开后再迁移。**

原因：

- 自动执行主链还没最终收口
- 订单 / 仓位 / 对账的真源规则还在梳理期
- 趁这个阶段先决定“未来实盘关键路径走 PG”，后面返工会少很多

也就是说：

- **现在立即全面切库**：不合时机
- **现在不做迁移设计，等实盘再说**：未来代价会更高

### 6.5 建议的渐进式迁移路径

结合当前项目阶段，我更建议下面这条路径，而不是一次性全量替换：

#### 阶段 DB-1：先定义边界，不先动全库

先明确哪些数据属于未来“实盘关键路径”：

- orders
- positions
- order_audit_logs
- reconciliation / lock / execution state

而以下数据可以继续暂留 SQLite 更久：

- backtest reports
- strategy optimizer 数据
- 历史配置快照
- 一般信号归档

#### 阶段 DB-2：优先迁移实盘关键链路到 SQLAlchemy + DATABASE_URL

优先把未来测试盘/实盘必经路径收敛到统一数据库抽象：

- OrderLifecycleService 依赖的持久化
- PositionManager
- OrderAuditLogRepository
- Reconciliation 相关状态

目标不是“全项目切库”，而是：

**让自动执行闭环先脱离 SQLite 特有实现。**

#### 阶段 DB-3：重写对账锁，而不是硬兼容

`src/application/reconciliation_lock.py` 建议不要做“SQLite/PG 双兼容补丁式演进”，而是后续直接重构为：

- PostgreSQL advisory lock
- 或基于事务行锁的统一实现

这是迁移中的关键点之一。

#### 阶段 DB-4：保留回测与研究链路继续使用 SQLite 一段时间

当前主线仍是回测优化，因此没有必要为了数据库统一而打断研究效率。

更现实的路径是：

- 回测/研究链继续 SQLite
- 测试盘/实盘链逐步转向 PostgreSQL

后续再看是否需要彻底统一。

### 6.6 对当前阶段的结论

对于“现在要不要切 PostgreSQL”这个问题，我的建议是：

1. 当前**不立即执行全量迁移**
2. 但在架构层面，应明确：
   - **未来实盘关键路径默认以 PostgreSQL 为目标**
3. 后续进入测试盘准备阶段时，把数据库迁移列为专项收口任务，而不是临时起意切换

一句话总结：

**SQLite 继续支撑当前回测优化没有问题；但如果后续要进入自动执行测试盘，数据库演进方向应优先定为 PostgreSQL，并采用“实盘关键链路先迁、回测研究链路后迁”的渐进方案。**

---

## 七、结语

当前系统最需要警惕的，不是“没有实盘能力”，而是：

**实盘能力已经分散存在于多个组件中，但自动执行主链还没完全收成一条单一、稳定、可审计的执行闭环。**

这件事现在先记录，不抢占回测优化主线；但未来一旦进入测试盘准备，它应当成为优先级最高的工程收口任务之一。
