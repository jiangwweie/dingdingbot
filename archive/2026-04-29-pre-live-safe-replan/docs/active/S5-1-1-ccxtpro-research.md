# S5-1-1 CCXT Pro WebSocket 调研报告

**创建日期**: 2026-03-27
**任务**: S5-1 WebSocket 资产推送

---

## 1. CCXT Pro watch_balance 方法

### 1.1 方法说明

`watch_balance()` 是 CCXT Pro 的核心方法，用于通过 WebSocket **实时监听**账户余额变化。

**优势**（相比轮询）:
- 实时推送（延迟 < 1 秒）
- 减少 API 请求频率
- 降低被交易所限流风险

### 1.2 使用方法

```python
import ccxt.pro as ccxtpro
import asyncio

async def main():
    exchange = ccxtpro.binance({
        'apiKey': 'YOUR_API_KEY',
        'secret': 'YOUR_SECRET_KEY',
        'options': {'defaultType': 'swap'},  # 合约账户
    })

    while True:
        balance = await exchange.watch_balance()
        print(f"USDT 总余额：{balance['total']['USDT']}")
        print(f"USDT 可用余额：{balance['free']['USDT']}")

    await exchange.close()
```

### 1.3 返回值结构

```python
{
    'info': {...},           # 交易所原始数据
    'total': {               # 总余额
        'USDT': Decimal('10000.0'),
        'BTC': Decimal('0.5'),
    },
    'free': {                # 可用余额
        'USDT': Decimal('8000.0'),
        'BTC': Decimal('0.3'),
    },
    'used': {                # 冻结/占用余额
        'USDT': Decimal('2000.0'),
        'BTC': Decimal('0.2'),
    }
}
```

---

## 2. 实现方案

### 2.1 架构设计

```
ExchangeGateway
    │
    ├── watch_balance() ← WebSocket 实时推送
    │       │
    │       └── _parse_ws_balance() → AccountSnapshot
    │                                       │
    │                                       └── callback(snapshot)
    │
    └── 降级方案：fetch_balance() ← 轮询（WebSocket 失败时）
```

### 2.2 重连机制

CCXT Pro 内部已处理 WebSocket 重连，我们需要：
1. 捕获异常
2. 指数退避重试
3. 超过最大重试次数后降级到轮询

### 2.3 注意事项

| 项目 | 说明 |
|------|------|
| API 权限 | 需要读取权限（只读 API Key） |
| 账户类型 | 需指定 `defaultType: 'swap'`（合约） |
| 连接管理 | 在循环外实例化交易所，避免重复创建连接 |
| 异常处理 | 捕获 `AuthenticationError`、`NetworkError` |

---

## 3. 可行性确认

✅ **确认可行** - CCXT Pro 支持 Binance WebSocket 余额推送

**下一步**: 进入步骤 2 - 类型定义与设计
