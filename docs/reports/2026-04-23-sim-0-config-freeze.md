# Sim-0.1 配置冻结报告

> 更新时间：2026-04-23
> 状态：✅ 通过
> 说明：敏感字段已脱敏；真实值只保存在本地忽略文件中，不提交仓库。

---

## 1. 阻塞项修复结果

| 检查项 | 当前状态 | Sim-0 要求 | 结果 |
|---|---|---|---|
| `PG_DATABASE_URL` | 已配置（本地 `.env`） | `postgresql+asyncpg://...` | ✅ 通过 |
| `CORE_EXECUTION_INTENT_BACKEND` | `postgres`（本地 `.env`） | `postgres` | ✅ 通过 |
| `CORE_ORDER_BACKEND` | `sqlite`（本地 `.env`） | `sqlite` | ✅ 通过 |
| `exchange.name` | `binance` | `binance` | ✅ 通过 |
| `exchange.testnet` | `true` | `true` | ✅ 通过 |
| `exchange.api_key` | `rmy4DPO0...tHlHA8hI` | Binance Testnet key | ✅ 已配置 |
| `exchange.api_secret` | `mP7Hk5r3...YXpqMFtR` | Binance Testnet secret | ✅ 已配置 |
| 飞书 webhook | `https://...435aafb7` | 可用 webhook | ✅ 已配置 |

---

## 2. Sim-0 固定范围

1. 环境：Binance Testnet / 模拟盘
2. symbol：`BTC/USDT:USDT`
3. `CORE_EXECUTION_INTENT_BACKEND=postgres`
4. `CORE_ORDER_BACKEND=sqlite`
5. 恢复真源：PG `execution_recovery_tasks`
6. breaker：内存缓存，由 PG active recovery tasks 重建
7. 策略：当前冻结主线策略
8. Sim-0 运行中不热改策略参数

---

## 3. 仍需人工注意

1. API key/secret 必须只用于 Testnet，不能混用主网。
2. API key 禁止提现权限。
3. `.env` 与 `config/user.yaml` 均为本地忽略文件，不应提交真实密钥。

---

## 4. 结论

✅ Sim-0.1 配置冻结通过。

允许进入：**Sim-0.2 主程序真实启动验证**。
