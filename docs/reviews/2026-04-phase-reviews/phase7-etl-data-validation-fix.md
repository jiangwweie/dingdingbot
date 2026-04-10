# Phase 7 ETL 数据异常问题分析与修复报告

> **报告日期**: 2026-04-02  
> **执行人**: AI Builder  
> **问题状态**: ✅ 已解决（确认为假阳性，数据实际正确）  
> **相关文档**: `docs/planning/phase7-validation-report.md`

---

## 问题概述

Phase 7 验证中发现 942 条 `high < low` "异常"记录，最初怀疑是 ETL 导入时列错位导致。

**初步报告** (误报):
- 异常记录数：942 条
- 时间范围：2024-12-05 ~ 2024-12-07
- 疑似根因：ETL 列错位，timestamp 误写入 open 字段

**实际根因** (深入分析后):
- **字符串比较与数值比较的差异**导致的假阳性
- 数据本身完全正确，无需修复

---

## 根因分析

### 1. 数据库表结构

`klines` 表定义如下：

```sql
CREATE TABLE klines (
    id INTEGER NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    timeframe VARCHAR(16) NOT NULL,
    timestamp INTEGER NOT NULL,
    open VARCHAR(32) NOT NULL,      -- VARCHAR 存储 Decimal
    high VARCHAR(32) NOT NULL,
    low VARCHAR(32) NOT NULL,
    close VARCHAR(32) NOT NULL,
    volume VARCHAR(32) NOT NULL,
    is_closed BOOLEAN NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (id)
)
```

**设计意图**:
- 使用 `VARCHAR(32)` 存储 Decimal 字符串表示
- 避免 FLOAT 类型的浮点精度丢失
- 与 Python 的 `decimal.Decimal` 类型完美映射

### 2. 字符串比较陷阱

SQLite 对 VARCHAR 字段进行**字典序比较**（lexicographical comparison），而非数值比较。

**示例**:
```sql
-- 字符串比较（字典序）
SELECT "10.015" < "9.929";  -- 返回 1 (True)，因为 "1" < "9"

-- 数值比较
SELECT CAST("10.015" AS REAL) < CAST("9.929" AS REAL);  -- 返回 0 (False)
```

**字典序比较规则**:
1. 从左到右逐字符比较
2. `"1"` 的 ASCII 码 (49) 小于 `"9"` 的 ASCII 码 (57)
3. 因此 `"10.015" < "9.929"` 在第一个字符就决定了结果

### 3. 假阳性记录示例

| datetime | symbol | timeframe | open | high | low | close |
|----------|--------|-----------|------|------|-----|-------|
| 2024-12-05 10:30:00 | BTC/USDT:USDT | 15m | 99352.7 | 102543.2 | 99288.6 | 101793.9 |
| 2024-12-06 03:30:00 | BTC/USDT:USDT | 15m | 100630.2 | 100815.0 | 99666.0 | 99802.5 |
| 2024-12-07 01:30:00 | BTC/USDT:USDT | 15m | 99399.9 | 100824.9 | 99216.3 | 100722.2 |

**验证** (数值比较):
```
记录 1: high=102543.2, low=99288.6 → 102543.2 > 99288.6 ✅
记录 2: high=100815.0, low=99666.0 → 100815.0 > 99666.0 ✅
记录 3: high=100824.9, low=99216.3 → 100824.9 > 99216.3 ✅
```

### 4. 验证查询

```sql
-- 字符串比较（假阳性：942 条）
SELECT COUNT(*) FROM klines WHERE high < low;

-- 数值比较（真实异常：0 条）
SELECT COUNT(*) FROM klines WHERE CAST(high AS REAL) < CAST(low AS REAL);

-- 完整 OHLCV 逻辑检查（0 条异常）
SELECT COUNT(*) FROM klines
WHERE CAST(high AS REAL) < CAST(low AS REAL)
   OR CAST(open AS REAL) < CAST(low AS REAL)
   OR CAST(open AS REAL) > CAST(high AS REAL)
   OR CAST(close AS REAL) < CAST(low AS REAL)
   OR CAST(close AS REAL) > CAST(high AS REAL);
```

---

## 修复方案

### 方案一：不修改数据（已采用） ✅

**理由**:
- 数据本身完全正确
- VARCHAR 存储 Decimal 是合理的设计选择
- Python 代码使用 Decimal 比较，不受影响

**实施内容**:
1. ✅ 创建验证脚本 `scripts/etl/fix_kline_validation.py`
2. ✅ 创建验证视图 `v_kline_validation`
3. ✅ 更新验证报告说明问题根因

**验证脚本使用**:
```bash
python3 scripts/etl/fix_kline_validation.py
```

**输出示例**:
```
============================================================
K 线数据完整性验证报告
============================================================
数据库：data/v3_dev.db
总记录数：440,055
------------------------------------------------------------
字符串比较 violations: 942
  (这是假阳性，因为 VARCHAR 字段进行字典序比较)
数值比较 violations: 0
------------------------------------------------------------
✅ 数据完整性验证通过！
   所有 K 线数据的 OHLCV 逻辑正确。
```

### 方案二：修改数据库表类型（未采用）

**方案**: 将 `open/high/low/close` 字段改为 `REAL` 类型

```sql
-- 注意：SQLite 的 REAL 是浮点数，会丢失精度
ALTER TABLE klines MODIFY COLUMN open REAL;
```

**缺点**:
- FLOAT/REAL 类型会丢失精度
- 不适合金融金额计算
- 与 Python Decimal 类型不匹配

**结论**: ❌ 不推荐

### 方案三：添加 CHECK 约束（可选优化）

**方案**: 添加 CHECK 约束确保数据逻辑正确性

```sql
CREATE TABLE klines_new (
    ...
    open VARCHAR(32) NOT NULL,
    high VARCHAR(32) NOT NULL,
    low VARCHAR(32) NOT NULL,
    close VARCHAR(32) NOT NULL,
    CHECK (CAST(high AS REAL) >= CAST(low AS REAL)),
    CHECK (CAST(open AS REAL) >= CAST(low AS REAL)),
    CHECK (CAST(open AS REAL) <= CAST(high AS REAL)),
    CHECK (CAST(close AS REAL) >= CAST(low AS REAL)),
    CHECK (CAST(close AS REAL) <= CAST(high AS REAL))
);
```

**优点**:
- 插入时自动验证数据逻辑
- 防止脏数据进入数据库

**缺点**:
- 需要重建表（SQLite 限制）
- 现有 942 条"假阳性"记录会导致迁移失败
- 性能开销（每次插入都要 CAST 转换）

**结论**: 📝 可选优化，优先级低

---

## 影响评估

### 不受影响的系统 ✅

| 系统/模块 | 原因 |
|-----------|------|
| **回测引擎** | Python 使用 Decimal 比较，不受 SQLite 字符串比较影响 |
| **策略引擎** | 领域层使用 Decimal 类型进行数值比较 |
| **ETL 脚本** | 导入时正确使用 Decimal 解析 CSV 数据 |
| **ORM 模型** | KlineORM 使用 `DecimalString` 类型，自动转换 |

### 需注意的场景 ⚠️

| 场景 | 建议 |
|------|------|
| 直接 SQL 查询 | 使用 `CAST(field AS REAL)` 进行数值比较 |
| SQL 聚合函数 | 使用 `SUM(CAST(volume AS REAL))` 而非 `SUM(volume)` |
| SQL ORDER BY | `ORDER BY CAST(close AS REAL)` 确保数值排序 |

---

## 验证视图

已创建验证视图 `v_kline_validation` 便于后续查询：

```sql
SELECT * FROM v_kline_validation
WHERE high_gte_low = 0  -- 筛选真实异常
LIMIT 10;
```

**视图字段**:
- `high_gte_low`: high >= low 验证结果
- `open_gte_low`: open >= low 验证结果
- `open_lte_high`: open <= high 验证结果
- `close_gte_low`: close >= low 验证结果
- `close_lte_high`: close <= high 验证结果

---

## 总结与建议

### 问题总结

| 项目 | 状态 |
|------|------|
| **问题报告** | 942 条 `high < low` 异常记录 |
| **初步分析** | 误判为 ETL 列错位 |
| **实际根因** | 字符串比较与数值比较的差异 |
| **数据状态** | 完全正确，无需修复 |
| **系统影响** | 无（Python 代码使用 Decimal 比较） |

### 建议

**已实施** ✅:
1. 创建验证脚本供后续使用
2. 创建验证视图便于查询
3. 更新验证报告说明问题根因

**可选优化** (优先级低):
1. 添加 CHECK 约束（需权衡性能）
2. 在 ETL 脚本中添加数值验证步骤
3. 文档化 SQLite VARCHAR 比较陷阱

**未来迁移建议**:
- 保持当前 VARCHAR 存储 Decimal 的设计
- 在应用层（Python）进行数值验证
- 避免在 SQLite 中进行字符串比较

---

## 附录：相关命令

### 验证数据完整性
```bash
python3 scripts/etl/fix_kline_validation.py
```

### 查询假阳性记录
```sql
SELECT
    datetime(timestamp/1000, 'unixepoch', 'localtime') as datetime,
    symbol, timeframe,
    open, high, low, close
FROM klines
WHERE high < low  -- 字符串比较
  AND CAST(high AS REAL) >= CAST(low AS REAL)  -- 数值比较正常
LIMIT 20;
```

### 查询真实异常（应返回 0 条）
```sql
SELECT * FROM klines
WHERE CAST(high AS REAL) < CAST(low AS REAL)
   OR CAST(open AS REAL) < CAST(low AS REAL)
   OR CAST(open AS REAL) > CAST(high AS REAL)
   OR CAST(close AS REAL) < CAST(low AS REAL)
   OR CAST(close AS REAL) > CAST(high AS REAL);
```

---

*报告生成：2026-04-02*
