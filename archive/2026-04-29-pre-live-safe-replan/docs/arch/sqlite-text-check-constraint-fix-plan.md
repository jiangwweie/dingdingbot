# ADR-2026-0414-SQLITE-CHECK: SQLite TEXT 列 CHECK 约束字典序比较 Bug 修复

**状态**: Proposed
**日期**: 2026-04-14
**编号**: ADR-2026-0414-SQLITE-CHECK
**关联 Issue**: 回测负收益率报告无法保存

---

## 背景

### 问题描述

回测引擎正常产生 41 笔交易，其中包含负收益报告（如 `total_return = -0.1787`），但报告无法保存到数据库。

### 根因分析

**直接原因**: `src/infrastructure/v3_orm.py:1167` 的 CHECK 约束：

```python
CheckConstraint(
    "total_return >= -1.0 AND total_return <= 10.0",
    name="check_total_return_range"
)
```

`total_return` 列使用 `DecimalField(32)` 即 `DecimalString`，在 SQLite 中以 **TEXT** 存储。
SQLite 的 CHECK 约束对 TEXT 列做 **字典序比较**（lexicographic），而非数值比较：

```
字典序:  '-0.1787' >= '-1.0'  -->  False (因为 '0' < '1')
数值序:   -0.1787  >=  -1.0    -->  True
```

因此负收益率在字典序比较中被拒绝，而正数（如 `'0.1595' >= '-1.0'` 为 True）能通过。

### 触发链

1. 回测引擎运行，产生 41 笔交易，`total_return = Decimal('-0.1787')`
2. `save_report()` 尝试 INSERT 到 `backtest_reports` 表
3. SQLite 对 CHECK 约束做字符串比较：`'-0.17' >= '-1.0'` = **False**
4. INSERT 违反 CHECK 约束，行被拒绝
5. 数据库中仅保留 `total_return='0'` 的旧记录（`'0' >= '-1.0'` = True）

### 证据

| 测试值 | 字符串比较结果 | 数值比较结果 | 实际 INSERT |
|--------|--------------|-------------|-------------|
| `'0.1595'` | `>= '-1.0'` = True | 0.1595 >= -1.0 = True | OK |
| `'0'` | `>= '-1.0'` = True | 0 >= -1.0 = True | OK |
| `'-0.1787'` | `>= '-1.0'` = **False** | -0.1787 >= -1.0 = True | **FAIL** |

修复验证：使用 `CAST(total_return AS REAL) >= -1.0` 后，负数 INSERT OK。

### 设计历史

`SignalORM` 和 `AccountORM` 等模型在设计时已意识到此问题：

```python
# v3_orm.py:439 -- SignalORM 有意避开数值 CHECK 约束
# 注意：SQLite 对 TEXT 字段使用字典序比较，因此不使用 CHECK 约束进行数值比较
# 数值验证应在应用层（Pydantic）进行
# 保留枚举 CHECK 约束（字符串字面量比较）
```

但 `BacktestReportORM`、`OrderORM`、`PositionORM` 在添加 CHECK 约束时未考虑此问题。

---

## 全量扫描结果

### 1. DecimalString 列 + 数值比较 CHECK 约束（**有问题**）

以下约束在 TEXT 列上做数值比较，字典序与数值序不一致，**存在潜在风险**：

| 模型 | 约束名 | CHECK 表达式 | 列类型 | 风险等级 | 实际触发? |
|------|--------|-------------|--------|---------|----------|
| **BacktestReportORM** | `check_total_return_range` | `total_return >= -1.0 AND total_return <= 10.0` | TEXT | **P0-已触发** | YES -- 负收益合法 |
| **BacktestReportORM** | `check_win_rate_range` | `win_rate >= 0.0 AND win_rate <= 1.0` | TEXT | P2-未触发 | 正常值 0~1，`'0.8' >= '0.0'` = True |
| **BacktestReportORM** | `check_max_drawdown_range` | `max_drawdown >= 0.0 AND max_drawdown <= 1.0` | TEXT | P2-未触发 | 正常值 0~1，`'0.3' >= '0.0'` = True |
| **OrderORM** | `check_requested_qty_positive` | `requested_qty > 0` | TEXT | P2-有防护 | Pydantic 验证 + `DecimalField` 不会传负数 |
| **OrderORM** | `check_filled_qty_non_negative` | `filled_qty >= 0` | TEXT | P2-有防护 | `default=Decimal('0')` + Pydantic 验证 |
| **PositionORM** | `check_current_qty_non_negative` | `current_qty >= 0` | TEXT | P2-有防护 | 应用层确保非负 |
| **PositionORM** | `check_entry_price_positive` | `entry_price > 0` | TEXT | P2-有防护 | 价格不可能为负 |

### 2. String 列 + 枚举值 CHECK 约束（**无问题**）

以下约束在 TEXT 列上做 `IN (...)` 字符串字面量匹配，**完全正确**：

| 模型 | 约束名 | 表达式 | 状态 |
|------|--------|--------|------|
| SignalORM / OrderORM / PositionORM | `check_direction` | `direction IN ('LONG', 'SHORT')` | OK |
| OrderORM | `check_order_status` | `status IN ('CREATED', 'SUBMITTED', ...)` | OK |
| OrderORM | `check_order_type` | `order_type IN ('MARKET', 'LIMIT', ...)` | OK |
| OrderORM | `check_order_role` | `order_role IN ('ENTRY', 'TP1', ...)` | OK |
| ConfigEntryORM | `check_value_type` | `value_type IN ('string', 'number', ...)` | OK |

### 3. 其他 CHECK 约束

| 模型 | 约束名 | 表达式 | 状态 |
|------|--------|--------|------|
| OrderORM | `check_filled_qty_not_exceed_requested` | `filled_qty <= requested_qty` | TEXT 列，但两 TEXT 列比较，仅在都为正时正确 |
| BacktestReportORM | (索引) | 4 个索引 | 无 CHECK 约束 |

---

## 方案对比

### 方案 A: 删除所有数值比较 CHECK 约束，改由应用层验证

**做法**: 移除 `BacktestReportORM` 和 `OrderORM`、`PositionORM` 中所有涉及 DecimalString 列的数值比较 CHECK 约束。

```python
# 删除这 3 个约束
__table_args__ = (
    # CheckConstraint("total_return >= -1.0 ..."),  # 删除
    # CheckConstraint("win_rate >= 0.0 ..."),      # 删除
    # CheckConstraint("max_drawdown >= 0.0 ..."),  # 删除
    Index(...),  # 保留索引
)
```

**优点**:
- 彻底消除 TEXT 列数值比较的不确定性
- 与 SignalORM 现有设计一致（已有注释说明数值验证应在应用层）
- 无需数据库迁移（约束删除后不影响现有数据）
- 零运行时性能开销
- 验证逻辑集中在 Pydantic 模型中，易于测试和维护

**缺点**:
- 失去数据库层的最后一道防线
- 如果绕过应用层直接写数据库，非法数据可以插入

**风险**:
- 低 -- 所有写入都经过 Pydantic 模型验证
- 已有应用层验证（Pydantic v2 模型校验类型和范围）

**迁移成本**: 无需数据迁移。现有负收益数据不受影响。

**工作量**: 0.5 小时（修改 3 处 CHECK 约束定义 + 补充应用层 Pydantic 验证）

---

### 方案 B: 修改 CHECK 约束使用 CAST(... AS REAL)

**做法**: 将数值比较改为 `CAST(col AS REAL)` 强制数值比较：

```python
CheckConstraint(
    "CAST(total_return AS REAL) >= -1.0 AND CAST(total_return AS REAL) <= 10.0",
    name="check_total_return_range"
),
```

**优点**:
- 保留数据库层约束
- 比较结果正确（数值序而非字典序）
- 无需数据迁移

**缺点**:
- 每次 INSERT/UPDATE 都要 CAST 转换，有运行时开销
- CHECK 约束中 3 次 CAST（`>=`、`<=`、以及可能的 NULL 处理）
- 与 SignalORM 现有设计不一致
- REAL 类型有浮点精度问题，与 "Decimal everywhere" 原则矛盾
- 极端 Decimal 值可能超出 REAL 范围

**风险**:
- REAL 精度问题：`Decimal('0.1')` 转为 REAL 后为 `0.10000000000000000555...`
- 极小值（如 `Decimal('1E-30')`）在 REAL 中可能下溢

**迁移成本**: 无需数据迁移。

**工作量**: 0.5 小时（修改 7 处 CHECK 约束）

---

### 方案 C: 迁移列类型为 REAL

**做法**: 将 `total_return`、`win_rate`、`max_drawdown` 等列从 TEXT 迁移到 REAL。

```python
total_return: Mapped[Decimal] = mapped_column(
    Float,  # 改为 REAL
    nullable=False
)
```

**优点**:
- CHECK 约束天然正确
- 数值比较无需 CAST

**缺点**:
- **REAL 精度丢失**：违反 "Decimal everywhere" 原则
- 需要数据库迁移脚本（ALTER TABLE + 数据转换）
- 回测报告涉及金融计算，REAL 精度不够
- 与整个系统的类型策略不一致

**风险**:
- **高** -- 金融计算中浮点精度问题可能导致计算结果偏差
- 现有 Decimal 序列化逻辑需要修改

**迁移成本**: 高 -- 需要 Alembic 迁移脚本 + 数据验证

**工作量**: 2 小时

---

### 方案 D: 混合方案 -- 保留合理约束，删除不合理约束

**做法**:
1. `total_return`: 删除约束（允许负数，业务上合法）
2. `win_rate` / `max_drawdown`: 删除约束（TEXT 字典序比较对 0~1 范围碰巧正确，但不应依赖隐式正确性）
3. Order/Position 的约束：保留（应用层有强验证，且值为正数时字典序与数值序一致）
4. 在 Pydantic 模型中补充范围验证

**优点**:
- 针对性修复真正有问题的约束
- 与 SignalORM 设计一致
- 无数据迁移需求
- 应用层验证集中管理

**缺点**:
- 部分约束保留在 "碰巧正确" 状态

**风险**: 低

**工作量**: 0.5 小时

---

## 推荐方案

### 推荐：方案 A（删除所有 DecimalString 列的数值比较 CHECK 约束）

**理由**:

1. **设计一致性**: SignalORM 已有明确注释 "SQLite 对 TEXT 字段使用字典序比较，因此不使用 CHECK 约束进行数值比较"。方案 A 将此设计原则统一到所有模型。

2. **根因彻底消除**: 不是修复一个约束，而是消除所有同类隐患（7 处都有潜在问题）。

3. **零迁移成本**: 删除约束不需要数据迁移，现有数据不受影响。

4. **应用层验证已存在**: Pydantic v2 模型已在应用层做类型和范围验证，数据库层约束是冗余的。

5. **方案 B 违反原则**: `CAST(... AS REAL)` 引入浮点精度问题，与 "Decimal everywhere" 原则矛盾。

6. **方案 C 不可接受**: 金融计算不能用 REAL。

### 补充措施

在 `BacktestReport` Pydantic 模型中补充范围验证：

```python
class BacktestReport(BaseModel):
    total_return: Decimal = Field(
        ge=Decimal('-1.0'), le=Decimal('10.0'),
        description="总收益率，-100% ~ 1000%"
    )
    win_rate: Decimal = Field(
        ge=Decimal('0'), le=Decimal('1'),
        description="胜率 0~1"
    )
    max_drawdown: Decimal = Field(
        ge=Decimal('0'), le=Decimal('1'),
        description="最大回撤 0~1"
    )
```

---

## 实施计划

### 修改文件

| 文件 | 修改内容 | 预估时间 |
|------|---------|---------|
| `src/infrastructure/v3_orm.py` | 删除 `BacktestReportORM` 的 3 个数值 CHECK 约束 | 5 min |
| `src/infrastructure/v3_orm.py` | 补充注释：说明为什么不使用数值 CHECK | 2 min |
| `src/domain/models.py` | 确认/补充 `BacktestReport` Pydantic 范围验证 | 10 min |
| `tests/unit/test_backtest_report.py` | 新增测试：负收益报告可以保存 | 15 min |
| `tests/unit/test_backtest_repository.py` | 新增测试：边界值验证 | 10 min |

### 实施步骤

1. **删除 CHECK 约束** -- 修改 `v3_orm.py` 中 `BacktestReportORM.__table_args__`
2. **验证 Pydantic 模型** -- 确认 `BacktestReport` 有范围验证
3. **编写测试** -- 负收益报告保存 + 边界值测试
4. **运行测试** -- `pytest tests/unit/test_backtest*.py -v`
5. **更新 progress.md**

### 数据库影响

**无需数据库迁移**。SQLite 的 CHECK 约束是表定义的一部分，使用 SQLAlchemy 的 `CREATE TABLE IF NOT EXISTS` 不会重新创建已存在的表。

**注意**: 如果使用 Alembic 自动迁移，需要生成 migration 来删除约束。但当前项目使用 `CREATE TABLE IF NOT EXISTS` + Repository 直接建表，不使用 Alembic，因此无需迁移。

### 已有数据处理

现有数据库中 `total_return='0'` 的记录不受影响。删除约束后，负收益报告可以正常插入。

**数据修复**: 无需修复已有数据。只需要确保后续负收益报告能正常保存。

---

## 关联影响

| 受影响模块 | 影响类型 | 风险等级 | 处理方案 |
|-----------|---------|---------|---------|
| `src/infrastructure/v3_orm.py` | 删除 CHECK 约束 | 无 | 直接修改 |
| `src/infrastructure/backtest_repository.py` | 无影响 | 无 | 无需修改 |
| `src/application/backtester.py` | 无影响 | 无 | 无需修改 |
| `src/domain/models.py` | 确认 Pydantic 验证 | 低 | 补充范围验证 |
| `tests/unit/test_backtest*.py` | 新增测试 | 低 | 补充负收益测试 |
| `gemimi-web-front/` | 无影响 | 无 | 前端不受影响 |

---

## 技术债

**已知**: 删除数据库层 CHECK 约束后，如果绕过应用层直接写数据库（如手动 SQL INSERT），非法数据可以插入。

**缓解措施**:
1. 所有写入都经过 `BacktestRepository.save_report()` 方法
2. 该方法接受 Pydantic `BacktestReport` 模型，已在入口处验证
3. 生产环境不开放直接数据库访问

**后续优化**: 如果未来需要多应用共享同一数据库，可考虑使用触发器（TRIGGER）替代 CHECK 约束来实现数值验证。
