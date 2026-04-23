# Sim-0.1 配置冻结报告

> 更新时间：2026-04-23
> 状态：✅ 通过
> 配置入口：`.env` / 进程环境变量
> 重要口径：YAML 配置已废弃，不参与 Sim-0 运行配置。
> 说明：敏感字段已脱敏；真实值仅保存在本地 `.env`，不要提交到远端。

---

## 1. 阻塞项修复结果

| 检查项 | 当前状态 | Sim-0 要求 | 结果 |
|---|---|---|---|
| `PG_DATABASE_URL` | 已配置（`.env`） | `postgresql+asyncpg://...` | ✅ 通过 |
| `CORE_EXECUTION_INTENT_BACKEND` | `postgres` | `postgres` | ✅ 通过 |
| `CORE_ORDER_BACKEND` | `sqlite` | `sqlite` | ✅ 通过 |
| `EXCHANGE_NAME` | `binance` | `binance` | ✅ 通过 |
| `EXCHANGE_TESTNET` | `true` | `true` | ✅ 通过 |
| `EXCHANGE_API_KEY` | `rmy4DPO0...tHlHA8hI` | Binance Testnet key | ✅ 已配置 |
| `EXCHANGE_API_SECRET` | `mP7Hk5r3...YXpqMFtR` | Binance Testnet secret | ✅ 已配置 |
| `FEISHU_WEBHOOK_URL` | `https://...435aafb7` | 可用 webhook | ✅ 已配置 |

---

## 2. YAML 状态

1. `config/user.yaml` / `config/core.yaml` 不作为 Sim-0 配置源。
2. 本地 `config/user.yaml` 已删除，避免误判运行配置来源。
3. 后续如代码仍读取 YAML，应视为技术债或兼容路径，不应作为 Sim-0 启动依据。

---

## 3. Sim-0 固定范围

1. 环境：Binance Testnet / 模拟盘
2. symbol：`BTC/USDT:USDT`
3. `CORE_EXECUTION_INTENT_BACKEND=postgres`
4. `CORE_ORDER_BACKEND=sqlite`
5. 恢复真源：PG `execution_recovery_tasks`
6. breaker：内存缓存，由 PG active recovery tasks 重建
7. 策略：当前冻结主线策略
8. Sim-0 运行中不热改策略参数

---

## 4. 启动前注意

当前代码未自动加载 `.env`，Sim-0.2 启动时需要使用：

```bash
set -a
source .env
set +a
python3 src/main.py
```

---

## 5. 仍需人工注意

1. API key/secret 必须只用于 Testnet，不能混用主网。
2. API key 禁止提现权限。
3. `.env` 包含敏感信息，不应提交到远端。

---

## 6. 结论

✅ Sim-0.1 配置冻结通过。

允许进入：**Sim-0.2 主程序真实启动验证**。
