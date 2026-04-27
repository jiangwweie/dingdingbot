# 盯盘狗 🐶

**加密货币量化交易自动化系统** - 完全动态化、高并发、强状态一致性的交易信号监控、执行与回测平台。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-red.svg)](https://docs.pydantic.dev/)

---

## 🎯 核心原则

**Automated Execution（自动执行）** - 量化交易自动化平台，支持信号监控、订单执行、仓位管理全流程。安全边界：API 密钥仅开交易权限，严禁提现权限。

---

## 🚀 快速开始

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

系统配置存储在 SQLite 数据库中（`data/v3_dev.db`），通过 REST API 或管理脚本管理。

**首次初始化**：

```bash
python scripts/init_config_db.py
```

**环境变量**（本地开发必需）：

```bash
# 复制示例文件
cp .env.local.example .env.local

# 或手动设置
export PG_DATABASE_URL="postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot"
export RUNTIME_PROFILE=sim1_eth_runtime
```

> ⚠️ YAML 不再作为运行时配置真源。系统启动与 Sim-1 运行都以 runtime profile（`runtime_profiles` 表）为准，通过 `RuntimeConfigResolver` 解析并冻结为 `ResolvedRuntimeConfig`；YAML 仅保留为导入导出/备份格式。旧配置域（`config_profiles` / `config_entries`）仅管理非 runtime 的配置 KV 条目，不是执行真源，变更仅在下一次启动或显式 reload 后生效。

### 3. 运行系统

**本地开发**：

```bash
# 1. 启动 PostgreSQL（首次或 PG 未运行时）
docker compose -f docker-compose.pg.yml up -d

# 2. 启动后端
python src/main.py

# 3. 前端（另一个终端）
cd gemimi-web-front && npm run dev
```

**Sim-1 观察（Docker 全栈）**：

```bash
cd docker && docker compose up -d
```

访问 REST API: http://localhost:8000
- `GET /api/runtime/health` - 健康检查
- `GET /api/signals` - 查询信号
- `POST /api/backtest` - 运行回测
- `GET /api/strategies` - 策略管理

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
│   │   ├── runtime_config.py   # RuntimeConfigResolver → ResolvedRuntimeConfig
│   │   ├── config_manager.py   # 旧配置域（非 runtime 真源）
│   │   ├── execution_orchestrator.py # 信号→意图→订单编排
│   │   ├── order_lifecycle_service.py
│   │   ├── position_projection_service.py
│   │   ├── capital_protection.py
│   │   ├── signal_pipeline.py  # 信号处理管道
│   │   ├── backtester.py       # 回测沙箱
│   │   └── performance_tracker.py
│   │
│   ├── infrastructure/         # 基础设施层（I/O）
│   │   ├── pg_models.py        # PG ORM（执行主线全量）
│   │   ├── pg_order_repository.py
│   │   ├── pg_execution_intent_repository.py
│   │   ├── pg_position_repository.py
│   │   ├── pg_signal_repository.py  # PG 实时信号
│   │   ├── hybrid_signal_repository.py # live→PG, backtest→SQLite
│   │   ├── runtime_profile_repository.py
│   │   ├── core_repository_factory.py
│   │   ├── exchange_gateway.py # 交易所网关
│   │   ├── notifier.py         # 通知推送
│   │   ├── logger.py           # 日志与脱敏
│   │   └── signal_repository.py # SQLite（signal_attempts + 回测）
│   │
│   ├── interfaces/             # REST API
│   │   ├── api.py
│   │   ├── api_console_runtime.py
│   │   └── api_profile_endpoints.py
│   │
│   └── main.py                 # 启动入口
│
├── gemimi-web-front/              # 前端控制台
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

### 运行时配置真源

系统当前的运行时配置真源是：

1. `runtime_profiles` 表（SQLite，启动期读取）→ `RuntimeConfigResolver` → 冻结为 `ResolvedRuntimeConfig`
2. 环境变量（仅用于 secrets / 基础设施连接，如 `PG_DATABASE_URL`、交易所密钥、Webhook）

**旧配置域**（`config_profiles` / `config_entries` / `ConfigManager`）：
- 仅管理非 runtime 的配置 KV 条目
- 变更仅在下一次启动或显式 reload 后生效，不热切当前 runtime
- 不是执行真源

YAML 仍然保留用于：

- 配置导出备份
- 配置导入恢复
- 测试中的临时 fixture

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

1. **API Key 权限**：仅开启交易权限，**严禁提现权限**，系统启动时自动校验
2. **敏感信息脱敏**：所有日志中的 API Key、Secret、Webhook URL 自动脱敏
3. **仓位限额控制**：单笔最大损失、每日最大回撤限制
4. **紧急停止开关**：异常情况自动平仓退出

---

## 🛠️ 技术栈

| 领域 | 技术 |
|------|------|
| 后端 | Python 3.11+、FastAPI、asyncio |
| 数据验证 | Pydantic v2 |
| 交易所 | CCXT (async_support + WebSocket) |
| 数据库 | PostgreSQL（runtime 执行主线 + 实时信号）+ SQLite（配置旧域/回测/signal_attempts） |
| 前端 | React、TypeScript、TailwindCSS |
| 测试 | pytest、pytest-asyncio |

---

## 📚 开发文档

- `CLAUDE.md` - 开发者快速指南
- `docs/arch/` - 架构规范与设计文档
- `docs/tasks/` - 子任务说明与演进路线

---

## 📈 演进路线

### ✅ 第一阶段：架构筑基（已完成）
- 强类型递归逻辑树
- 前端 Schema 驱动
- 动态标签系统

### ✅ 第二阶段：交互升维（已完成）
- 热预览接口（Dry Run）
- 逻辑路径可视化
- 策略模板 CRUD

### ✅ 第三阶段：风控执行（已完成）
- 多周期数据对齐
- 动态风险头寸
- 交易所挂单集成

### ✅ 第四阶段：工业化（已完成）
- 配置快照版本化
- 异步 I/O 队列
- 指标计算缓存

### ✅ v3.0 迁移（已完成）
- 执行主线 PG 闭环（orders / intents / positions / signals / recovery）
- RuntimeConfigResolver + runtime_profiles 配置真源
- Sim-1 模拟盘观察部署

### 🎯 当前阶段：Sim-1 观察期
- 策略研究与运行治理
- 前端 runtime / research 观察面完善
- PG / 边界治理后续减熵

---

## 📄 许可证

本项目仅供学习交流使用，不构成任何投资建议。

---

*本系统为量化交易自动化平台，具备自动执行能力，不构成任何投资建议。*
