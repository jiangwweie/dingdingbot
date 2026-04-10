# 日志错误诊断报告

> **诊断日期**: 2026-03-29
> **日志时间段**: 2026-03-29 16:39 - 17:08 (约 30 分钟)
> **日志文件**: `logs/dingdingbot.log` (5102 行)
> **诊断分析师**: Diagnostic Analyst

---

## 执行摘要

在 30 分钟的日志样本中，共发现 **227 条错误日志**，经过去重分析，识别出 **6 类独立错误**。

| 错误类型 | 出现次数 | 占比 | 严重程度 |
|----------|----------|------|----------|
| `MagicMock can't be used in 'await'` | 171 | 75.3% | 🔴 高 |
| `AtrFilterDynamic is not defined` | 16 | 7.0% | 🟠 中 |
| `Feishu webhook returned 500` | 11 | 4.8% | 🟡 低 |
| `Failed to send Feishu notification` | 11 | 4.8% | 🟡 低 |
| `Connection error` (OHLCV) | 8 | 3.5% | 🟡 低 |
| `DB error` | 7 | 3.1% | 🟠 中 |
| `AsyncMock.keys() returned non-iterable` | 2 | 0.9% | 🟡 低 |
| `__aenter__` error | 1 | 0.4% | 🟡 低 |

---

## 错误详细分析

### 🔴 错误 #1: `object MagicMock can't be used in 'await' expression`

**出现次数**: 171 次 (75.3%)

**错误日志示例**:
```
[2026-03-29 16:39:21] [ERROR] Error checking pending signals: object MagicMock can't be used in 'await' expression
```

**问题位置**: `src/application/performance_tracker.py:34`

**根因分析**:

1. **现象**: `check_pending_signals()` 方法中调用 `repository.get_pending_signals()` 时出错
2. **原因**: 代码中使用了 `MagicMock` 对象作为 `repository`，但 `MagicMock` 默认返回同步对象，不能 `await`
3. **触发场景**: 这很可能是**测试代码或初始化时的占位符代码**遗留到生产环境

**代码定位**:
```python
# src/application/performance_tracker.py:34
pending_signals = await repository.get_pending_signals(kline.symbol)
```

**5 Why 分析**:
```
Why 1: 为什么会出现 MagicMock?
  → repository 没有被正确初始化

Why 2: 为什么 repository 没有被正确初始化?
  → SignalPipeline 初始化时 repository 参数可能是 Mock 对象

Why 3: 为什么会使用 Mock 对象?
  → 可能是测试代码或临时调试代码未清理

Why 4: 为什么测试代码会进入生产环境?
  → 缺少运行环境检查或配置切换机制

Why 5: 为什么没有环境隔离?
  → 需要添加环境感知的初始化逻辑
```

**解决方案**:

| 方案 | 说明 | 优先级 | 工作量 |
|------|------|--------|--------|
| **A: 修复 repository 初始化** | 检查 `SignalPipeline` 的 `_repository` 属性，确保生产环境使用真实的 `SignalRepository` 实例 | 🔴 P0 | 30min |
| **B: 添加异步 Mock 支持** | 如确实需要 Mock，使用 `AsyncMock` 替代 `MagicMock` | 🟡 P2 | 15min |
| **C: 添加环境检查** | 在初始化时检测运行环境，生产环境禁止使用 Mock | 🟢 P3 | 1h |

**推荐执行顺序**: A → C

---

### 🟠 错误 #2: `name 'AtrFilterDynamic' is not defined`

**出现次数**: 16 次 (7.0%)

**错误日志示例**:
```
[2026-03-29 16:39:34] [ERROR] Error processing K-line: name 'AtrFilterDynamic' is not defined
```

**问题位置**: 策略引擎动态加载过滤器时

**根因分析**:

1. **现象**: K 线处理时尝试使用 `AtrFilterDynamic` 类但未定义
2. **已确认**: `AtrFilterDynamic` 类在 `src/domain/filter_factory.py:332` 已定义
3. **已确认**: `src/domain/strategy_engine.py:21` 已导入该类
4. **可能原因**:
   - 配置文件中引用了过滤器，但动态加载时命名空间不包含该类
   - 过滤器工厂的 `create_filter()` 方法可能无法正确解析 `atr_volatility` 类型

**代码定位**:
```python
# src/domain/filter_factory.py:332
class AtrFilterDynamic(FilterBase):
    """ATR volatility filter for filtering out low-volatility noise."""
```

**5 Why 分析**:
```
Why 1: 为什么 AtrFilterDynamic 已定义但仍报错?
  → 动态加载时找不到类名

Why 2: 动态加载如何查找类?
  → 可能通过字符串名称查找 (如 filter_type == "atr_volatility")

Why 3: 查找映射是否正确配置?
  → 检查 FilterFactory.create_filter() 中的类型映射

Why 4: 类型映射是否包含 atr_volatility?
  → 需要验证 FilterFactory 的实现
```

**解决方案**:

| 方案 | 说明 | 优先级 | 工作量 |
|------|------|--------|--------|
| **A: 检查 FilterFactory 映射** | 确认 `FilterFactory.create_filter()` 中有 `atr_volatility` → `AtrFilterDynamic` 的映射 | 🔴 P0 | 15min |
| **B: 检查用户配置** | 检查 `config/user.yaml` 中是否正确配置了 ATR 过滤器类型名称 | 🟠 P1 | 10min |
| **C: 添加过滤器注册表** | 实现自动发现机制，避免手动维护映射 | 🟢 P3 | 2h |

**推荐执行顺序**: B → A → C

---

### 🟡 错误 #3: `Feishu webhook returned 500`

**出现次数**: 11 次 (4.8%)

**错误日志示例**:
```
[2026-03-29 16:39:34] [ERROR] Feishu webhook returned 500
```

**问题位置**: `src/infrastructure/notifier.py:307`

**根因分析**:

1. **现象**: 飞书 webhook 返回 HTTP 500 错误
2. **原因**:
   - 飞书服务端问题（可能性低）
   - Webhook URL 配置错误（可能性中）
   - 消息格式不符合飞书规范（可能性高）
   - 网络问题（可能性中）

**解决方案**:

| 方案 | 说明 | 优先级 | 工作量 |
|------|------|--------|--------|
| **A: 验证 Webhook URL** | 检查 `config/user.yaml` 中的飞书 webhook URL 是否正确有效 | 🔴 P0 | 5min |
| **B: 检查消息格式** | 对比飞书开放平台文档，确认 Markdown 格式正确 | 🟠 P1 | 30min |
| **C: 添加重试机制** | webhook 失败时自动重试（指数退避） | 🟢 P2 | 1h |
| **D: 添加降级策略** | webhook 连续失败时切换到备用通知渠道 | 🟢 P3 | 2h |

**推荐执行顺序**: A → B → C

---

### 🟡 错误 #4: `Failed to send Feishu notification: __aenter__`

**出现次数**: 11 次 (4.8%)

**错误日志示例**:
```
[2026-03-29 16:39:34] [ERROR] Failed to send Feishu notification: __aenter__
```

**问题位置**: `src/infrastructure/notifier.py:278-323`

**根因分析**:

1. **现象**: `__aenter__` 错误通常与 async context manager 有关
2. **原因**: `aiohttp.ClientSession` 的异步上下文管理器使用不当
3. **可能场景**:
   - session 对象未正确初始化
   - session 已关闭但仍在使用
   - 嵌套异步上下文管理器使用错误

**代码定位**:
```python
# src/infrastructure/notifier.py:278
async def send(self, message: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:  # __aenter__ 可能失败
            async with session.post(self.webhook_url, json=...) as response:
                ...
```

**解决方案**:

| 方案 | 说明 | 优先级 | 工作量 |
|------|------|--------|--------|
| **A: 复用 ClientSession** | 创建全局或单例的 ClientSession，避免频繁创建销毁 | 🔴 P0 | 1h |
| **B: 添加 session 生命周期管理** | 确保 session 在使用前已正确初始化 | 🟠 P1 | 30min |
| **C: 添加异常包装** | 捕获具体异常并记录更详细的错误信息 | 🟡 P2 | 15min |

**推荐执行顺序**: A → B → C

---

### 🟡 错误 #5: `Failed to fetch historical OHLCV: Connection error`

**出现次数**: 8 次 (3.5%)

**错误日志示例**:
```
[2026-03-29 16:39:20] [ERROR] Failed to fetch historical OHLCV for BTC/USDT:USDT 1h: Connection error
```

**问题位置**: `src/infrastructure/exchange_gateway.py`

**根因分析**:

1. **现象**: 获取历史 K 线数据时连接错误
2. **原因**:
   - 交易所 API 暂时不可用（币安等）
   - 网络连接问题
   - API 限流/封禁
   - WebSocket 连接未正确建立

**解决方案**:

| 方案 | 说明 | 优先级 | 工作量 |
|------|------|--------|--------|
| **A: 添加重试机制** | 连接失败时自动重试（指数退避） | 🟠 P1 | 1h |
| **B: 添加连接健康检查** | 启动时验证交易所连接状态 | 🟠 P1 | 30min |
| **C: 添加 API 限流处理** | 检测 429 错误并自动降级请求频率 | 🟡 P2 | 1h |
| **D: 添加错误日志级别** | 降级为 WARNING（因为是预期内的临时错误） | 🟡 P2 | 5min |

**推荐执行顺序**: D → B → A → C

---

### 🟠 错误 #6: `DB error`

**出现次数**: 7 次 (3.1%)

**错误日志示例**:
```
[2026-03-29 16:39:34] [ERROR] Error checking pending signals: DB error
```

**问题位置**: `src/application/performance_tracker.py` → `SignalRepository`

**根因分析**:

1. **现象**: 数据库操作失败
2. **可能原因**:
   - SQLite 数据库文件被锁定
   - 并发写入冲突
   - 数据库连接未正确关闭
   - Schema 不匹配

**解决方案**:

| 方案 | 说明 | 优先级 | 工作量 |
|------|------|--------|--------|
| **A: 检查数据库锁** | 查看 `data/signals.db` 是否有锁文件 (-journal, -wal) | 🔴 P0 | 5min |
| **B: 添加连接池管理** | 使用 asyncio 安全的连接池 | 🟠 P1 | 2h |
| **C: 添加重试逻辑** | 数据库锁定时等待并重试 | 🟠 P1 | 30min |
| **D: 优化事务隔离** | 减少锁持有时间 | 🟡 P2 | 1h |

**推荐执行顺序**: A → C → B

---

## 问题优先级汇总

| 优先级 | 问题 | 建议方案 | 预计工作量 |
|--------|------|----------|------------|
| **P0** | MagicMock await 错误 | 修复 repository 初始化 | 30min |
| **P0** | AtrFilterDynamic 未定义 | 检查 FilterFactory 映射和用户配置 | 25min |
| **P0** | Feishu webhook 500 | 验证 webhook URL | 5min |
| **P0** | aiohttp ClientSession 错误 | 复用 session 单例 | 1h |
| **P1** | DB error | 检查数据库锁，添加重试 | 35min |
| **P2** | OHLCV 连接错误 | 添加重试和降级日志 | 1h5min |

**总计预计修复时间**: ~3.5 小时

---

## 系统性问题识别

### 1. 测试代码污染生产环境 ⚠️

**问题**: `MagicMock` 出现在生产日志中，表明测试代码和运行代码没有适当隔离。

**建议**:
- 添加环境检查机制（`ENV=production` vs `ENV=test`）
- 生产环境禁止使用 Mock 对象
- 使用依赖注入框架管理真实/模拟实现

### 2. 缺少错误恢复机制 ⚠️

**问题**: Webhook、DB、交易所连接失败后没有自动重试。

**建议**:
- 实现统一的重试装饰器（指数退避）
- 添加熔断器模式，防止雪崩
- 记录重试指标用于监控

### 3. 缺少资源生命周期管理 ⚠️

**问题**: `aiohttp.ClientSession` 未正确管理生命周期。

**建议**:
- 创建全局单例 session（应用启动时创建，关闭时销毁）
- 使用 async context manager 管理资源
- 添加资源泄漏检测

---

## 建议修复顺序

```
1. 验证 Feishu webhook URL (5min)
2. 修复 repository 初始化 (30min)
3. 检查 ATR 过滤器配置和映射 (25min)
4. 修复 ClientSession 管理 (1h)
5. 检查数据库锁状态 (5min)
6. 添加数据库重试逻辑 (30min)
7. 添加交易所连接重试 (1h)
8. 添加环境隔离机制 (1h)
```

---

## 下一步行动

1. **立即执行** (P0):
   - [ ] 验证 Feishu webhook URL 配置
   - [ ] 检查 `SignalPipeline._repository` 初始化
   - [ ] 检查 `FilterFactory.create_filter()` 映射

2. **今天内完成** (P1):
   - [ ] 修复 aiohttp session 管理
   - [ ] 检查数据库锁状态并添加重试

3. **本周内完成** (P2+):
   - [ ] 实现统一重试机制
   - [ ] 添加环境隔离
   - [ ] 实现连接健康检查

---

*报告生成时间：2026-03-29*
*诊断分析师：Diagnostic Analyst*
