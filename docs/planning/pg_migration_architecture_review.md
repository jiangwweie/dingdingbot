# PG 全状态迁移架构审查报告

**审查日期**: 2026-04-29
**审查分支**: `codex/pg-full-migration`
**审查人**: Architect (架构师)
**审查重点**: 默认 PG 路由、SQLite 显式路径兼容、迁移脚本字段映射、误切 PG 风险

---

## 📋 审查结论总览

**整体评级**: **B+ (可合并，但需先解决 3 个 P1 问题)**

**关键发现**:
- ✅ 默认 PG 路由逻辑正确（环境变量 + 参数判断）
- ✅ SQLite 显式路径兼容性良好（测试场景保留）
- ⚠️ 迁移脚本字段映射存在 3 个潜在风险点
- ⚠️ HybridSignalRepository 改动激进，可能误切 backtest 信号
- ⚠️ `__new__` 模式与 `StrategyConfigRepository` 的 `__init__` 模式不一致

---

## 🔍 详细审查问题清单（不少于 10 个）

### 问题 1: HybridSignalRepository 默认删除 SQLite fallback 是否过于激进？

**位置**: `src/infrastructure/hybrid_signal_repository.py:24-27`

**代码变更**:
```python
# 修改前
self._legacy_repo = legacy_repo or SignalRepository()

# 修改后
self._legacy_repo = legacy_repo  # 默认 None
```

**风险分析**:
- ❌ **默认构造不再创建 SQLite fallback**
- ❌ **`__getattr__` 在无 legacy_repo 时直接抛 AttributeError**
- ⚠️ **backtest 信号路由逻辑被移除**（`get_signals` 不再判断 `source=="backtest"`）

**潜在影响**:
1. **Backtest 信号可能误切 PG**：如果 backtest 脚本未显式注入 `legacy_repo`，信号会写入 PG（而非 SQLite）
2. **旧脚本兼容性断裂**：依赖默认 HybridSignalRepository 的脚本可能突然失败
3. **测试隔离失效**：测试 fixture 如果未注入 legacy_repo，会污染 PG 生产数据

**建议修复**:
```python
# 方案 A: 保守方案（推荐）
self._legacy_repo = legacy_repo
if self._legacy_repo is None and os.getenv("MIGRATE_ALL_STATE_TO_PG") != "true":
    # 仅在未开启全量迁移时保留默认 SQLite fallback
    self._legacy_repo = SignalRepository()

# 方案 B: 激进方案（需文档明确）
# 强制所有调用方显式注入 legacy_repo（测试/脚本需更新）
```

**优先级**: **P1 (必须修复)**

---

### 问题 2: HybridSignalRepository `delete_signals` 路由逻辑是否误切 backtest？

**位置**: `src/infrastructure/hybrid_signal_repository.py:92-100`

**代码变更**:
```python
# 修改前
if source == "backtest" or request_source == "backtest":
    return await self._legacy_repo.delete_signals(*args, **kwargs)
return await self._live_repo.delete_signals(*args, **kwargs)

# 修改后
if self._legacy_repo is not None:
    if source == "backtest" or request_source == "backtest":
        return await self._legacy_repo.delete_signals(*args, **kwargs)
return await self._live_repo.delete_signals(*args, **kwargs)
```

**风险分析**:
- ⚠️ **如果 `legacy_repo=None`，backtest delete 会误切 PG**
- ⚠️ **PG 生产信号可能被误删**（如果 backtest 脚本未注入 legacy_repo）

**建议修复**:
```python
# 添加安全检查
if source == "backtest" or request_source == "backtest":
    if self._legacy_repo is None:
        raise RuntimeError(
            "Cannot delete backtest signals without legacy_repo. "
            "Inject SignalRepository() for backtest isolation."
        )
    return await self._legacy_repo.delete_signals(*args, **kwargs)
```

**优先级**: **P1 (必须修复)**

---

### 问题 3: 迁移脚本 `signal_take_profits` 字段映射是否遗漏 `signal_id` 转换？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:184-195`

**代码逻辑**:
```python
if table == "signal_take_profits":
    signal_id_map = _sqlite_signal_id_map(db_path)
    mapped_rows = []
    for row in rows:
        numeric_id = row.get("signal_id")
        signal_id = signal_id_map.get(int(numeric_id)) if numeric_id is not None else None
        if not signal_id:
            continue  # ⚠️ 跳过无 signal_id 的记录
        mapped = dict(row)
        mapped["signal_id"] = signal_id
        mapped_rows.append(mapped)
    rows = mapped_rows
```

**风险分析**:
- ⚠️ **跳过无 `signal_id` 的记录**：可能导致数据丢失（如果 SQLite signals 表有孤立记录）
- ⚠️ **`signal_id` 类型转换假设**：假设 SQLite `signal_id` 是 numeric ID，但实际可能是 UUID string

**建议修复**:
```python
# 添加日志记录跳过的记录
if not signal_id:
    print(f"[warn] skip signal_take_profit row with missing signal_id: {row.get('id')}")
    continue

# 添加类型检查
if isinstance(numeric_id, str) and numeric_id.startswith("sig_"):
    # 已经是 UUID string，无需转换
    signal_id = numeric_id
else:
    signal_id = signal_id_map.get(int(numeric_id))
```

**优先级**: **P2 (建议修复)**

---

### 问题 4: 迁移脚本 `runtime_profiles` 字段重命名是否覆盖所有场景？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:196-203`

**代码逻辑**:
```python
elif table == "runtime_profiles":
    rows = [
        {
            ("profile_payload" if key == "profile_json" else key): value
            for key, value in row.items()
        }
        for row in rows
    ]
```

**风险分析**:
- ✅ **字段重命名逻辑正确**（`profile_json` → `profile_payload`）
- ⚠️ **但 PG ORM 定义中字段名是 `profile_payload`**（已确认一致）
- ⚠️ **是否需要验证 PG 表结构已更新？**（如果 PG 表仍用旧字段名，会插入失败）

**建议修复**:
```python
# 添加 PG 表结构验证
pg_columns = await _pg_columns(session, "runtime_profiles")
if "profile_payload" not in pg_columns:
    print(f"[error] PG runtime_profiles missing 'profile_payload' column")
    return 0
```

**优先级**: **P2 (建议修复)**

---

### 问题 5: 迁移脚本 `backtest_reports` 字段修复是否覆盖所有异常？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:204-214`

**代码逻辑**:
```python
elif table == "backtest_reports":
    cleaned_rows = []
    for row in rows:
        cleaned = dict(row)
        sharpe_ratio = cleaned.get("sharpe_ratio")
        if isinstance(sharpe_ratio, str) and sharpe_ratio.lstrip().startswith(("[", "{")):
            if not cleaned.get("positions_summary"):
                cleaned["positions_summary"] = sharpe_ratio
            cleaned["sharpe_ratio"] = None
        cleaned_rows.append(cleaned)
    rows = cleaned_rows
```

**风险分析**:
- ✅ **修复逻辑正确**（将误存为 sharpe_ratio 的 JSON 移到 positions_summary）
- ⚠️ **但仅处理 JSON string，未处理其他异常类型**（如空字符串、非法数值）

**建议修复**:
```python
# 添加更全面的 sharpe_ratio 清理
if sharpe_ratio is not None:
    if isinstance(sharpe_ratio, str):
        if sharpe_ratio.lstrip().startswith(("[", "{")):
            # JSON 误存
            if not cleaned.get("positions_summary"):
                cleaned["positions_summary"] = sharpe_ratio
            cleaned["sharpe_ratio"] = None
        elif sharpe_ratio.strip() == "":
            # 空字符串
            cleaned["sharpe_ratio"] = None
        else:
            # 尝试转换为 Decimal
            try:
                cleaned["sharpe_ratio"] = Decimal(sharpe_ratio)
            except:
                cleaned["sharpe_ratio"] = None
```

**优先级**: **P2 (建议修复)**

---

### 问题 6: 迁移脚本 JSON 字段强制重序列化是否破坏原始数据？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:131-145`

**代码逻辑**:
```python
if column in JSON_COLUMNS:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if value == "":
        return None
    try:
        return json.dumps(json.loads(value), ensure_ascii=False, default=str)
    except Exception:
        return value
```

**风险分析**:
- ⚠️ **强制重序列化可能改变原始 JSON 格式**（如缩进、字段顺序）
- ⚠️ **`default=str` 可能丢失类型信息**（如 Decimal → string）
- ⚠️ **异常时返回原始 value，可能导致 PG 插入失败**（如果 PG 列是 JSONB 类型）

**建议修复**:
```python
# 仅在必要时重序列化
if column in JSON_COLUMNS:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        # 已经是 Python 对象，直接序列化
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        try:
            # 验证是否为合法 JSON
            parsed = json.loads(value)
            # 仅在格式异常时重序列化
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            # 非 JSON string，返回 None（避免 PG JSONB 类型错误）
            print(f"[warn] column {column} has non-JSON value: {value[:50]}")
            return None
```

**优先级**: **P2 (建议修复)**

---

### 问题 7: `__new__` 模式与 `StrategyConfigRepository.__init__` 模式不一致

**位置**: `src/infrastructure/repositories/config_repositories.py`

**代码对比**:
```python
# StrategyConfigRepository 使用 __init__ + use_pg 参数
def __init__(self, db_path="data/v3_dev.db", connection=None, use_pg=None):
    if use_pg is None:
        use_pg = _should_route_default_to_pg(db_path, connection)
    if use_pg:
        self._pg_repo = PgStrategyConfigRepository()
        self._use_pg = True
    else:
        self._db = ...
        self._use_pg = False

# RiskConfigRepository 使用 __new__ 模式
def __new__(cls, db_path="data/v3_dev.db", connection=None):
    if cls is RiskConfigRepository and _should_route_default_to_pg(db_path, connection):
        return PgRiskConfigRepository()
    return super().__new__(cls)
```

**风险分析**:
- ⚠️ **两种模式不一致**：StrategyConfigRepository 返回自身实例（内部委托），其他 Repository 返回 PG 实例（完全替换）
- ⚠️ **StrategyConfigRepository 的方法调用需判断 `self._use_pg`**，其他 Repository 直接调用 PG 方法
- ⚠️ **维护成本高**：两种模式需分别理解，容易出错

**建议修复**:
```python
# 统一使用 __new__ 模式（推荐）
class StrategyConfigRepository:
    def __new__(cls, db_path="data/v3_dev.db", connection=None, use_pg=None):
        if use_pg is None:
            use_pg = _should_route_default_to_pg(db_path, connection)
        if use_pg:
            return PgStrategyConfigRepository()
        return super().__new__(cls)

    def __init__(self, db_path="data/v3_dev.db", connection=None, use_pg=None):
        # 仅在 SQLite 模式下初始化
        ...
```

**优先级**: **P1 (必须修复)**

---

### 问题 8: 迁移脚本 `ON CONFLICT DO NOTHING` 是否导致数据不一致？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:275`

**代码逻辑**:
```python
stmt = text(f'INSERT INTO "{target_table}" ({column_sql}) VALUES ({value_sql}) ON CONFLICT DO NOTHING')
```

**风险分析**:
- ⚠️ **跳过冲突记录，不更新已有数据**：如果 PG 已有数据，SQLite 新数据不会覆盖
- ⚠️ **可能导致数据不一致**：如果 SQLite 和 PG 数据有差异，迁移后 PG 仍保留旧数据
- ⚠️ **缺少冲突日志**：无法知道哪些记录被跳过

**建议修复**:
```python
# 方案 A: 记录冲突记录（推荐）
stmt = text(f'''
    INSERT INTO "{target_table}" ({column_sql}) VALUES ({value_sql})
    ON CONFLICT DO NOTHING
''')
# 执行后检查实际插入数量
result = await session.execute(stmt, batch)
if result.rowcount < len(batch):
    print(f"[warn] {len(batch) - result.rowcount} records skipped due to conflict")

# 方案 B: 使用 ON CONFLICT DO UPDATE（激进）
# 仅在确认需要覆盖时使用
```

**优先级**: **P2 (建议修复)**

---

### 问题 9: 迁移脚本缺少表结构验证是否导致插入失败？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:246-248`

**代码逻辑**:
```python
pg_columns = await _pg_columns(session, target_table)
if not pg_columns:
    print(f"[skip] PG table missing: {target_table}")
    return 0
```

**风险分析**:
- ✅ **检查 PG 表是否存在**
- ⚠️ **但未检查字段是否匹配**：如果 SQLite 有字段 `foo`，但 PG 无 `foo`，插入会失败
- ⚠️ **payload 构造时会过滤掉不匹配字段**（line 260-264），但无日志记录

**建议修复**:
```python
# 添加字段差异日志
sqlite_columns = set(rows[0].keys())
missing_in_pg = sqlite_columns - pg_columns
if missing_in_pg:
    print(f"[warn] SQLite columns missing in PG: {missing_in_pg}")

payload = {
    key: _coerce_value(key, value)
    for key, value in row.items()
    if key in pg_columns  # 仅保留 PG 有字段
}
```

**优先级**: **P2 (建议修复)**

---

### 问题 10: 迁移脚本缺少数据验证是否导致迁移后数据丢失？

**位置**: `scripts/migrate_sqlite_state_to_pg.py` (全文)

**风险分析**:
- ⚠️ **无迁移后验证**：未检查 PG 数据数量是否与 SQLite 一致
- ⚠️ **无数据完整性检查**：未验证 JSON 字段是否正确反序列化
- ⚠️ **无回滚机制**：迁移失败后无法恢复

**建议修复**:
```python
# 添加迁移后验证
async def _verify_migration(session, db_path, table, expected_count):
    result = await session.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
    actual_count = result.scalar()
    if actual_count < expected_count:
        print(f"[error] {table}: expected {expected_count}, got {actual_count}")
        return False
    return True

# 在 main() 中调用验证
for table in tables:
    expected = _sqlite_row_count(db_path, table)
    await _copy_table(session, db_path, table, args.truncate)
    if not await _verify_migration(session, db_path, table, expected):
        print(f"[error] migration verification failed for {table}")
```

**优先级**: **P2 (建议修复)**

---

### 问题 11: 测试 fixture 连接池清理是否影响生产代码？

**位置**: `tests/unit/test_config_profile.py`

**代码变更**:
```python
# 添加 close_all_connections() 清理
await close_all_connections()
```

**风险分析**:
- ⚠️ **测试清理逻辑不应影响生产代码**
- ⚠️ **`close_all_connections()` 是全局清理**，可能影响并发测试
- ⚠️ **仅在测试中添加，未在迁移报告中说明**

**建议修复**:
```python
# 使用 pytest fixture scope=session（推荐）
@pytest.fixture(scope="session")
async def cleanup_connections():
    yield
    from src.infrastructure.connection_pool import close_all_connections
    await close_all_connections()

# 或使用唯一临时 DB（避免连接池冲突）
@pytest.fixture
async def temp_db():
    db_path = f"/tmp/test_{uuid.uuid4()}.db"
    yield db_path
    # 无需清理连接池
```

**优先级**: **P3 (可选修复)**

---

### 问题 12: 迁移脚本 `research_jobs` 字段映射是否覆盖所有场景？

**位置**: `scripts/migrate_sqlite_state_to_pg.py:215-225`

**代码逻辑**:
```python
elif table == "research_jobs":
    rows = [
        {
            ("spec_payload" if key == "spec_json" else key): value
            for key, value in row.items()
        }
        for row in rows
    ]
    for row in rows:
        if not row.get("spec_payload"):
            row["spec_payload"] = _load_json_artifact(row.get("spec_ref"))
```

**风险分析**:
- ✅ **字段重命名正确**（`spec_json` → `spec_payload`）
- ⚠️ **从文件加载 artifact 逻辑正确**（`_load_json_artifact`）
- ⚠️ **但未检查文件是否存在**：如果 `spec_ref` 指向不存在的文件，会返回空 dict

**建议修复**:
```python
# 添加文件存在检查
spec_ref = row.get("spec_ref")
if spec_ref:
    artifact = _load_json_artifact(spec_ref)
    if not artifact:
        print(f"[warn] research_jobs {row['id']}: spec_ref file missing: {spec_ref}")
    row["spec_payload"] = artifact
```

**优先级**: **P3 (可选修复)**

---

## 🎯 合并建议

### P1 问题（必须修复）

1. **HybridSignalRepository 默认删除 SQLite fallback** → 添加保守 fallback 或强制显式注入
2. **HybridSignalRepository backtest delete 路由** → 添加安全检查，防止误删 PG 生产信号
3. **`__new__` 与 `__init__` 模式不一致** → 统一为 `__new__` 模式

### P2 问题（建议修复）

4. **迁移脚本 `signal_take_profits` 字段映射** → 添加日志和类型检查
5. **迁移脚本 `runtime_profiles` 字段重命名** → 添加 PG 表结构验证
6. **迁移脚本 `backtest_reports` 字段修复** → 添加更全面的 sharpe_ratio 清理
7. **迁移脚本 JSON 字段重序列化** → 仅在必要时重序列化，避免破坏原始数据
8. **迁移脚本 `ON CONFLICT DO NOTHING`** → 添加冲突日志
9. **迁移脚本表结构验证** → 添加字段差异日志
10. **迁移脚本数据验证** → 添加迁移后验证

### P3 问题（可选修复）

11. **测试 fixture 连接池清理** → 使用 session scope 或唯一临时 DB
12. **迁移脚本 `research_jobs` 字段映射** → 添加文件存在检查

---

## 📝 合并前检查清单

**必须完成**:
- [ ] 修复 HybridSignalRepository 默认 fallback（P1）
- [ ] 修复 HybridSignalRepository backtest delete 安全检查（P1）
- [ ] 统一 Repository 路由模式（P1）
- [ ] 运行完整测试套件（`MIGRATE_ALL_STATE_TO_PG=false`）
- [ ] 运行迁移脚本验证（`--truncate` 仅用于本地测试）
- [ ] 确认 PG 表结构已更新（所有新增字段已创建）

**建议完成**:
- [ ] 添加迁移脚本日志增强（P2）
- [ ] 添加迁移后数据验证（P2）
- [ ] 更新迁移文档（说明 HybridSignalRepository 改动影响）

---

## 🔒 风险等级

| 风险类型 | 等级 | 说明 |
|---------|------|------|
| **数据丢失风险** | 🔴 高 | HybridSignalRepository 可能误删 PG 生产信号 |
| **兼容性断裂风险** | 🟡 中 | 默认 SQLite fallback 删除，旧脚本可能失败 |
| **数据不一致风险** | 🟡 中 | 迁移脚本跳过冲突记录，可能导致 PG 数据陈旧 |
| **测试隔离失效风险** | 🟡 中 | 测试未注入 legacy_repo 可能污染 PG |

---

## 📚 相关文档

- `docs/planning/pg_migration_completion_report.md` - 迁移完成报告
- `src/infrastructure/database.py` - 默认 PG 路由逻辑
- `src/infrastructure/config_repository_factory.py` - 工厂函数路由逻辑
- `scripts/migrate_sqlite_state_to_pg.py` - 迁移脚本

---

**审查人**: Architect
**审查日期**: 2026-04-29
**建议**: **暂不合进 dev，先修复 P1 问题后再合并**