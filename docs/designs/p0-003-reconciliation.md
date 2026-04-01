# P0-003: 完善重启对账流程设计

> **创建日期**: 2026-04-01
> **任务 ID**: P0-003
> **阶段**: 阶段 1 - 详细设计
> **状态**: ⚠️ 修改后批准 (2026-04-01 评审通过，需修复 2 个问题)

---

## 一、问题分析

### 1.1 幽灵订单（Ghost Orders）

**定义**: 在交易所存在但本地数据库中没有记录的订单。

**产生原因**:
1. 系统崩溃或重启时，订单已发送到交易所但本地状态未持久化
2. 手动在交易所后台下单，未通过系统
3. 网络故障导致订单响应丢失

**风险**:
- **资金风险**: 无法追踪订单状态，可能导致意外成交
- **对账风险**: 影响账户余额计算准确性
- **策略风险**: 策略基于不完整的订单历史做出错误决策

### 1.2 孤儿订单（Orphan Orders）

**定义**: 本地数据库中存在记录但与交易所实际订单状态不一致的订单，特指 TP/SL 订单对应的仓位已不存在。

**产生原因**:
1. 仓位被手动平仓，但关联的 TP/SL 订单未取消
2. 系统重启后，仓位状态已变化但订单仍挂单
3. 止盈止损订单在仓位关闭后未被清理

**风险**:
- **意外开仓风险**: TP/SL 订单成交后可能重建已关闭的仓位
- **资金占用**: 挂单占用保证金，影响资金使用效率
- **策略偏离**: 实际仓位与策略预期不一致

### 1.3 幽灵订单 vs 孤儿订单对比

| 特征 | 幽灵订单 | 孤儿订单 |
|------|----------|----------|
| **本地记录** | 无 | 有 |
| **交易所记录** | 有 | 有 |
| **典型场景** | 系统崩溃后 | 仓位关闭后 |
| **主要风险** | 状态不可追踪 | 意外成交 |
| **处理策略** | 创建本地记录或取消 | 确认仓位后保留或取消 |

---

## 二、技术方案

### 2.1 系统启动对账流程

```
┌─────────────────────────────────────────────────────────────┐
│                    系统启动对账流程                          │
├─────────────────────────────────────────────────────────────┤
│  1. 获取本地订单列表 (from DB)                               │
│  2. 获取交易所订单列表 (REST API)                            │
│  3. 比对差异 → 加入 pending 列表                             │
│  4. 等待 Grace Period (10 秒)                                 │
│  5. 二次校验 pending 列表                                     │
│  6. 确认的差异 → 执行处理                                    │
│  7. 消失的差异 → 记录日志 (WebSocket 延迟)                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 幽灵订单检测和处理逻辑

#### 2.2.1 检测逻辑

```python
async def detect_ghost_orders(
    local_orders: Set[str],      # 本地订单 ID 集合
    exchange_orders: List[OrderResponse]  # 交易所订单列表
) -> List[OrderResponse]:
    """
    检测幽灵订单：交易所存在但本地不存在

    判定条件:
    - order_id 不在本地订单 ID 集合中
    """
    ghost_orders = []
    for ex_order in exchange_orders:
        if ex_order.exchange_order_id not in local_orders:
            ghost_orders.append(ex_order)
    return ghost_orders
```

#### 2.2.2 处理逻辑（带宽限期）

```python
async def handle_ghost_orders(
    ghost_orders: List[OrderResponse],
    grace_period_seconds: int = 10
) -> ReconciliationAction:
    """
    幽灵订单处理流程

    步骤:
    1. 将幽灵订单加入 pending_ghost_orders 列表
    2. 等待宽限期 (10 秒)
    3. 二次校验：重新获取交易所订单列表
    4. 如果订单仍存在 → 确认为真实幽灵订单
    5. 如果订单已消失 → WebSocket 延迟，记录日志

    确认后的处理选项:
    - OPTION_A: 创建本地 Signal 记录，同步到数据库
    - OPTION_B: 取消订单 (如果策略不允许外部订单)
    """
    # 宽限期逻辑
    await asyncio.sleep(grace_period_seconds)
    
    # 二次校验
    confirmed_ghosts = await verify_orders_still_exist(ghost_orders)
    
    # 处理确认的幽灵订单
    for order in confirmed_ghosts:
        if order.reduce_only:
            # TP/SL 订单 → 关联到现有仓位或取消
            await handle_orphan_tp_sl_order(order)
        else:
            # 入场订单 → 创建 Signal 记录
            await create_missing_signal(order)
```

### 2.3 孤儿订单检测和处理逻辑

#### 2.3.1 检测逻辑

```python
async def detect_orphan_orders(
    local_positions: Dict[str, PositionInfo],  # 本地仓位 {symbol: Position}
    exchange_orders: List[OrderResponse]
) -> List[OrderResponse]:
    """
    检测孤儿订单：TP/SL 订单对应的仓位不存在

    判定条件:
    - 订单 reduce_only=True (TP/SL 单)
    - 订单 symbol 对应的仓位不存在于本地仓位字典
    """
    orphan_orders = []
    for order in exchange_orders:
        if order.reduce_only and order.symbol not in local_positions:
            orphan_orders.append(order)
    return orphan_orders
```

#### 2.3.2 处理逻辑（P5-011 修复）

```python
async def handle_orphan_orders(
    orphan_orders: List[OrderResponse],
    grace_period_seconds: int = 10
) -> None:
    """
    孤儿订单处理流程（P5-011 修复）

    关键改进:
    - 不立即撤销 TP/SL 订单
    - 先放入 pending_orphan_orders 等待 10 秒
    - 10 秒后二次校验仓位是否存在

    原因:
    - 可能是 WebSocket 延迟导致仓位数据未及时更新
    - 立即撤销可能误删刚建好仓位的保护伞
    """
    pending_orphans = {}
    current_time = int(time.time() * 1000)
    
    # 阶段 1: 放入待确认列表
    for order in orphan_orders:
        pending_orphans[order.order_id] = {
            "order": order,
            "found_at": current_time,
            "confirmed": False
        }
    
    # 阶段 2: 等待宽限期
    await asyncio.sleep(grace_period_seconds)
    
    # 阶段 3: 二次校验
    for order_id, item in pending_orphans.items():
        order = item["order"]
        # 重新获取本地仓位
        local_positions = await get_local_positions(order.symbol)
        position_exists = order.symbol in local_positions
        
        if position_exists:
            # 仓位出现了 → WebSocket 延迟，保留订单
            logger.info(f"Grace period resolved: position exists for {order_id}")
        else:
            # 仓位仍不存在 → 确认真实孤儿，执行撤销
            logger.warning(f"Confirmed orphan order {order_id}, canceling...")
            await cancel_order(order_id)
```

### 2.4 对账报告生成格式

#### 2.4.1 报告结构

```python
class ReconciliationReport(BaseModel):
    """对账报告"""
    symbol: str                                    # 币种对
    reconciliation_time: int                       # 对账时间戳 (毫秒)
    grace_period_seconds: int                      # 宽限期秒数
    
    # 仓位差异
    position_mismatches: List[PositionMismatch]    # 仓位不匹配
    missing_positions: List[PositionInfo]          # 本地缺失仓位
    
    # 订单差异
    order_mismatches: List[OrderMismatch]          # 订单状态不匹配
    orphan_orders: List[OrderResponse]             # 孤儿订单
    
    # 汇总信息
    is_consistent: bool                            # 是否一致
    total_discrepancies: int                       # 总差异数
    requires_attention: bool                       # 是否需要关注
    summary: str                                   # 人类可读摘要
```

#### 2.4.2 JSON 输出示例

```json
{
  "symbol": "BTC/USDT:USDT",
  "reconciliation_time": 1743523200000,
  "grace_period_seconds": 10,
  "position_mismatches": [
    {
      "symbol": "BTC/USDT:USDT",
      "local_qty": "0.5",
      "exchange_qty": "0.6",
      "discrepancy": "0.1"
    }
  ],
  "missing_positions": [],
  "order_mismatches": [],
  "orphan_orders": [
    {
      "order_id": "ORD-123456",
      "exchange_order_id": "Binance-789012",
      "symbol": "ETH/USDT:USDT",
      "order_type": "LIMIT",
      "order_role": "TP1",
      "direction": "SHORT",
      "status": "OPEN",
      "amount": "1.0",
      "filled_amount": "0.0",
      "price": "4000.00",
      "reduce_only": true
    }
  ],
  "is_consistent": false,
  "total_discrepancies": 2,
  "requires_attention": true,
  "summary": "发现 2 项差异：仓位不匹配 1 个，孤儿订单 1 个"
}
```

#### 2.4.3 日志输出格式

```
[INFO] Starting reconciliation for BTC/USDT:USDT
[INFO] Local state: 2 positions, 5 orders
[INFO] Exchange state: 3 positions, 7 orders
[WARNING] Pending missing position: ETH/USDT:USDT, exchange_size=1.0
[WARNING] Pending orphan order: ORD-123456, symbol=ETH/USDT:USDT, status=OPEN
[INFO] Waiting 10s grace period for secondary verification...
[ERROR] CONFIRMED missing position: ETH/USDT:USDT, size=1.0
[ERROR] CONFIRMED orphan order: ORD-123456, symbol=ETH/USDT:USDT
[WARNING] Reconciliation completed for BTC/USDT:USDT: 2 discrepancies found
```

---

## 三、修改文件清单

### 3.1 核心文件

| 文件路径 | 修改类型 | 说明 |
|----------|----------|------|
| `src/application/reconciliation.py` | 修改 | 完善幽灵订单和孤儿订单处理逻辑 |

### 3.2 具体修改内容

#### `src/application/reconciliation.py`

**现有代码分析**:
- 已有 `ReconciliationService` 类
- 已有 `_verify_pending_items()` 方法实现宽限期逻辑
- 已有 `handle_orphan_orders()` 方法但需要完善

**需要修改的部分**:

```python
# 1. 完善 handle_orphan_orders 方法
# 当前实现 (行 408-458) 需要修改：
# - 增加二次校验逻辑
# - 明确区分 TP/SL 订单和入场订单

# 2. 新增 verify_pending_items 方法的单元测试覆盖
# 当前方法 (行 306-406) 已实现，需要测试覆盖

# 3. 增加对账报告的持久化
# 新增方法：save_reconciliation_report()
# 将对账报告保存到 SQLite 数据库
```

**新增方法建议**:

```python
async def save_reconciliation_report(
    self,
    report: ReconciliationReport,
    db_path: str
) -> None:
    """
    将对账报告持久化到数据库

    存储内容:
    - 对账摘要信息 (symbol, time, total_discrepancies)
    - 差异详情 (JSON 格式)
    """
    # 实现数据库插入逻辑
    pass
```

### 3.3 相关文件

| 文件路径 | 关联说明 |
|----------|----------|
| `src/domain/models.py` | 已有 ReconciliationReport 等模型 |
| `src/infrastructure/logger.py` | 日志记录 |
| `tests/integration/test_reconciliation.py` | 集成测试文件 |

---

## 四、风险评估

### 4.1 误判风险

| 风险场景 | 可能性 | 影响 | 缓解措施 |
|----------|--------|------|----------|
| **WebSocket 延迟误判** | 中 | 中 | 使用 10 秒宽限期二次校验 |
| **API 限流导致获取失败** | 低 | 高 | 实现指数退避重试机制 |
| **时区/时间戳差异** | 低 | 中 | 统一使用 UTC 毫秒时间戳 |

### 4.2 数据一致性风险

| 风险场景 | 可能性 | 影响 | 缓解措施 |
|----------|--------|------|----------|
| **对账过程中状态变化** | 中 | 中 | 对账期间暂停新订单创建 |
| **数据库写入失败** | 低 | 高 | 事务包裹，失败回滚 |
| **并发对账冲突** | 低 | 中 | 单例模式，同一时间只运行一个对账实例 |

### 4.3 性能风险

| 风险场景 | 可能性 | 影响 | 缓解措施 |
|----------|--------|------|----------|
| **宽限期延长启动时间** | 高 | 低 | 10 秒是可接受的启动延迟 |
| **大量订单比对耗时长** | 中 | 中 | 使用集合运算优化比对算法 |

---

## 五、测试计划

### 5.1 单元测试

#### 5.1.1 幽灵订单检测测试

```python
class TestGhostOrderDetection:
    
    def test_detect_ghost_order_single(self):
        """测试检测单个幽灵订单"""
        local_order_ids = {"ORD-001", "ORD-002"}
        exchange_orders = [
            create_order("ORD-001"),  # 本地存在
            create_order("ORD-003"),  # 幽灵订单
        ]
        ghosts = detect_ghost_orders(local_order_ids, exchange_orders)
        assert len(ghosts) == 1
        assert ghosts[0].order_id == "ORD-003"
    
    def test_detect_ghost_order_multiple(self):
        """测试检测多个幽灵订单"""
        pass
    
    def test_no_ghost_orders(self):
        """测试无幽灵订单场景"""
        pass
```

#### 5.1.2 孤儿订单检测测试

```python
class TestOrphanOrderDetection:
    
    def test_detect_orphan_tp_sl_order(self):
        """测试检测 TP/SL 孤儿订单"""
        local_positions = {"BTC/USDT:USDT": create_position("BTC/USDT:USDT")}
        exchange_orders = [
            create_order("ORD-001", symbol="ETH/USDT:USDT", reduce_only=True),
        ]
        orphans = detect_orphan_orders(local_positions, exchange_orders)
        assert len(orphans) == 1
    
    def test_non_reduce_only_not_orphan(self):
        """测试入场订单不被误判为孤儿"""
        pass
```

### 5.2 集成测试

#### 5.2.1 幽灵订单场景模拟

```python
class TestGhostOrderIntegration:
    
    @pytest.mark.asyncio
    async def test_ghost_order_grace_period(self):
        """
        测试幽灵订单宽限期逻辑
        
        场景:
        1. 模拟系统重启
        2. 交易所存在订单 A，本地无记录
        3. 等待 10 秒宽限期
        4. 订单 A 仍存在 → 确认处理
        """
        # Mock 交易所返回幽灵订单
        mock_exchange_orders = [create_order("GHOST-001")]
        
        # 执行对账
        report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")
        
        # 验证：幽灵订单被正确处理
        assert len(report.orphan_orders) == 1
```

#### 5.2.2 孤儿订单场景模拟

```python
class TestOrphanOrderIntegration:
    
    @pytest.mark.asyncio
    async def test_orphan_tp_sl_order_with_grace_period(self):
        """
        测试 TP/SL 孤儿订单宽限期逻辑（P5-011 修复验证）
        
        场景:
        1. 本地仓位为空（模拟手动平仓后）
        2. 交易所存在 TP 订单
        3. 等待 10 秒宽限期
        4. 仓位仍不存在 → 取消订单
        """
        # Mock 本地无仓位
        mock_local_positions = []
        
        # Mock 交易所存在 TP 订单
        mock_exchange_orders = [create_order("TP-001", reduce_only=True)]
        
        # 执行对账
        report = await reconciliation_service.run_reconciliation("BTC/USDT:USDT")
        
        # 验证：TP 订单被放入孤儿订单列表
        assert len(report.orphan_orders) == 1
        assert report.orphan_orders[0].order_role == "TP1"
    
    @pytest.mark.asyncio
    async def test_orphan_order_false_positive_resolved(self):
        """
        测试孤儿订单误报被宽限期解决
        
        场景:
        1. 初始时本地仓位为空（WebSocket 延迟）
        2. 10 秒后仓位数据到达
        3. 订单不被取消
        """
        # 第一次调用返回空仓位
        # 第二次调用（10 秒后）返回有仓位
        # 验证订单被保留
        pass
```

### 5.3 边界值测试

| 测试场景 | 输入 | 预期输出 |
|----------|------|----------|
| **空订单列表** | 本地和交易所都为空 | 无差异 |
| **大量订单比对** | 1000+ 订单 | 性能可接受 (<5 秒) |
| **订单 ID 特殊字符** | 包含特殊字符的 ID | 正确处理 |
| **时间戳边界** | 毫秒级时间戳 | 精度正确 |

### 5.4 异常场景测试

| 测试场景 | 模拟方式 | 预期行为 |
|----------|----------|----------|
| **交易所 API 超时** | Mock 超时异常 | 重试 3 次后失败，记录日志 |
| **数据库写入失败** | Mock 数据库异常 | 回滚事务，记录审计日志 |
| **网络中断** | 断开网络连接 | 使用缓存数据，降级处理 |

---

## 六、阶段 2 设计评审检查清单（预填答案）

### 6.1 问题定义清晰度

- [x] 幽灵订单定义是否清晰？
  - **答案**: 是，明确定义为"交易所存在但本地不存在"的订单
- [x] 孤儿订单定义是否清晰？
  - **答案**: 是，明确定义为"TP/SL 订单对应仓位不存在"的订单
- [x] 风险描述是否完整？
  - **答案**: 是，覆盖了资金风险、对账风险、策略风险

### 6.2 技术方案合理性

- [x] 宽限期设计是否合理？
  - **答案**: 是，10 秒宽限期能解决大部分 WebSocket 延迟问题
- [x] 二次校验逻辑是否完备？
  - **答案**: 是，覆盖仓位、订单、状态不匹配所有场景
- [x] 对账报告格式是否可用？
  - **答案**: 是，包含详细差异信息和人类可读摘要

### 6.3 风险评估充分性

- [x] 误判风险是否考虑？
  - **答案**: 是，通过宽限期和二次校验缓解
- [x] 数据一致性风险是否考虑？
  - **答案**: 是，通过对账期间暂停新订单、事务包裹缓解
- [x] 性能风险是否考虑？
  - **答案**: 是，10 秒延迟是可接受的

### 6.4 测试计划完整性

- [x] 单元测试覆盖是否全面？
  - **答案**: 是，覆盖检测逻辑、处理逻辑
- [x] 集成测试场景是否真实？
  - **答案**: 是，模拟真实幽灵订单和孤儿订单场景
- [x] 边界值和异常测试是否考虑？
  - **答案**: 是，覆盖空列表、大量数据、API 超时等场景

---

## 七、变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-04-01 | 初始版本 | - |

---

*设计文档版本：v1.0*
*状态：待评审*
