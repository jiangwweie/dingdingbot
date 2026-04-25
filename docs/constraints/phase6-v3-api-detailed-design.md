# Phase 6: v3.0 REST API 详细设计

> **创建日期**: 2026-03-31
> **版本**: v1.0
> **状态**: 📝 设计中

---

## 一、设计目标

实现 v3.0 前端管理页面所需的后端 REST API 端点，支持：
1. 订单管理（创建/查询/取消）
2. 仓位管理（查询/平仓）
3. 账户查询（余额/快照）
4. 资金保护检查
5. 对账服务

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      gemimi-web-front (React)                       │
│  /v3/orders  /v3/positions  /v3/account                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP/JSON
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                 FastAPI (src/interfaces/api.py)              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  v3 Routes                                            │  │
│  │  - /api/v3/orders/*                                   │  │
│  │  - /api/v3/positions/*                                │  │
│  │  - /api/v3/account/*                                  │  │
│  │  - /api/v3/reconciliation                             │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │  Dependency Injection                                 │  │
│  │  - exchange_gateway                                   │  │
│  │  - position_manager                                   │  │
│  │  - capital_protection                                 │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼─────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   Exchange    │  │   Position    │  │   Capital     │
│   Gateway     │  │   Manager     │  │   Protection  │
│               │  │               │  │   Manager     │
│ - place_order │  │ - get_positions│ │ - pre_order   │
│ - cancel_order│  │ - get_position │  │   _check      │
│ - fetch_order │  │ - close_position││               │
└───────────────┘  └───────────────┘  └───────────────┘
```

---

## 三、核心流程

### 3.1 订单创建流程

```
POST /api/v3/orders
     │
     ▼
1. 请求验证 (Pydantic)
     │
     ▼
2. 资金保护检查
     ├─ CapitalProtectionManager.pre_order_check()
     ├─ 检查单项损失限制
     ├─ 检查仓位限制
     ├─ 检查每日亏损限制
     └─ 检查交易次数限制
     │
     ▼
3. 订单参数转换
     ├─ order_role + direction → side (buy/sell)
     ├─ Decimal 精度处理
     └─ reduce_only 标志设置
     │
     ▼
4. 调用 ExchangeGateway
     ├─ place_order(symbol, type, side, amount, ...)
     └─ 返回 OrderPlacementResult
     │
     ▼
5. 订单持久化（可选）
     │
     ▼
6. 返回 OrderResponse
```

### 3.2 订单取消流程

```
DELETE /api/v3/orders/{order_id}?symbol=xxx
     │
     ▼
1. 查询订单状态
     │
     ▼
2. 检查订单是否可取消
     ├─ 状态必须为 OPEN/PENDING
     └─ 不能是已成交订单
     │
     ▼
3. 调用 ExchangeGateway
     ├─ cancel_order(order_id, symbol)
     └─ 返回 OrderCancelResult
     │
     ▼
4. 更新本地订单状态（可选）
     │
     ▼
5. 返回 OrderCancelResponse
```

### 3.3 仓位查询流程

```
GET /api/v3/positions?symbol=xxx&is_closed=false
     │
     ▼
1. 参数解析
     ├─ symbol 过滤
     ├─ is_closed 过滤
     └─ pagination
     │
     ▼
2. 调用 PositionManager
     ├─ get_positions(symbol, is_closed)
     └─ 返回 PositionInfo 列表
     │
     ▼
3. 格式化为响应
     │
     ▼
4. 返回 PositionsResponse
```

---

## 四、实现细节

### 4.1 订单角色映射

```python
# src/interfaces/api.py

def role_direction_to_side(role: OrderRole, direction: Direction) -> str:
    """
    将订单角色 + 方向映射到 CCXT side (buy/sell)

    U 本位合约规则:
    - 开多 (ENTRY + LONG) → buy
    - 开空 (ENTRY + SHORT) → sell
    - 平多 (TP/SL + LONG) → sell
    - 平空 (TP/SL + SHORT) → buy
    """
    if role == OrderRole.ENTRY:
        return "buy" if direction == Direction.LONG else "sell"
    else:  # TP1-5, SL
        return "sell" if direction == Direction.LONG else "buy"
```

### 4.2 资金保护检查集成

```python
# src/interfaces/api.py

@app.post("/api/v3/orders/check")
async def check_order_capital(request: OrderCheckRequest):
    """下单前资金保护检查（Dry Run）"""
    result = await capital_protection.pre_order_check(
        symbol=request.symbol,
        order_type=request.order_type,
        amount=request.quantity,
        price=request.price,
        trigger_price=request.trigger_price,
        stop_loss=request.stop_loss,
    )
    return result

@app.post("/api/v3/orders")
async def create_order(request: OrderRequest):
    """创建订单"""
    # 1. 资金保护检查
    check_result = await capital_protection.pre_order_check(...)
    if not check_result.allowed:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "CAPITAL_CHECK_FAILED", "reason": check_result.reason}
        )

    # 2. 下单
    order_result = await exchange_gateway.place_order(...)
    return order_result
```

### 4.3 错误处理

```python
# src/interfaces/api.py

from src.domain.exceptions import (
    InsufficientMarginError,      # F-010
    InvalidOrderError,            # F-011
    OrderNotFoundError,           # F-012
    OrderAlreadyFilledError,      # F-013
    RateLimitError,               # C-010
)

@app.exception_handler(InsufficientMarginError)
async def handle_insufficient_margin(request, exc):
    return JSONResponse(
        status_code=402,
        content={"error_code": exc.code, "message": str(exc)}
    )

@app.exception_handler(InvalidOrderError)
async def handle_invalid_order(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error_code": exc.code, "message": str(exc)}
    )

@app.exception_handler(OrderNotFoundError)
async def handle_order_not_found(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error_code": exc.code, "message": str(exc)}
    )
```

### 4.4 日志脱敏

```python
# src/interfaces/api.py

from src.infrastructure.logger import mask_secret

logger.info(f"Creating order: symbol={request.symbol}, "
            f"type={request.order_type}, "
            f"qty={request.quantity}, "
            f"client_order_id={mask_secret(request.client_order_id) if request.client_order_id else 'N/A'}")
```

---

## 五、数据库设计

### 5.1 orders 表（Phase 1 已创建）

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | TEXT PRIMARY KEY | 系统订单 ID |
| exchange_order_id | TEXT | 交易所订单 ID |
| symbol | TEXT NOT NULL | 币种对 |
| order_type | TEXT NOT NULL | 订单类型 |
| order_role | TEXT NOT NULL | 订单角色 |
| direction | TEXT NOT NULL | 方向 |
| quantity | REAL NOT NULL | 数量 |
| price | REAL | 价格 |
| trigger_price | REAL | 触发价 |
| reduce_only | BOOLEAN DEFAULT FALSE | 仅减仓 |
| status | TEXT NOT NULL | 状态 |
| filled_qty | REAL DEFAULT 0 | 已成交数量 |
| average_exec_price | REAL | 平均成交价 |
| fee_paid | REAL | 手续费 |
| created_at | INTEGER NOT NULL | 创建时间 |
| updated_at | INTEGER NOT NULL | 更新时间 |

### 5.2 positions 表（Phase 1 已创建）

| 字段 | 类型 | 说明 |
|------|------|------|
| position_id | TEXT PRIMARY KEY | 仓位 ID |
| symbol | TEXT NOT NULL | 币种对 |
| direction | TEXT NOT NULL | 方向 |
| entry_price | REAL NOT NULL | 入场价 |
| current_qty | REAL NOT NULL | 当前数量 |
| original_qty | REAL NOT NULL | 原始数量 |
| unrealized_pnl | REAL | 未实现盈亏 |
| realized_pnl | REAL | 已实现盈亏 |
| is_closed | BOOLEAN DEFAULT FALSE | 是否已平 |
| entry_time | INTEGER NOT NULL | 入场时间 |
| closed_at | INTEGER | 平仓时间 |

---

## 六、测试计划

### 6.1 单元测试

| 测试文件 | 测试内容 | 用例数 |
|----------|----------|--------|
| `test_v3_api_endpoints.py` | API 端点测试 | 20 |
| `test_v3_order_creation.py` | 订单创建流程 | 10 |
| `test_v3_capital_protection.py` | 资金保护检查 | 8 |
| `test_v3_order_cancel.py` | 订单取消流程 | 6 |
| `test_v3_positions.py` | 仓位查询 | 6 |

### 6.2 集成测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_v3_e2e_orders.py` | 订单创建→查询→取消完整流程 |
| `test_v3_e2e_positions.py` | 开仓→持仓→平仓完整流程 |
| `test_v3_capital_protection_e2e.py` | 资金保护触发场景 |

---

## 七、依赖项

### 7.1 Phase 5 已实现

- [x] ExchangeGateway.place_order()
- [x] ExchangeGateway.cancel_order()
- [x] ExchangeGateway.fetch_order()
- [x] PositionManager.get_positions()
- [x] CapitalProtectionManager.pre_order_check()
- [x] ReconciliationService.run_reconciliation()

### 7.2 Phase 6 需要实现

- [ ] FastAPI 路由定义（`src/interfaces/api.py`）
- [ ] 请求/响应模型（`src/domain/models.py`）
- [ ] 依赖注入配置
- [ ] 错误处理映射
- [ ] 单元测试

---

## 八、验收标准

### 8.1 功能验收

- [ ] 所有端点实现与契约表一致
- [ ] 请求验证正确（Pydantic）
- [ ] 资金保护检查生效
- [ ] 错误响应格式统一
- [ ] 日志脱敏正确

### 8.2 测试验收

- [ ] 单元测试通过率 100%
- [ ] 集成测试通过率 100%
- [ ] 覆盖率 ≥ 80%

### 8.3 性能验收

- [ ] API 响应时间 < 500ms (P95)
- [ ] 并发请求无竞态条件
- [ ] 资金保护检查无遗漏

---

*详细设计版本：v1.0*
*最后更新：2026-03-31*
