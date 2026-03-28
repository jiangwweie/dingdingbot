# Phase 5 详细设计文档

**版本**: v1.0
**创建日期**: 2026-03-27
**阶段目标**: 完善用户体验和系统稳定性 - WebSocket 实时推送 + 信号状态跟踪

---

## 一、Phase 5 概述

### 1.1 任务拆分原则

为避免 OOM（上下文溢出），将每个子任务拆分为 **独立可执行的微任务**，每个微任务：
- 聚焦单一文件或少量相关文件
- 有明确的验收标准
- 可独立测试和验证
- 完成后立即提交 Git

### 1.2 任务依赖图

```
Phase 5
├── S5-1: WebSocket 资产推送 (拆分为 6 个微任务)
│   ├── S5-1-1: CCXT.Pro WebSocket 调研与原型验证
│   ├── S5-1-2: WebSocket 账户订阅接口设计
│   ├── S5-1-3: 实现 WebSocket 资产推送
│   ├── S5-1-4: 实现资产快照更新回调
│   ├── S5-1-5: 降级轮询机制（WebSocket 失败时）
│   └── S5-1-6: 集成测试与日志验证
│
└── S5-2: 信号 pending 状态跟踪 (拆分为 5 个微任务)
    ├── S5-2-1: 信号状态机模型设计
    ├── S5-2-2: 实现 SignalStatusTracker
    ├── S5-2-3: 信号落库时初始化状态
    ├── S5-2-4: 状态查询 API 端点
    └── S5-2-5: 前端状态展示 UI
```

---

## 二、S5-1: 交易所 WebSocket 资产推送

### 2.1 目标

将当前的 **轮询模式** 改为 **WebSocket 实时推送**，降低延迟和 API 请求频率。

### 2.2 当前架构（轮询模式）

```python
# exchange_gateway.py 现有代码
async def _poll_assets_loop(self, interval_seconds: int = 60) -> None:
    """每 60 秒轮询一次账户余额和持仓"""
    while True:
        balance = await self.rest_exchange.fetch_balance()
        positions = await self.rest_exchange.fetch_positions()
        self._account_snapshot = parse_snapshot(balance, positions)
        await asyncio.sleep(interval_seconds)
```

**问题**:
- 延迟高（最多 60 秒延迟）
- API 请求频繁（容易触发限流）
- 无法实时响应资产变化

### 2.3 目标架构（WebSocket 模式）

```
币安 WebSocket → CCXT.Pro → on_balance_update() → 更新快照 → 通知信号管道
                      ↓
                 重连失败 → 降级轮询
```

### 2.4 微任务拆分

#### S5-1-1: CCXT.Pro WebSocket 调研与原型验证

**文件**: `docs/superpowers/specs/S5-1-1-ccxtpro-research.md`

**任务**:
1. 调研 CCXT.Pro 支持的交易所 WebSocket 频道
2. 验证币安 WebSocket 账户推送接口
3. 编写原型代码测试连接

**验收标准**:
- 确认币安 WebSocket 支持账户余额推送
- 原型代码能成功订阅并接收消息
- 文档记录订阅频道和消息格式

**预估耗时**: 1 小时

---

#### S5-1-2: WebSocket 账户订阅接口设计

**文件**:
- `src/domain/models.py` - 新增 WebSocket 配置模型
- `src/infrastructure/exchange_gateway.py` - 新增 WebSocket 订阅方法签名

**任务**:
1. 定义 `WebSocketAssetConfig` 模型
2. 定义 `AssetUpdateCallback` 类型
3. 在 `ExchangeGateway` 添加 `subscribe_account_updates()` 方法签名

**验收标准**:
- 类型定义完整
- 方法签名符合异步回调模式
- 通过类型检查 `mypy --strict`

**预估耗时**: 0.5 小时

---

#### S5-1-3: 实现 WebSocket 资产推送

**文件**: `src/infrastructure/exchange_gateway.py`

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
    # 1. 创建 WebSocket 连接
    # 2. 订阅账户频道
    # 3. 解析消息并回调
    # 4. 重连逻辑（指数退避）
```

**关键点**:
- 使用 `ccxtpro.watch_balance()` 或交易所特定方法
- 重连逻辑复用 `_subscribe_single_ohlcv` 的模式
- 解析消息格式适配币安

**预估耗时**: 2 小时

---

#### S5-1-4: 实现资产快照更新回调

**文件**:
- `src/infrastructure/exchange_gateway.py` - 解析 WebSocket 消息
- `src/application/signal_pipeline.py` - 接收资产更新

**任务**:
1. 实现 `_parse_ws_balance()` 解析函数
2. 将 WebSocket 消息转换为 `AccountSnapshot`
3. 调用回调函数更新信号管道

**预估耗时**: 1 小时

---

#### S5-1-5: 降级轮询机制

**文件**: `src/infrastructure/exchange_gateway.py`

**逻辑**:
```python
async def subscribe_account_updates(self, callback):
    try:
        await self._ws_subscribe_account(callback)
    except Exception as e:
        logger.warning(f"WebSocket 失败，降级到轮询：{e}")
        # 回退到原有轮询模式
        await self._poll_assets_loop_fallback(callback)
```

**任务**:
1. 保留原有轮询代码作为降级方案
2. WebSocket 失败时自动切换
3. 记录降级日志

**预估耗时**: 1 小时

---

#### S5-1-6: 集成测试与日志验证

**文件**: `tests/integration/test_websocket_asset.py`

**测试场景**:
1. WebSocket 正常接收测试
2. WebSocket 失败降级轮询测试
3. 重连逻辑测试
4. 资产快照准确性测试

**预估耗时**: 1.5 小时

---

### 2.5 S5-1 总结

| 微任务 | 文件 | 预估工时 |
|--------|------|----------|
| S5-1-1 | 调研文档 | 1h |
| S5-1-2 | models.py, exchange_gateway.py | 0.5h |
| S5-1-3 | exchange_gateway.py | 2h |
| S5-1-4 | exchange_gateway.py, signal_pipeline.py | 1h |
| S5-1-5 | exchange_gateway.py | 1h |
| S5-1-6 | test_websocket_asset.py | 1.5h |
| **总计** | | **7 小时** |

---

## 三、S5-2: 信号 pending 状态跟踪

### 3.1 目标

跟踪信号从生成到成交的全流程状态，提供状态查询 API。

### 3.2 状态机设计

```
┌─────────────┐
│  Generated  │ 信号生成
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   PENDING   │ 等待成交
└──────┬──────┘
       │
       ├──→ FILLED ──→ 已成交
       ├──→ CANCELLED ──→ 已取消
       └──→ REJECTED ──→ 被拒绝
```

### 3.3 微任务拆分

#### S5-2-1: 信号状态机模型设计

**文件**:
- `src/domain/models.py` - 新增 `SignalStatus` 枚举和 `SignalTrack` 模型

**新增模型**:
```python
class SignalStatus(str, Enum):
    GENERATED = "generated"      # 已生成
    PENDING = "pending"          # 等待成交
    FILLED = "filled"            # 已成交
    CANCELLED = "cancelled"      # 已取消
    REJECTED = "rejected"        # 被拒绝

class SignalTrack(BaseModel):
    """信号全生命周期跟踪"""
    signal_id: str
    original_signal: SignalResult
    status: SignalStatus
    created_at: int  # 毫秒时间戳
    updated_at: int  # 毫秒时间戳
    filled_price: Optional[Decimal] = None
    filled_at: Optional[int] = None
    reject_reason: Optional[str] = None
```

**预估耗时**: 0.5 小时

---

#### S5-2-2: 实现 SignalStatusTracker

**文件**: `src/application/signal_tracker.py` (新文件)

**核心功能**:
```python
class SignalStatusTracker:
    """信号状态跟踪器"""

    async def track_signal(self, signal: SignalResult) -> None:
        """开始跟踪信号"""

    async def update_status(
        self,
        signal_id: str,
        status: SignalStatus,
        filled_price: Optional[Decimal] = None,
    ) -> None:
        """更新信号状态"""

    async def get_signal_status(self, signal_id: str) -> Optional[SignalTrack]:
        """查询信号状态"""
```

**预估耗时**: 2 小时

---

#### S5-2-3: 信号落库时初始化状态

**文件**:
- `src/infrastructure/signal_repository.py` - 新增状态字段
- `src/application/signal_pipeline.py` - 调用 tracker

**任务**:
1. SQLite 表新增 `status` 字段
2. 保存信号时初始化为 `GENERATED`
3. 信号管道调用 `tracker.track_signal()`

**预估耗时**: 1 小时

---

#### S5-2-4: 状态查询 API 端点

**文件**: `src/interfaces/api.py`

**新增端点**:
```python
@app.get("/api/signals/{signal_id}/status")
async def get_signal_status(signal_id: str) -> SignalTrack:
    """查询信号状态"""

@app.get("/api/signals/status")
async def list_signal_statuses(
    status: Optional[SignalStatus] = None,
    limit: int = 50,
) -> List[SignalTrack]:
    """批量查询信号状态"""
```

**预估耗时**: 1 小时

---

#### S5-2-5: 前端状态展示 UI

**文件**:
- `web-front/src/lib/api.ts` - 新增 API 调用
- `web-front/src/pages/Signals.tsx` - 新增状态列
- `web-front/src/components/SignalStatusBadge.tsx` (新文件) - 状态徽章组件

**UI 设计**:
```
信号列表
┌─────────┬────────┬─────────┬────────────┐
│ 币种    │ 方向   │ 入场价  │ 状态       │
├─────────┼────────┼─────────┼────────────┤
│ BTC/USDT│ LONG   │ 68500   │ ● PENDING  │
│ ETH/USDT│ SHORT  │ 3820    │ ✓ FILLED   │
└─────────┴────────┴─────────┴────────────┘
```

**预估耗时**: 1.5 小时

---

### 3.4 S5-2 总结

| 微任务 | 文件 | 预估工时 |
|--------|------|----------|
| S5-2-1 | models.py | 0.5h |
| S5-2-2 | signal_tracker.py | 2h |
| S5-2-3 | signal_repository.py, signal_pipeline.py | 1h |
| S5-2-4 | api.py | 1h |
| S5-2-5 | api.ts, Signals.tsx, SignalStatusBadge.tsx | 1.5h |
| **总计** | | **6 小时** |

---

## 四、执行顺序与依赖

### 4.1 依赖关系

```
S5-1 (WebSocket 推送)
    │
    └── 独立完成，无依赖
    └── 为 S5-2 提供实时资产数据（可选）

S5-2 (信号状态跟踪)
    │
    └── 独立完成，不依赖 S5-1
    └── 未来可扩展：信号成交时推送通知
```

### 4.2 建议执行顺序

```
窗口 1: S5-1-1 → S5-1-2 → S5-1-3  (调研 + 设计 + 实现)
窗口 2: S5-1-4 → S5-1-5 → S5-1-6  (回调 + 降级 + 测试)
窗口 3: S5-2-1 → S5-2-2 → S5-2-3  (模型 + 跟踪器 + 落库)
窗口 4: S5-2-4 → S5-2-5           (API + 前端 UI)
```

---

## 五、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| CCXT.Pro WebSocket 接口变化 | 中 | 实现前验证最新文档，保留轮询降级 |
| 币安 WebSocket 限流 | 低 | 重连使用指数退避 |
| 状态机设计过度复杂 | 低 | 只跟踪核心状态，暂缓边缘状态 |
| 前端 UI 工作量大 | 低 | 使用简单徽章组件，不做复杂交互 |

---

## 六、验收标准

### Phase 5 完成标志

- [ ] S5-1 所有微任务完成
- [ ] S5-2 所有微任务完成
- [ ] 所有测试通过 (单元测试 + 集成测试)
- [ ] TypeScript 编译通过
- [ ] 创建 v0.5.0-phase5 发布说明
- [ ] 创建 Git 标签 v0.5.0-phase5

---

*最后更新：2026-03-27*
