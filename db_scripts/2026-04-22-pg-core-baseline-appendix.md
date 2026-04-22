# PG 核心表设计附录

> 日期：2026-04-22
> 对应基线脚本：`db_scripts/2026-04-22-pg-core-baseline.sql`

---

## 1. 目的

本附录用于解释第一波 PostgreSQL 核心表迁移的目标设计基线，作为后续实现的架构约束与审核依据。

本轮只覆盖三张核心表：

1. `orders`
2. `execution_intents`
3. `positions`

---

## 2. 总体原则

### 2.1 不是 1:1 搬 SQLite 表

本轮迁移不是把 SQLite 历史表结构原样复制到 PG，而是借迁移窗口同步修正明显不合理设计。

### 2.2 统一基础类型口径

1. 金额 / 价格 / 数量：统一 `NUMERIC(30,8)`
2. 布尔：统一 `BOOLEAN`
3. 时间：统一 `BIGINT` 毫秒时间戳

### 2.3 当前不跨库做外键

`signals` 当前仍在 SQLite，因此 `orders.signal_id`、`execution_intents.signal_id`、`positions.signal_id` 暂时只作为逻辑引用，不在数据库层加外键。

### 2.4 迁移时同步补最小约束

至少补齐：

1. 非空约束
2. 正数/非负数约束
3. 状态/角色合法值约束
4. 必要唯一索引
5. 按真实查询路径建立的查询索引

---

## 3. `orders` 设计说明

### 3.1 目标定位

`orders` 是核心执行链真源，必须强收口，不能继续延续 SQLite 宽松表设计。

### 3.2 相对 SQLite 的主要优化

1. `price / trigger_price / requested_qty / filled_qty / average_exec_price` 不再使用 `TEXT`
2. `requested_qty > 0`
3. `filled_qty >= 0 AND filled_qty <= requested_qty`
4. `exchange_order_id` 增加部分唯一索引
5. `parent_order_id` 显式建自引用关系

### 3.3 当前保留为字符串 + CHECK 的字段

以下字段本轮暂不引入 PostgreSQL ENUM，而是采用 `TEXT + CHECK`：

1. `direction`
2. `order_type`
3. `order_role`
4. `status`

原因：

1. 迁移期改动面更小
2. Python 侧枚举与数据库侧约束仍然能保持一致
3. 比 PostgreSQL ENUM 更便于后续小步演进

### 3.4 本轮故意不做

1. 不对 `signal_id` 做数据库外键
2. 不引入复杂 OCO 完整性约束
3. 不为所有业务查询场景预埋组合索引，只补核心执行链高频路径

---

## 4. `execution_intents` 设计说明

### 4.1 目标定位

`execution_intents` 用于替代当前 orchestrator 的内存真源，必须做到“一次成型”，避免继续补内存态补丁。

### 4.2 关键设计

1. `signal_payload JSONB NOT NULL`
2. `strategy_payload JSONB`
3. `blocked_message TEXT`
4. 同时保留以下反规范化列：
   - `symbol`
   - `status`
   - `order_id`
   - `exchange_order_id`
   - `blocked_reason`
   - `blocked_message`

### 4.3 这么设计的原因

1. `SignalResult` 和策略快照结构天然更适合按对象存储
2. 如果强行拆成很多子列，迁移初期会放大 schema 演进成本
3. 仅依赖 JSONB 查询又不利于恢复和状态轮询，因此保留关键检索列
4. 当前领域模型和拦截链路仍显式区分 `blocked_reason` 与 `blocked_message`，本轮保留两者，避免迁移时丢失拦截上下文

### 4.4 本轮故意不做

1. 不拆成多表
2. 不引入复杂 recovery graph
3. 不提前建过多 JSONB 表达式索引

---

## 5. `positions` 设计说明

### 5.1 目标定位

`positions` 本轮采用“稳定核心列 + 扩展载荷”的过渡方案，不在这一轮强行完成全部领域模型扁平化。

### 5.2 核心列

本轮只固化最稳定的持仓字段：

1. `symbol`
2. `direction`
3. `quantity`
4. `entry_price`
5. `mark_price`
6. `leverage`
7. `unrealized_pnl`
8. `realized_pnl`
9. `is_closed`
10. `opened_at`
11. `closed_at`
12. `updated_at`

### 5.3 扩展载荷

复杂或尚未稳定的持仓字段先落到：

- `position_payload JSONB`

这样做的原因：

1. 避免把当前 SQLite / ORM 双轨差异强行扁平化
2. 避免 `PositionManager` 在本轮被迫大改
3. 给后续二次收口保留空间

### 5.4 本轮故意不做

1. 不一次映射全部 trailing / TP 原始价格等复杂字段
2. 不在本轮重构 `PositionManager`
3. 不承诺当前 `positions` schema 已是最终形态

---

## 6. 本轮审核重点

审核这份基线时，建议优先看以下问题：

1. 三张表的字段类型口径是否统一
2. `orders` 的状态/角色集合是否完整
3. `execution_intents` 的状态集合是否足够支撑当前执行链
4. `positions` 的过渡方案是否过轻或过重
5. 当前索引是否覆盖核心执行链真实查询路径

---

## 7. 实现约束

后续实现 `pg_models.py`、PG repository、连接验证时，必须遵守：

1. 不允许脱离本附录随意新增/删减核心字段
2. 若实现中发现基线不够，需要先回到设计层修正，再继续编码
3. 若本轮故意不修某个设计债，必须在实现输出里显式说明原因
