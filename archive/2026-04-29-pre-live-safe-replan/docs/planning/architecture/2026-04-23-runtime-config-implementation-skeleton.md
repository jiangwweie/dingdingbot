# Runtime Config 实现骨架设计

> **Created**: 2026-04-23  
> **Status**: 骨架设计，供后续实现/Claude 执行使用  
> **Parent**: `docs/planning/architecture/2026-04-23-config-module-ssot-runtime-resolver-design.md`

---

## 1. 目标

为 Sim-1 ETH 模拟盘提供最小可用的 Runtime Config 骨架：

```text
.env environment
+ SQLite runtime profile
+ code safety defaults
=> ResolvedRuntimeConfig
=> main.py / SignalPipeline / ExecutionOrchestrator
```

本阶段不改 PG config、不扩前端、不恢复 YAML 启动链。

---

## 2. 推荐新增文件

| 文件 | 职责 |
|---|---|
| `src/application/runtime_config.py` | Pydantic 模型 + Resolver |
| `src/infrastructure/runtime_profile_repository.py` | SQLite runtime profile 仓储 |
| `scripts/seed_sim1_runtime_profile.py` | 写入/更新 `sim1_eth_runtime` profile |
| `scripts/verify_sim1_runtime_config.py` | 只解析配置，不启动交易 |

> 注：如果实现时希望拆得更细，可把模型放到 `src/application/config/runtime_models.py`，但第一版不必过度拆分。

---

## 3. SQLite 表建议

短期新增一张窄表，不改现有 `strategies / system_configs / risk_configs`：

```sql
CREATE TABLE IF NOT EXISTS runtime_profiles (
    name TEXT PRIMARY KEY,
    description TEXT,
    profile_json TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    is_readonly BOOLEAN NOT NULL DEFAULT FALSE,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_runtime_profiles_active
ON runtime_profiles(is_active);
```

设计理由：

1. 避免在 Sim-1 前强拆现有历史 config tables。
2. 用一份 profile JSON 固化五模块结构，降低短期实现成本。
3. 后续迁 PG 时，repo adapter 可替换，不影响 `ResolvedRuntimeConfig`。

---

## 4. Pydantic 模型骨架

```python
class EnvironmentRuntimeConfig(BaseModel):
    pg_database_url: SecretStr
    core_execution_intent_backend: Literal["postgres"]
    core_order_backend: Literal["sqlite", "postgres"] = "sqlite"
    core_position_backend: Literal["sqlite", "postgres"] = "sqlite"
    exchange_name: str = "binance"
    exchange_testnet: bool = True
    exchange_api_key: SecretStr
    exchange_api_secret: SecretStr
    feishu_webhook_url: SecretStr
    backend_port: int = 8000


class MarketRuntimeConfig(BaseModel):
    primary_symbol: str
    primary_timeframe: str
    mtf_timeframe: str
    warmup_history_bars: int
    asset_polling_interval: int

    @property
    def subscribed_pairs(self) -> list[tuple[str, str]]:
        return [
            (self.primary_symbol, self.primary_timeframe),
            (self.primary_symbol, self.mtf_timeframe),
        ]


class StrategyRuntimeConfig(BaseModel):
    allowed_directions: list[Direction]
    trigger: dict
    filters: list[dict]
    atr_enabled: bool = False


class RiskRuntimeConfig(BaseModel):
    max_loss_percent: Decimal
    max_leverage: int
    max_total_exposure: Decimal
    daily_max_trades: int | None = None
    daily_max_loss_percent: Decimal


class ExecutionRuntimeConfig(BaseModel):
    tp_levels: int
    tp_ratios: list[Decimal]
    tp_targets: list[Decimal]
    initial_stop_loss_rr: Decimal = Decimal("-1.0")
    breakeven_enabled: bool = False
    trailing_stop_enabled: bool = False
    oco_enabled: bool = True

    def to_order_strategy(self) -> OrderStrategy: ...


class ResolvedRuntimeConfig(BaseModel):
    profile_name: str
    version: int
    config_hash: str
    environment: EnvironmentRuntimeConfig
    market: MarketRuntimeConfig
    strategy: StrategyRuntimeConfig
    risk: RiskRuntimeConfig
    execution: ExecutionRuntimeConfig
```

---

## 5. Resolver 伪代码

```python
class RuntimeConfigResolver:
    def __init__(
        self,
        profile_repo: RuntimeProfileRepository,
        env: Mapping[str, str] | None = None,
    ):
        self._profile_repo = profile_repo
        self._env = env or os.environ

    async def resolve(self, profile_name: str) -> ResolvedRuntimeConfig:
        profile = await self._profile_repo.get(profile_name)
        env_config = self._resolve_environment()
        merged = {
            "profile_name": profile.name,
            "version": profile.version,
            "environment": env_config,
            "market": profile.market,
            "strategy": profile.strategy,
            "risk": profile.risk,
            "execution": profile.execution,
        }
        merged["config_hash"] = stable_hash(masked_non_secret_payload(merged))
        return ResolvedRuntimeConfig.model_validate(merged)
```

Resolver 验收：

1. 缺 `PG_DATABASE_URL` 直接 F-003。
2. 缺 exchange key/secret 直接 F-003。
3. 缺 webhook 直接 F-003，除非 notification 明确 disabled。
4. `CORE_EXECUTION_INTENT_BACKEND` 必须是 `postgres`。
5. `CORE_ORDER_BACKEND` 默认/冻结为 `sqlite`。
6. `execution.tp_ratios` 总和必须为 1。
7. `market.primary_symbol` 必须等于 `ETH/USDT:USDT`。

---

## 6. `sim1_eth_runtime` profile 初始内容

```json
{
  "market": {
    "primary_symbol": "ETH/USDT:USDT",
    "primary_timeframe": "1h",
    "mtf_timeframe": "4h",
    "warmup_history_bars": 100,
    "asset_polling_interval": 60
  },
  "strategy": {
    "allowed_directions": ["LONG"],
    "trigger": {
      "type": "pinbar",
      "enabled": true,
      "params": {
        "min_wick_ratio": "0.6",
        "max_body_ratio": "0.3",
        "body_position_tolerance": "0.1"
      }
    },
    "filters": [
      {
        "type": "ema",
        "enabled": true,
        "params": {
          "period": 50,
          "min_distance_pct": "0.005"
        }
      },
      {
        "type": "mtf",
        "enabled": true,
        "params": {
          "source_timeframe": "4h",
          "ema_period": 60
        }
      },
      {
        "type": "atr",
        "enabled": false,
        "params": {}
      }
    ],
    "atr_enabled": false
  },
  "risk": {
    "max_loss_percent": "0.01",
    "max_leverage": 20,
    "max_total_exposure": "1.0",
    "daily_max_trades": 10,
    "daily_max_loss_percent": "0.10"
  },
  "execution": {
    "tp_levels": 2,
    "tp_ratios": ["0.5", "0.5"],
    "tp_targets": ["1.0", "3.5"],
    "initial_stop_loss_rr": "-1.0",
    "breakeven_enabled": false,
    "trailing_stop_enabled": false,
    "oco_enabled": true
  }
}
```

---

## 7. 主程序接入顺序

第一阶段只接 environment 与 profile 解析，不改完整运行链：

1. `main.py` Phase 0.5：初始化 `RuntimeConfigResolver`
2. 解析 `sim1_eth_runtime`
3. 打印脱敏 effective config
4. ExchangeGateway 用 resolver 的 environment secret
5. NotificationService 用 resolver 的 webhook secret
6. `SignalPipeline` 暂继续按旧 ConfigManager 创建，但下一阶段改为吃 resolved market/strategy/risk

第二阶段再切运行消费：

1. `SignalPipeline` 使用 resolved market/strategy/risk
2. `SignalPipeline` execution hook 使用 `resolved.execution.to_order_strategy()`
3. `ConfigManager` 热重载对当前运行进程失效或被拒绝

---

## 8. Claude 执行边界

Claude 可执行：

1. 新增 SQLite `runtime_profiles` 仓储。
2. 新增 Pydantic 模型。
3. 新增 seed/verify 脚本。
4. 补局部测试或语法检查。

Claude 不应自行决定：

1. 是否把 config 迁 PG。
2. 是否删除现有 SQLite config tables。
3. 是否改变 Sim-1 ETH 参数。
4. 是否允许热改 strategy/risk/execution。
5. 是否让 backtest/Optuna 写 runtime profile。

