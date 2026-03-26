# 盯盘狗 🐶

**加密货币量化交易信号监控系统** - 完全动态化、高并发、强状态一致性的交易信号监控与回测沙箱系统。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-red.svg)](https://docs.pydantic.dev/)

---

## 🎯 核心原则

**Zero Execution Policy（零执行政策）** - 系统仅为观测与通知工具，严禁集成任何交易下单接口。

---

## 🚀 快速开始

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置文件

编辑 `config/user.yaml` 设置交易所凭证：

```yaml
exchange:
  name: "binance"
  api_key: "your-read-only-api-key"  # ⚠️ 必须只读权限
  api_secret: "your-secret"
  testnet: false  # 使用测试网

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
# 运行主程序（实时监控 + REST API）
python src/main.py

# 访问 REST API: http://localhost:8000
# - GET /api/signals     - 查询历史信号
# - POST /api/backtest   - 运行回测
# - GET /api/strategies  - 获取策略模板
```

### 4. 运行回测

```bash
python tests/backtest.py
```

---

## 📦 项目结构

```
dingdingbot/
├── src/
│   ├── domain/                 # 领域核心层（纯业务逻辑）
│   │   ├── models.py           # Pydantic 数据模型
│   │   ├── exceptions.py       # 统一异常体系
│   │   ├── indicators.py       # EMA 等指标计算
│   │   ├── filter_factory.py   # 动态过滤器工厂
│   │   ├── strategy_engine.py  # 动态策略引擎
│   │   ├── strategies/         # 具体策略实现
│   │   └── risk_calculator.py  # 风控试算
│   │
│   ├── application/            # 应用服务层
│   │   ├── config_manager.py   # 配置加载/合并/热重载
│   │   ├── signal_pipeline.py  # 信号处理管道
│   │   ├── backtester.py       # 回测沙箱
│   │   └── performance_tracker.py
│   │
│   ├── infrastructure/         # 基础设施层（I/O）
│   │   ├── exchange_gateway.py # 交易所网关
│   │   ├── notifier.py         # 通知推送
│   │   ├── logger.py           # 日志与脱敏
│   │   └── signal_repository.py # SQLite 持久化
│   │
│   ├── interfaces/             # REST API
│   │   └── api.py
│   │
│   └── main.py                 # 启动入口
│
├── config/
│   ├── core.yaml               # 系统核心配置
│   └── user.yaml               # 用户配置
│
├── web-front/                  # 前端策略工作台
├── docs/                       # 架构文档
└── tests/
    ├── unit/                   # 单元测试
    ├── e2e/                    # 端到端测试
    └── integration/            # 集成测试
```

---

## 🔧 核心功能

### 信号识别策略

支持**多 Trigger + 多 Filter**组合策略：

| 类型 | 支持的模式 |
|------|-----------|
| **Trigger** | Pinbar（锤子线）、Engulfing（吞没）、Doji（十字星） |
| **Filter** | EMA 趋势、MTF 多周期、ATR 波动率、成交量突增、时间过滤 |

#### Pinbar 形态检测
- 颜色不敏感（阴阳线均可）
- 可配置参数：`min_wick_ratio`、`max_body_ratio`、`body_position_tolerance`

#### MTF 多周期共振
- 自动映射：15m→1h、1h→4h、4h→1d、1d→1w
- 状态：`CONFIRMED`（确认）、`REJECTED`（拒绝）、`DISABLED`（禁用）

### 风控试算

- 单笔最大损失：基于账户余额百分比（默认 1%）
- 仓位公式：`Position_Size = (Balance × Loss_Percent) / Stop_Loss_Distance`
- 所有计算使用 `Decimal` 类型，零精度丢失

### 通知推送

| 渠道 | 支持 |
|------|------|
| 飞书 Webhook | ✅ |
| 企业微信 | ✅ |
| Telegram | ✅ |

- 纯文本 Markdown 格式
- 核心字段：币种、周期、方向、入场价、止损、仓位、动态标签

### REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/signals` | GET/DELETE | 查询/删除历史信号 |
| `/api/backtest` | POST | 运行策略回测 |
| `/api/strategies` | GET/POST/DELETE | 策略模板管理 |
| `/api/strategies/meta` | GET | 获取动态 Schema |

---

## ⚙️ 配置说明

### 核心配置（`config/core.yaml`）

系统级配置，通常无需修改：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `core_symbols` | 核心监测币种 | BTC, ETH, SOL, BNB |
| `pinbar_defaults.min_wick_ratio` | 影线占比下限 | 0.6 |
| `ema.period` | EMA 周期 | 60 |
| `warmup.history_bars` | REST 预热 K 线数 | 100 |

### 用户配置（`config/user.yaml`）

| 参数 | 说明 |
|------|------|
| `exchange.api_key` | 交易所 API Key（**必须只读权限**） |
| `exchange.testnet` | 是否使用测试网 |
| `user_symbols` | 自定义监测币种 |
| `timeframes` | 监测时间周期 |
| `risk.max_loss_percent` | 单笔最大亏损比例 |
| `risk.max_leverage` | 最大杠杆倍数 |
| `notification.channels` | 通知渠道配置 |

---

## ⚠️ 异常与错误码

| 错误码 | 级别 | 说明 |
|--------|------|------|
| `F-001` | FATAL | API Key 有交易权限 |
| `F-002` | FATAL | API Key 有提现权限 |
| `F-003` | FATAL | 必填配置缺失 |
| `F-004` | FATAL | 交易所初始化失败 |
| `C-001` | CRITICAL | WebSocket 重连超限 |
| `C-002` | CRITICAL | 资产轮询连续失败 |
| `W-001` | WARNING | K 线数据质量异常 |
| `W-002` | WARNING | 数据延迟超限 |

---

## 🧪 测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio pytest-cov

# 运行所有单元测试
pytest tests/unit/ -v

# 运行覆盖率报告
pytest tests/unit/ --cov=src --cov-report=html

# 运行特定测试
pytest tests/unit/test_strategy_engine.py -v
```

---

## 🔒 安全注意事项

1. **API Key 权限**：必须使用只读权限，系统启动时自动校验
2. **敏感信息脱敏**：所有日志中的 API Key、Secret、Webhook URL 自动脱敏
3. **零执行政策**：代码中不得出现任何下单、撤单、转账相关方法

---

## 🛠️ 技术栈

| 领域 | 技术 |
|------|------|
| 后端 | Python 3.11+、FastAPI、asyncio |
| 数据验证 | Pydantic v2 |
| 交易所 | CCXT (async_support + WebSocket) |
| 数据库 | SQLite |
| 前端 | React、TypeScript、TailwindCSS |
| 测试 | pytest、pytest-asyncio |

---

## 📚 开发文档

- `CLAUDE.md` - 开发者快速指南
- `docs/arch/` - 架构规范与设计文档
- `docs/tasks/` - 子任务说明与演进路线

---

## 📈 演进路线

### 🟢 第一阶段：架构筑基（当前）
- 强类型递归逻辑树
- 前端 Schema 驱动
- 动态标签系统

### 🟡 第二阶段：交互升维
- 热预览接口（Dry Run）
- 逻辑路径可视化
- 策略模板 CRUD

### 🟠 第三阶段：风控执行
- 多周期数据对齐
- 动态风险头寸
- 交易所挂单集成

### 🔵 第四阶段：工业化
- 配置快照版本化
- 异步 I/O 队列
- 指标计算缓存

---

## 📄 许可证

本项目仅供学习交流使用，不构成任何投资建议。

---

*本系统仅为行情观测与通知工具。*
