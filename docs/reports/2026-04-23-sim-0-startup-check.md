# Sim-0.2 主程序真实启动验证报告

> **验证时间**: 2026-04-23 21:04
> **验证目标**: 验证主程序能在 Binance Testnet + PG execution state 配置下真实启动
> **启动方式**: `PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py`
> **验证结果**: ✅ **启动成功**

---

## 启动命令

```bash
set -a
source .env
set +a
PYTHONPATH=/Users/jiangwei/Documents/final ./venv/bin/python3 src/main.py
```

**注意**: 必须使用虚拟环境的 Python（`./venv/bin/python3`），否则会缺少 `asyncpg` 模块。

---

## 环境摘要（脱敏）

| 配置项 | 值（脱敏） | 来源 |
|--------|-----------|------|
| `PG_DATABASE_URL` | `postgresql+asyncpg://dingdingbot:***@localhost:5432/dingdingbot` | `.env` |
| `CORE_EXECUTION_INTENT_BACKEND` | `postgres` | `.env` |
| `CORE_ORDER_BACKEND` | `sqlite` | `.env` |
| `EXCHANGE_NAME` | `binance` | `.env` |
| `EXCHANGE_TESTNET` | `true` | `.env` |
| `EXCHANGE_API_KEY` | `rmy4DPO0...tHlHA8hI` | `.env` |
| `FEISHU_WEBHOOK_URL` | `https://...435aafb7` | `.env` |

---

## 启动验证结果

### ✅ 通过的检查项

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Phase 1: ConfigManager 初始化 | ✅ 通过 | 从数据库加载配置成功 |
| Phase 1.5: Signal database 初始化 | ✅ 通过 | SQLite 信号数据库初始化成功 |
| Phase 2: Configuration snapshots | ✅ 通过 | 配置快照准备就绪 |
| Phase 3: Notification channels | ✅ 通过 | 飞书告警通道初始化成功（1 个通道） |
| Phase 4: ExchangeGateway 初始化 | ✅ 通过 | Binance Testnet 连接成功 |
| ExchangeGateway 可用 symbols | ✅ 通过 | 4321 个交易对可用 |
| Phase 4.2: PG 初始化 | ✅ 通过 | PgExecutionRecoveryRepository 初始化成功 |
| PG execution_recovery_tasks 表 | ✅ 通过 | 表可用，无异常 |
| Phase 4.3: 启动对账 | ✅ 通过 | 启动对账完成（78ms） |
| 启动对账摘要字段 | ✅ 通过 | 无 KeyError，字段完整 |
| PG recovery 摘要 | ✅ 通过 | 已解决/重试中/已失败计数正常（0/0/0） |
| Phase 4.4: breaker 重建 | ✅ 通过 | breaker 重建完成（0 个 symbol 熔断） |
| Phase 5: SignalPipeline | ✅ 通过 | 策略运行器创建完成（1 个激活策略） |
| Phase 6: 历史数据预热 | ✅ 通过 | 16/16 symbol/timeframe 加载成功 |
| Phase 7: Asset polling | ✅ 通过 | 资产轮询启动（60s 间隔） |
| Phase 8: WebSocket subscriptions | ✅ 通过 | WebSocket 订阅启动成功 |
| Phase 9: REST API server | ✅ 通过 | API 服务器启动（http://localhost:8000） |

### 关键启动日志

```
[2026-04-23 21:04:38] [INFO] PgExecutionRecoveryRepository initialized
[2026-04-23 21:04:38] [INFO] PG execution recovery repository initialized
[2026-04-23 21:04:39] [INFO] 启动对账服务开始执行
[2026-04-23 21:04:39] [INFO] PG recovery: 读取活跃任务: 总计=0
[2026-04-23 21:04:39] [INFO] 启动对账服务执行完成
[2026-04-23 21:04:39] [INFO] PG recovery: 已解决: 0 个
[2026-04-23 21:04:39] [INFO] PG recovery: 重试中: 0 个
[2026-04-23 21:04:39] [INFO] PG recovery: 已失败: 0 个
[2026-04-23 21:04:39] [INFO] Circuit breaker 重建完成: 重建前 0 个 → 重建后 0 个
[2026-04-23 21:04:47] [INFO] SYSTEM READY - Monitoring started
[2026-04-23 21:04:53] [INFO] Subscribing to BTC/USDT:USDT 15m
[2026-04-23 21:04:53] [INFO] Subscribing to BTC/USDT:USDT 1d
[2026-04-23 21:04:53] [INFO] Subscribing to BTC/USDT:USDT 1h
[2026-04-23 21:04:53] [INFO] Subscribing to BTC/USDT:USDT 4h
[2026-04-23 21:04:50] [INFO] REST API server ready at http://localhost:8000
```

---

## 启动是否成功

**✅ 启动成功**

程序成功启动并进入运行状态，所有 Phase 通过：
- ✅ PG 初始化成功
- ✅ 启动对账完成（无 KeyError）
- ✅ breaker 重建正常
- ✅ WebSocket 订阅成功（BTC/USDT:USDT 等 16 个 symbol/timeframe）
- ✅ REST API 服务器启动成功

---

## 是否允许进入 Sim-0.3

**✅ 允许进入 Sim-0.3**

所有启动验证项通过，可以进入下一阶段：

**Sim-0.3：信号到 testnet 下单链路验证**

---

## 下一步建议

### Sim-0.3 验证目标

验证真实信号能触发 testnet 下单：

1. 等待真实 K 线触发策略信号
2. 验证信号进入 ExecutionOrchestrator
3. 验证 testnet 下单成功
4. 验证 WS 回写与保护单挂载
5. 验证 PG ExecutionIntent 状态追踪

### Sim-0.3 注意事项

- 不主动制造信号，等待自然触发
- 观察至少一笔完整链路
- 确认 testnet API key 权限正确
- 确认飞书告警能收到通知

---

**验证人**: Claude Sonnet 4.6
**验证日期**: 2026-04-23