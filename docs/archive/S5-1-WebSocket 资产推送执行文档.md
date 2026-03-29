# S5-1 任务执行文档 - WebSocket 资产推送

**任务 ID**: S5-1
**阶段**: Phase 5 - 窗口 1
**预估工时**: 7 小时
**优先级**: 高

---

## 任务概述

将当前的 **轮询模式** 改为 **WebSocket 实时推送**，降低延迟和 API 请求频率。

### 当前架构（轮询模式）

现有代码位于 `src/infrastructure/exchange_gateway.py`:
- `_poll_assets_loop()` - 每 60 秒轮询一次账户余额和持仓
- `_poll_account()` - 执行单次轮询

### 目标架构（WebSocket 模式）

```
币安 WebSocket → CCXT.Pro → on_balance_update() → 更新快照 → 通知信号管道
                      ↓
                 重连失败 → 降级轮询
```

---

## 执行步骤（按顺序完成）

### 步骤 1: CCXT.Pro WebSocket 调研

**输出文件**: `docs/superpowers/specs/S5-1-1-ccxtpro-research.md`

**任务**:
1. 阅读 CCXT.Pro 官方文档：https://docs.ccxt.com/en/ccxt.pro.manual.html
2. 查找币安 WebSocket 账户推送接口
3. 验证 `watch_balance()` 方法可用性
4. 记录订阅频道和消息格式

**调研要点**:
- 币安 WebSocket 账户推送的频道名称
- 消息格式示例
- 重连机制说明
- 是否需要特殊权限

**验收标准**:
- 文档包含完整的 API 使用方法
- 包含代码示例
- 确认可行性

---

### 步骤 2: 类型定义与设计

**修改文件**: `src/domain/models.py`

**新增模型**:

```python
class WebSocketAssetConfig(BaseModel):
    """WebSocket 资产推送配置"""
    enabled: bool = True
    reconnect_delay: float = 1.0  # 初始重连延迟（秒）
    max_reconnect_delay: float = 60.0  # 最大重连延迟
    max_reconnect_attempts: int = 10
    fallback_to_polling: bool = True  # WebSocket 失败时降级轮询
    polling_interval: int = 60  # 轮询间隔（秒）


class AssetUpdateCallback(Protocol):
    """资产更新回调协议"""
    async def __call__(self, snapshot: AccountSnapshot) -> None:
        ...
```

**验收标准**:
- 类型检查通过
- 模型字段完整

---

### 步骤 3: WebSocket 订阅实现

**修改文件**: `src/infrastructure/exchange_gateway.py`

**新增方法**:

```python
async def subscribe_account_updates(
    self,
    callback: Callable[[AccountSnapshot], Awaitable[None]],
) -> None:
    """
    订阅账户资产实时更新

    Args:
        callback: 资产更新时的异步回调
    """
    self._ws_running = True
    self._reconnect_count = 0

    # 创建 WebSocket 交换实例
    self.ws_exchange = self._create_ws_exchange({
        'defaultType': 'swap',
    })

    # 加载市场数据
    await self.ws_exchange.load_markets()

    # 订阅账户更新
    await self._ws_subscribe_account_loop(callback)
```

**内部方法**:

```python
async def _ws_subscribe_account_loop(
    self,
    callback: Callable[[AccountSnapshot], Awaitable[None]],
) -> None:
    """WebSocket 订阅循环（含重连逻辑）"""
    reconnect_count = 0

    while self._ws_running:
        try:
            while self._ws_running:
                # 使用 CCXT.Pro watch_balance() 方法
                balance = await self.ws_exchange.watch_balance()

                # 解析并回调
                snapshot = self._parse_ws_balance(balance)
                await callback(snapshot)

        except asyncio.CancelledError:
            break

        except Exception as e:
            reconnect_count += 1
            if reconnect_count >= self._max_reconnect_attempts:
                raise ConnectionLostError(
                    f"WebSocket 重连失败超过 {self._max_reconnect_attempts} 次",
                    "C-001"
                )

            # 指数退避
            delay = min(
                self._initial_reconnect_delay * (2 ** (reconnect_count - 1)),
                self._max_reconnect_delay
            )
            logger.warning(f"WebSocket 重连中... {delay:.1f}s (尝试 {reconnect_count}/{self._max_reconnect_attempts})")
            await asyncio.sleep(delay)
```

---

### 步骤 4: 资产快照解析

**修改文件**: `src/infrastructure/exchange_gateway.py`

**新增方法**:

```python
def _parse_ws_balance(
    self,
    balance: Dict[str, Any],
) -> AccountSnapshot:
    """
    解析 WebSocket 余额消息为 AccountSnapshot

    Args:
        balance: CCXT.Pro watch_balance() 返回的余额数据

    Returns:
        AccountSnapshot 对象
    """
    import time
    from decimal import Decimal

    total_balance = Decimal('0')
    available_balance = Decimal('0')
    unrealized_pnl = Decimal('0')

    # 解析 USDT 余额
    if 'total' in balance and 'USDT' in balance['total']:
        total_balance = Decimal(str(balance['total']['USDT']))
    if 'free' in balance and 'USDT' in balance['free']:
        available_balance = Decimal(str(balance['free']['USDT']))

    return AccountSnapshot(
        total_balance=total_balance,
        available_balance=available_balance,
        unrealized_pnl=unrealized_pnl,
        positions=[],  # WebSocket 余额不包含持仓，需要单独获取
        timestamp=int(time.time() * 1000),
    )
```

---

### 步骤 5: 降级轮询机制

**修改文件**: `src/infrastructure/exchange_gateway.py`

**修改现有代码**:

```python
async def subscribe_account_updates(
    self,
    callback: Callable[[AccountSnapshot], Awaitable[None]],
) -> None:
    """订阅账户资产更新（含降级逻辑）"""
    try:
        await self._ws_subscribe_account_loop(callback)
    except Exception as e:
        logger.warning(f"WebSocket 订阅失败，降级到轮询模式：{e}")
        # 降级到轮询模式
        await self._poll_assets_loop_with_callback(callback)
```

**新增方法**:

```python
async def _poll_assets_loop_with_callback(
    self,
    callback: Callable[[AccountSnapshot], Awaitable[None]],
    interval_seconds: int = 60,
) -> None:
    """降级轮询模式（带回调）"""
    while True:
        try:
            snapshot = await self._poll_account()
            await callback(snapshot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"降级轮询失败：{e}")

        await asyncio.sleep(interval_seconds)
```

---

### 步骤 6: 集成测试

**创建文件**: `tests/integration/test_websocket_asset.py`

**测试用例**:

```python
"""
WebSocket 资产推送集成测试
"""
import pytest
import asyncio
from decimal import Decimal

from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import AccountSnapshot


class TestWebSocketAssetPush:
    """WebSocket 资产推送测试"""

    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """测试 WebSocket 连接成功"""
        gateway = ExchangeGateway(
            exchange_name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )
        await gateway.initialize()

        received_snapshots = []

        async def on_update(snapshot: AccountSnapshot):
            received_snapshots.append(snapshot)

        # 订阅 5 秒后取消
        async def subscribe_with_timeout():
            await asyncio.wait_for(
                gateway.subscribe_account_updates(on_update),
                timeout=5.0
            )

        try:
            await subscribe_with_timeout()
        except asyncio.TimeoutError:
            pass  # 预期行为

        await gateway.close()

        # 验证至少收到一次更新
        assert len(received_snapshots) > 0

    @pytest.mark.asyncio
    async def test_fallback_to_polling(self):
        """测试 WebSocket 失败时降级到轮询"""
        # 实现降级逻辑测试
        pass

    @pytest.mark.asyncio
    async def test_reconnect_logic(self):
        """测试重连逻辑"""
        # 实现重连测试
        pass
```

---

## 验收标准

### 功能验收
- [ ] WebSocket 能成功连接并接收资产更新
- [ ] 重连逻辑正常工作（指数退避）
- [ ] WebSocket 失败时自动降级到轮询
- [ ] 资产快照数据准确

### 代码验收
- [ ] 类型检查通过
- [ ] 所有测试通过
- [ ] 代码已提交 Git
- [ ] 无敏感信息泄露

### 文档验收
- [ ] 调研报告完成
- [ ] 代码注释完整
- [ ] 更新 CHANGELOG

---

## 相关文件

| 文件 | 操作 |
|------|------|
| `src/infrastructure/exchange_gateway.py` | 修改 - 新增 WebSocket 方法 |
| `src/domain/models.py` | 修改 - 新增配置模型 |
| `tests/integration/test_websocket_asset.py` | 创建 - 集成测试 |
| `docs/superpowers/specs/S5-1-1-ccxtpro-research.md` | 创建 - 调研报告 |

---

## 开始执行

**启动命令**（仅供参考，无需实际运行）:
```bash
# 1. 阅读现有代码
cat src/infrastructure/exchange_gateway.py

# 2. 创建调研报告
# 3. 实现代码
# 4. 运行测试
pytest tests/integration/test_websocket_asset.py -v

# 5. 提交 Git
git add -A
git commit -m "feat(S5-1): 实现 WebSocket 资产推送"
```

---

**开始执行任务！按顺序完成每个步骤，完成后标记验收标准。**
