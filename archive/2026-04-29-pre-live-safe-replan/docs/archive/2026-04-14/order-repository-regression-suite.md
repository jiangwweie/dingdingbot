# OrderRepository 回归测试套件

> **文档目的**: 定义 OrderRepository 核心功能的回归测试用例，确保修改不破坏现有功能
> **创建日期**: 2026-04-07
> **执行频率**: 每次代码提交前
> **执行时间目标**: < 30 秒

---

## 📋 核心功能路径识别

### OrderRepository 核心功能树

```
OrderRepository
├── 🔴 P0: 订单持久化 (CRUD)
│   ├── save() - 保存/更新订单
│   ├── save_batch() - 批量保存
│   ├── update_status() - 更新状态
│   ├── get_order() - 查询单个订单
│   └── delete_orders_batch() - 批量删除
│
├── 🟠 P1: 订单查询
│   ├── get_orders_by_signal() - 按信号查询
│   ├── get_orders_by_symbol() - 按币种查询
│   ├── get_open_orders() - 获取未完成订单
│   ├── get_order_chain_by_order_id() - 订单链查询
│   └── get_oco_group() - OCO 组查询
│
├── 🟡 P2: 订单树/级联
│   ├── get_order_tree() - 树形结构 (分页)
│   ├── delete_order() - 级联删除
│   └── clear_orders() - 批量清理
│
└── 🔵 P3: 工具方法
    ├── initialize() - 初始化
    ├── close() - 关闭连接
    ├── set_exchange_gateway() - 依赖注入
    └── set_audit_logger() - 依赖注入
```

---

## 🧪 回归测试用例列表

### 套件 A: 订单持久化 (CRUD) - 5 个用例

#### A1. 基础保存测试
```python
def test_save_and_retrieve_order():
    """验证订单保存后可正确查询"""
    # 保存订单 → 查询 → 验证字段一致
```

#### A2. UPSERT 更新测试
```python
def test_upsert_updates_existing_order():
    """验证更新已存在订单时保留历史字段"""
    # 保存订单 → 再次保存 (更新) → 验证 filled_at 等字段保留
```

#### A3. 批量保存测试
```python
def test_save_batch_atomicity():
    """验证批量保存的原子性"""
    # 保存 5 个订单 → 验证全部存在 → 验证事务性
```

#### A4. 状态更新测试
```python
def test_update_status_all_fields():
    """验证状态更新支持所有可选字段"""
    # 更新 status + filled_qty + average_exec_price + filled_at + exchange_order_id
```

#### A5. 空值处理测试
```python
def test_save_with_null_optional_fields():
    """验证可选字段为 None 时的保存"""
    # price=None, average_exec_price=None → 保存 → 查询验证
```

---

### 套件 B: 订单查询 - 6 个用例

#### B1. 按信号查询测试
```python
def test_get_orders_by_signal_isolation():
    """验证按信号查询只返回指定信号订单"""
    # 创建信号 A(3 单) + 信号 B(2 单) → 查询信号 A → 验证只返回 3 单
```

#### B2. 按币种查询测试
```python
def test_get_orders_by_symbol_filter():
    """验证按币种过滤"""
    # 创建 BTC(3 单) + ETH(2 单) → 查询 BTC → 验证只返回 BTC 订单
```

#### B3. 未完成订单测试
```python
def test_get_open_orders_status_filter():
    """验证只返回 OPEN/PARTIALLY_FILLED 状态"""
    # 创建 OPEN(2) + PARTIALLY(2) + FILLED(2) + CANCELED(1) → 验证返回 4 单
```

#### B4. 订单链查询 (ENTRY)
```python
def test_get_order_chain_from_entry():
    """验证从 ENTRY 订单查询返回所有子订单"""
    # ENTRY → TP1, TP2, SL → 查询 → 验证返回 4 单
```

#### B5. 订单链查询 (Child)
```python
def test_get_order_chain_from_child():
    """验证从子订单查询返回父订单 + 兄弟订单"""
    # 查询 TP1 → 验证返回 ENTRY + TP1 + TP2 + SL
```

#### B6. OCO 组查询测试
```python
def test_get_oco_group_returns_all():
    """验证 OCO 组查询返回所有关联订单"""
    # TP1 + SL (同 oco_group_id) → 查询 → 验证返回 2 单
```

---

### 套件 C: 批量删除 - 5 个用例

#### C1. 空列表验证
```python
def test_delete_batch_empty_list_raises():
    """验证空列表抛出 ValueError"""
    # delete_orders_batch([]) → pytest.raises(ValueError)
```

#### C2. 超限验证
```python
def test_delete_batch_over_limit_raises():
    """验证超过 100 个订单抛出 ValueError"""
    # delete_orders_batch([101 个 ID]) → pytest.raises(ValueError)
```

#### C3. 级联删除测试
```python
def test_delete_batch_cascades_to_children():
    """验证删除 ENTRY 订单级联删除子订单"""
    # ENTRY + TP1 + SL → 删除 ENTRY → 验证 3 单都被删除
```

#### C4. 审计日志测试
```python
def test_delete_batch_creates_audit_log():
    """验证批量删除生成审计日志"""
    # 删除订单 (带 audit_info) → 验证 audit_log_id 存在
```

#### C5. 部分失败测试
```python
def test_delete_batch_partial_not_exists():
    """验证部分订单不存在时的处理"""
    # 删除 [存在，不存在，不存在] → 验证只删除存在的 1 单
```

---

### 套件 D: 依赖注入 - 3 个用例

#### D1. ExchangeGateway 注入测试
```python
def test_set_exchange_gateway():
    """验证交易所网关注入"""
    # set_exchange_gateway(mock) → 验证引用设置
```

#### D2. AuditLogger 注入测试
```python
def test_set_audit_logger():
    """验证审计日志器注入"""
    # set_audit_logger(mock) → 验证引用设置
```

#### D3. 依赖缺失降级测试
```python
def test_delete_without_gateway_graceful():
    """验证依赖缺失时优雅降级"""
    # 不注入 gateway → 删除订单 → 验证不崩溃，记录 warning
```

---

### 套件 E: 边界条件 - 5 个用例

#### E1. 并发更新测试
```python
async def test_concurrent_update_same_order():
    """验证并发更新同一订单"""
    # asyncio.gather(3 次更新) → 验证最终状态一致
```

#### E2. 事务回滚测试
```python
async def test_transaction_rollback_on_error():
    """验证错误时事务回滚"""
    # 批量保存 (中途抛出异常) → 验证无订单保存
```

#### E3. Decimal 精度测试
```python
async def test_decimal_precision_preserved():
    """验证 Decimal 精度保留"""
    # 保存 Decimal('0.00000001') → 查询 → 验证精度未丢失
```

#### E4. 大数据量测试
```python
async def test_save_large_order_list():
    """验证大批量订单保存"""
    # save_batch(100 个订单) → 验证全部保存
```

#### E5. 特殊字符测试
```python
async def test_symbol_with_special_chars():
    """验证币种对包含特殊字符"""
    # symbol="BTC/USDT:USDT" → 保存 → 查询验证
```

---

## 📊 回归测试执行矩阵

| 套件 | 用例数 | 优先级 | 执行时间 | 负责人 |
|------|--------|--------|----------|--------|
| A: 订单持久化 | 5 | P0 | < 5 秒 | QA |
| B: 订单查询 | 6 | P0 | < 8 秒 | QA |
| C: 批量删除 | 5 | P0 | < 8 秒 | QA |
| D: 依赖注入 | 3 | P1 | < 3 秒 | QA |
| E: 边界条件 | 5 | P1 | < 6 秒 | QA |
| **总计** | **24** | - | **< 30 秒** | - |

---

## 🔧 执行命令

```bash
# 运行完整回归测试套件
pytest tests/unit/infrastructure/test_order_repository_unit.py \
       tests/unit/test_order_repository.py \
       tests/integration/test_order_repository_queries.py \
       -v --tb=short

# 运行并生成覆盖率
pytest tests/unit/infrastructure/test_order_repository_unit.py \
       tests/unit/test_order_repository.py \
       tests/integration/test_order_repository_queries.py \
       --cov=src/infrastructure/order_repository --cov-report=html

# 运行特定套件 (如：只运行 CRUD 测试)
pytest tests/unit/infrastructure/test_order_repository_unit.py::test_save_order -v
```

---

## ✅ 验收标准

### 通过率要求
| 套件 | 通过率要求 | 阻断级别 |
|------|------------|----------|
| A: 订单持久化 | 100% | 🔴 阻断发布 |
| B: 订单查询 | 100% | 🔴 阻断发布 |
| C: 批量删除 | 100% | 🔴 阻断发布 |
| D: 依赖注入 | 80% | 🟡 警告 |
| E: 边界条件 | 80% | 🟡 警告 |

### 覆盖率要求
| 指标 | 目标 | 测量方式 |
|------|------|----------|
| 行覆盖率 | ≥ 60% | pytest-cov |
| 分支覆盖率 | ≥ 50% | pytest-cov --cov-branch |
| P0 方法覆盖 | 100% | 手动检查 |

---

## 📝 失败处理流程

### P0 套件失败
1. **立即通知** PM 和相关开发
2. **定位根因**: 查看失败测试的 traceback
3. **复现问题**: 单独运行失败测试
4. **确定责任方**:
   - 测试代码问题 → QA 修复
   - 业务代码问题 → Backend 修复
5. **修复后验证**: 重新运行回归套件

### P1/P2 套件失败
1. 记录失败用例到 issue tracker
2. 排期修复
3. 修复后运行回归验证

---

## 📈 历史执行记录

| 日期 | 通过率 | 覆盖率 | 备注 |
|------|--------|--------|------|
| 2026-04-07 | - | - | 初始创建 |

---

*最后更新：2026-04-07*
