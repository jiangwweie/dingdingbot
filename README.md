# Crypto Signal Monitor

加密货币信号监测与风险评估系统 - 基于 Pinbar 形态识别、EMA 趋势过滤和多周期校验的交易信号监测系统。

**核心原则：Zero Execution Policy（零执行政策）** - 系统仅为观测与通知工具，严禁集成任何交易下单接口。

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置文件

编辑 `config/user.yaml` 设置你的交易所凭证和偏好：

```yaml
exchange:
  name: "binance"
  api_key: "your-read-only-api-key"
  api_secret: "your-secret"
  testnet: true

timeframes:
  - "15m"
  - "1h"
  - "4h"

notification:
  channels:
    - type: "feishu"
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

### 3. 运行系统

```bash
python src/main.py
```

## 项目结构

```
crypto-signal-monitor/
├── src/
│   ├── domain/                 # 领域核心层（策略/风控计算）
│   │   ├── models.py           # Pydantic 数据模型
│   │   ├── exceptions.py       # 统一异常体系
│   │   ├── indicators.py       # EMA 指标计算
│   │   ├── strategy_engine.py  # Pinbar 策略引擎
│   │   └── risk_calculator.py  # 风控试算
│   │
│   ├── application/            # 应用服务层
│   │   ├── config_manager.py   # 配置加载与合并
│   │   └── signal_pipeline.py  # 信号处理管道
│   │
│   ├── infrastructure/         # 基础设施层（所有 I/O）
│   │   ├── exchange_gateway.py # 交易所网关（REST+WS）
│   │   ├── notifier.py         # 通知推送（飞书/企微）
│   │   └── logger.py           # 日志与脱敏
│   │
│   └── main.py                 # 启动入口
│
├── config/
│   ├── core.yaml               # 系统核心配置（只读）
│   └── user.yaml               # 用户配置（可修改）
│
└── tests/
    └── unit/                   # 单元测试
```

## 核心功能

### 信号识别策略

1. **Pinbar 形态检测**
   - 颜色不敏感（阴阳线均可）
   - 基于影线/实体/全长的几何比例关系
   - 可配置参数：`min_wick_ratio`, `max_body_ratio`, `body_position_tolerance`

2. **EMA60 趋势过滤**
   - 价格在 EMA 上方：仅识别看多信号
   - 价格在 EMA 下方：仅识别看空信号
   - 可通过 `trend_filter_enabled` 开关

3. **多周期（MTF）校验**
   - 跨周期共振验证：15m→1h, 1h→4h, 4h→1d, 1d→1w
   - 可通过 `mtf_validation_enabled` 开关

### 风控试算

- 单笔最大损失：基于账户余额百分比（默认 1%）
- 仓位计算公式：`Position_Size = (Balance × Loss_Percent) / Stop_Loss_Distance`
- 杠杆熔断：强制遵循配置的 `max_leverage` 上限
- 所有计算使用 `Decimal` 类型，严禁 `float` 精度丢失

### 通知推送

- 支持飞书 Webhook 和企业微信机器人
- 纯文本 Markdown 格式，禁止截图
- 核心字段：币种、周期、方向、入场价、止损、仓位、MTF 状态、EMA 趋势

## 配置说明

### 核心配置（`config/core.yaml`）

系统级配置，通常不需要修改：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `core_symbols` | 核心监测币种 | BTC, ETH, SOL, BNB |
| `pinbar_defaults.min_wick_ratio` | 影线占比下限 | 0.6 |
| `pinbar_defaults.max_body_ratio` | 实体占比上限 | 0.3 |
| `ema.period` | EMA 周期 | 60 |
| `warmup.history_bars` | REST 预热 K 线数量 | 100 |

### 用户配置（`config/user.yaml`）

用户可根据需要修改：

| 参数 | 说明 |
|------|------|
| `exchange.api_key` | 交易所 API Key（**只读权限**） |
| `exchange.testnet` | 是否使用测试网 |
| `user_symbols` | 自定义监测币种 |
| `timeframes` | 监测时间周期 |
| `strategy.trend_filter_enabled` | EMA 趋势过滤开关 |
| `strategy.mtf_validation_enabled` | MTF 校验开关 |
| `risk.max_loss_percent` | 单笔最大亏损比例 |
| `risk.max_leverage` | 最大杠杆倍数 |
| `notification.channels` | 通知渠道配置 |

## 异常与错误码

| 错误码 | 级别 | 说明 |
|--------|------|------|
| `F-001` | FATAL | API Key 包含交易权限 |
| `F-002` | FATAL | API Key 包含提现权限 |
| `F-003` | FATAL | 必填配置缺失 |
| `F-004` | FATAL | 交易所初始化失败 |
| `C-001` | CRITICAL | WebSocket 重连超限 |
| `C-002` | CRITICAL | 资产轮询连续失败 |
| `W-001` | WARNING | K 线数据质量异常 |
| `W-002` | WARNING | 数据延迟超限 |

## 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio pytest-cov

# 运行所有单元测试
pytest tests/unit/ -v

# 运行覆盖率报告
pytest tests/unit/ --cov=src --cov-report=html
```

## 安全注意事项

1. **API Key 权限**：必须使用只读权限的 API Key，系统启动时会校验权限
2. **敏感信息脱敏**：所有日志和通知中的 API Key、Secret、Webhook URL 都会自动脱敏
3. **零执行政策**：系统代码中不得出现任何下单、撤单、转账相关的方法调用

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- Pydantic v2
- ccxt (async_support)
- aiohttp
- PyYAML
- pytest

## 开发说明

本项目采用 **Clean Architecture** 分层设计：

- **Domain Layer** (`src/domain/`)：纯业务逻辑，无外部依赖
- **Application Layer** (`src/application/`)：应用编排
- **Infrastructure Layer** (`src/infrastructure/`)：所有 I/O 操作
- **Interfaces Layer** (`src/interfaces/`)：对外 API（预留）

**红线规则**：
- `domain/` 目录下严禁出现 `ccxt`、`aiohttp`、`requests` 等 I/O 库
- 所有金融计算必须使用 `Decimal`，禁止使用 `float`
- 严禁裸 `print()`，必须使用 `logging`

---

*本系统仅为行情观测与通知工具，不构成任何投资建议。*
