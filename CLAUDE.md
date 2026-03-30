# CLAUDE.md - 盯盘狗 🐶 项目开发指南

> **最后更新**: 2026-03-30
> **项目阶段**: v3.0 Phase 5 准备中 - 实盘集成待启动
> **下一版本**: v3.0 Phase 5 (实盘集成) - 待启动

---

## 项目使命

**盯盘狗** 是一个**完全动态化、高并发、强状态一致性**的加密货币量化交易自动化系统。

**核心原则：Automated Execution（自动执行）** - 系统为完整的量化交易自动化平台，支持信号监控、订单执行、仓位管理全流程。

**安全边界**:
- API 密钥权限：仅开启交易权限，**严禁提现权限**
- 仓位限额控制：单笔最大损失、每日最大回撤限制
- 紧急停止开关：异常情况自动平仓退出
- 交易模式：U 本位合约 (USDT-Margined Futures)，暂不支持现货/币本位

**核心目标**: 允许高级交易员通过"积木化"的零代码前端工作台，自由拼装多态的触发器（Triggers）与拦截滤网（Filters），形成环境隔离的组合策略，并自动执行交易。

---

## 快速开始

```bash
# 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 运行测试
pytest tests/unit/ -v

# 运行应用
python src/main.py

# 运行回测
python tests/backtest.py
```

---

## 技术栈

| 领域 | 技术 |
|------|------|
| **语言** | Python 3.11+ |
| **框架** | FastAPI + asyncio + Uvicorn |
| **交易所** | CCXT (async_support) + CCXT.Pro (WebSocket) |
| **数据验证** | Pydantic v2 |
| **金融精度** | `decimal.Decimal`（严禁 `float`） |
| **测试** | pytest + pytest-asyncio + pytest-cov |
| **前端** | React + TypeScript + TailwindCSS（重构中） |

---

## 系统架构 (Clean Architecture)

```
dingdingbot/
├── src/
│   ├── domain/                     # 领域核心层（纯业务逻辑，无 I/O）
│   │   ├── models.py               # Pydantic 数据模型（SSOT）
│   │   ├── exceptions.py           # 统一异常体系（F/C/W 错误码）
│   │   ├── indicators.py           # EMA 等指标流式计算
│   │   ├── filter_factory.py       # 动态过滤器工厂
│   │   ├── strategy_engine.py      # 动态策略引擎（支持多策略）
│   │   ├── strategies/             # 具体策略实现
│   │   │   ├── pinbar.py           # Pinbar 形态策略
│   │   │   └── engulfing.py        # 吞没形态策略
│   │   └── risk_calculator.py      # 风控试算（Decimal 精度）
│   │
│   ├── application/                # 应用服务层
│   │   ├── config_manager.py       # 配置加载/合并/热重载
│   │   ├── signal_pipeline.py      # 信号处理管道（K 线→策略→风控→通知）
│   │   ├── backtester.py           # 回测沙箱引擎
│   │   └── performance_tracker.py  # 性能追踪器
│   │
│   ├── infrastructure/             # 基础设施层（所有 I/O）
│   │   ├── exchange_gateway.py     # 交易所网关（REST+WS）
│   │   ├── notifier.py             # 通知推送（飞书/微信/Telegram）
│   │   ├── logger.py               # 统一日志（敏感信息脱敏）
│   │   └── signal_repository.py    # SQLite 信号持久化
│   │
│   ├── interfaces/                 # REST API 端点
│   │   └── api.py                  # FastAPI 路由（回测/配置/信号查询）
│   │
│   └── main.py                     # 启动入口
│
├── config/
│   ├── core.yaml                   # 系统核心配置（只读）
│   └── user.yaml                   # 用户配置（API 密钥/策略开关）
│
├── web-front/                      # 前端策略工作台（重构中）
├── docs/                           # 架构文档
│   ├── arch/                       # 架构规范
│   └── tasks/                      # 子任务说明
└── tests/
    ├── unit/                       # 单元测试
    ├── e2e/                        # 端到端测试
    └── integration/                # 集成测试
```

---

## 核心约束 (Code Review Red Lines)

### 领域层纯净性
`domain/` 目录**严禁**导入：`ccxt`、`aiohttp`、`requests`、`fastapi`、`yaml` 或任何 I/O 框架。

### Decimal  everywhere
所有金额、比率、计算必须使用 `decimal.Decimal`。使用 `float` 进行金融计算将被拒绝。

### API 密钥安全
- API 密钥权限：**交易权限 ✅ / 提现权限 ❌**
- 系统启动时校验权限，发现 `withdraw` 权限立即退出 (`F-002`)
- Phase 5 实盘模式：需配置交易权限
- 所有敏感信息必须通过 `mask_secret()` 脱敏后记录日志

### 类型安全
- **禁用 `Dict[str, Any]`** - 核心参数必须定义具名 Pydantic 类
- **辨识联合** - 多态对象必须使用 `discriminator='type'`
- **自动 Schema** - 接口文档通过模型反射生成

---

## 错误码系统

| 错误码 | 级别 | 说明 |
|--------|------|------|
| `F-001` | FATAL | API Key 有交易权限（Phase 5 起允许） |
| `F-002` | FATAL | API Key 有提现权限（严禁） |
| `F-003` | FATAL | 必填配置缺失 |
| `F-004` | FATAL | 交易所初始化失败 |
| `F-010` | FATAL | 保证金不足 |
| `F-011` | FATAL | 订单参数错误 |
| `F-012` | FATAL | 订单不存在 |
| `F-013` | FATAL | 订单已成交 |
| `C-001` | CRITICAL | WebSocket 重连超限 |
| `C-002` | CRITICAL | 资产轮询连续失败 |
| `C-010` | CRITICAL | API 频率限制 |
| `W-001` | WARNING | K 线数据质量异常（high < low 等） |
| `W-002` | WARNING | 数据延迟超限 |

---

## 核心模型契约

### 输入数据（基础设施层 → 领域层）

```python
KlineData:      # K 线数据
  - symbol: str          # "BTC/USDT:USDT"
  - timeframe: str       # "15m", "1h", "4h", "1d", "1w"
  - timestamp: int       # 毫秒时间戳
  - open/high/low/close/volume: Decimal
  - is_closed: bool

AccountSnapshot:  # 账户快照
  - total_balance: Decimal
  - available_balance: Decimal
  - unrealized_pnl: Decimal
  - positions: List[PositionInfo]
  - timestamp: int
```

### 输出数据（领域层 → 基础设施层）

```python
SignalResult:     # 信号结果
  - symbol: str
  - timeframe: str
  - direction: Direction (LONG/SHORT)
  - entry_price: Decimal
  - suggested_stop_loss: Decimal
  - suggested_position_size: Decimal
  - current_leverage: int
  - tags: List[Dict[str, str]]  # 动态标签，如 [{"name": "EMA", "value": "Bullish"}]
  - risk_reward_info: str
  - strategy_name: str          # 策略名称
  - score: float                # 形态质量评分 (0~1)
  # 遗留字段（已废弃）: ema_trend, mtf_status
```

### 动态策略模型（Phase K）

```python
StrategyDefinition:
  - id: str
  - name: str
  - triggers: List[TriggerConfig]    # 触发器列表
  - trigger_logic: "AND" | "OR"      # 触发器组合逻辑
  - filters: List[FilterConfig]      # 过滤器链
  - filter_logic: "AND" | "OR"       # 过滤器组合逻辑
  - apply_to: List[str]              # 作用域，如 ["BTC/USDT:USDT:15m"]

TriggerConfig:
  - type: "pinbar" | "engulfing" | "doji" | "hammer"
  - params: Dict[str, Any]

FilterConfig:
  - type: "ema" | "ema_trend" | "mtf" | "atr" | "volume_surge" | ...
  - params: Dict[str, Any]
```

---

## 策略逻辑

### Pinbar 形态检测（颜色不敏感）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `min_wick_ratio` | 0.6 | 影线占比下限 |
| `max_body_ratio` | 0.3 | 实体占比上限 |
| `body_position_tolerance` | 0.1 | 实体位置容差 |

- **看涨 Pinbar**: 长下影线，实体在顶部
- **看跌 Pinbar**: 长上影线，实体在底部

### 过滤器组合

```python
signal_valid = (
    pattern_detected
    and all(filters_passed)  # 所有过滤器通过
)
```

### 仓位计算公式

```
Position_Size = (Balance × Loss_Percent) / Stop_Loss_Distance
```

其中：
- `Loss_Percent` = `max_loss_percent`（默认 1%）
- `Stop_Loss_Distance` = `|Entry_Price - Stop_Loss| / Entry_Price`

---

## 模块接口

### ConfigManager

```python
from src.application.config_manager import ConfigManager, load_all_configs

config_manager = load_all_configs()
config_manager.load_core_config()      # → CoreConfig
config_manager.load_user_config()      # → UserConfig
config_manager.merge_symbols()         # → List[str]
await config_manager.check_api_key_permissions(exchange)
config_manager.print_startup_info()    # 打印所有生效参数（脱敏）
```

### ExchangeGateway

```python
from src.infrastructure.exchange_gateway import ExchangeGateway

gateway = ExchangeGateway(
    exchange_name="binance",
    api_key="...",
    api_secret="...",
    testnet=True
)

await gateway.initialize()
await gateway.fetch_historical_ohlcv("BTC/USDT:USDT", "15m", 100)
await gateway.subscribe_ohlcv(symbols, timeframes, callback)
await gateway.start_asset_polling(interval_seconds=60)
gateway.get_account_snapshot()  # → AccountSnapshot | None
await gateway.close()
```

### SignalPipeline

```python
from src.application.signal_pipeline import SignalPipeline

pipeline = SignalPipeline(
    config_manager=config_manager,
    risk_config=risk_config,
    notification_service=notifier,
    signal_repository=repository,
    cooldown_seconds=300
)

await pipeline.process_kline(kline)  # 处理单根 K 线
pipeline.update_account_snapshot(snapshot)  # 更新账户快照
```

### RiskCalculator

```python
from src.domain.risk_calculator import RiskCalculator, RiskConfig

calculator = RiskCalculator(risk_config)
stop_loss = calculator.calculate_stop_loss(kline, direction)  # → Decimal
position_size, leverage = calculator.calculate_position_size(
    account, entry, stop, direction
)
```

---

## 测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio pytest-cov

# 运行所有单元测试
pytest tests/unit/ -v

# 运行覆盖率
pytest tests/unit/ --cov=src --cov-report=html

# 运行特定测试
pytest tests/unit/test_strategy_engine.py -v
```

### 测试文件

| 文件 | 测试内容 |
|------|----------|
| `test_config_manager.py` | 配置加载、合并、权限校验、脱敏 |
| `test_exchange_gateway.py` | OHLCV 解析、历史获取、轮询逻辑 |
| `test_notifier.py` | 消息格式化、Webhook 推送 |
| `test_indicators.py` | EMA 计算、预热、重置 |
| `test_strategy_engine.py` | Pinbar 检测、趋势过滤、MTF 校验 |
| `test_risk_calculator.py` | 仓位计算、止损、Decimal 精度 |
| `test_signal_pipeline.py` | 管道处理流程、冷却去重 |

---

## 项目演进路线图

### ✅ 已完成阶段

**第一阶段：架构筑基 (v0.1.0)** - ✅ 已完成
- [x] 强类型递归逻辑树 (Pydantic + Discriminator)
- [x] 前端 100% Schema 驱动（移除硬编码）
- [x] 信号标签动态化（移除 `ema_trend`/`mtf_status`）

**第二阶段：交互升维 (v0.2.0)** - ✅ 已完成
- [x] 热预览接口（Dry Run，单笔即时验证）
- [x] 逻辑路径可视化（Trace Tree）
- [x] 策略模板库 CRUD + 一键下发实盘
- [x] 实盘热重载功能

**第三阶段：风控执行 (v0.3.0)** - ✅ 已完成
- [x] 多周期数据对齐优化
- [x] 动态风险头寸计算

**第四 + 五阶段：工业化调优 + 状态增强 (v0.6.0)** - ✅ 已完成
- [x] 配置快照版本化（Rollback）
- [x] 异步 I/O 队列（`asyncio.Queue` 批处理）
- [x] 指标计算缓存（多策略共用）
- [x] WebSocket 资产推送
- [x] 信号状态跟踪系统

**多交易所适配** - ✅ 已完成
- [x] Binance/Bybit/OKX 配置驱动切换
- [x] 完整的单元测试和集成测试覆盖

---

### 🎯 当前首要目标：v3.0 迁移（2026-05-06 ~ 2026-08-24）

**Phase 0**: v3 准备 (1 周) - ✅ 已完成
**Phase 1**: 模型筑基 (2 周) - ✅ 已完成 (2026-03-30)
**Phase 2**: 撮合引擎 (3 周) - ✅ 已完成
**Phase 3**: 风控状态机 (2 周) - ✅ 已完成
**Phase 4**: 订单编排 (2 周) - ✅ 已完成
**Phase 5**: 实盘集成 (3 周) - ⏳ 准备启动
**Phase 6**: 前端适配 (2 周) - ⏳ pending

**Phase 5 交付成果** (预计):
- ✅ ExchangeGateway 订单接口扩展
- ✅ WebSocket 订单推送监听
- ✅ 并发保护机制（Asyncio Lock + DB 行锁）
- ✅ 启动对账服务
- ✅ DCA 分批建仓
- ✅ 资金安全限制（单笔/每日/仓位）
- ✅ 飞书告警集成

**详细文档**: `docs/v3/v3-evolution-roadmap.md`

---

## 开发规范

### 🎭 角色分工（Project Skills）

#### Agent Team（5 人_full stack 团队）
| 角色 | 命令 | 职责 | 技术栈 |
|------|------|------|------|
| 团队协调器 | `/coordinator` | 任务分解、角色调度、结果整合 | - |
| 后端开发 | `/backend` | Python + FastAPI + asyncio | Python 3.11, FastAPI, Pydantic v2 |
| 前端开发 | `/frontend` | React + TypeScript + TailwindCSS | React 18, TS 5, TailwindCSS 3 |
| 测试专家 | `/qa` | 单元测试、集成测试、E2E 测试 | pytest, vitest |
| 代码审查员 | `/reviewer` | 独立代码审查、架构一致性检查 | Clean Architecture, OWASP |

### 使用 Agent Team

### 使用 Agent Team

**方式 1: 使用 Slash Commands（推荐）**
在项目目录下运行：
```bash
/coordinator   # 团队协调器（完整功能开发）
/frontend      # 前端开发专家
/backend       # 后端开发专家
/qa            # 质量保障专家
```

**方式 2: 直接描述需求（自动分解）**
```
用户：添加策略预览功能
→ Coordinator 自动分解为前端/后端/测试任务并并行执行
```

**方式 3: 并行调度（使用 Agent 工具）**
```python
Agent(subagent_type="frontend-dev", prompt="...")
Agent(subagent_type="backend-dev", prompt="...")
Agent(subagent_type="qa-tester", prompt="...")
```

> 📚 详细文档：`.claude/team/README.md`
> 🚀 快速开始：`.claude/team/QUICKSTART.md`

---

## 🚀 全自动复杂任务交付流水线

**复杂任务（涉及前端 + 后端 + 测试）必须走全自动工作流**:

```
【阶段 0】需求接收 → 【阶段 1】契约设计 → 【阶段 2】任务分解 → 【阶段 3】并行开发 → 【阶段 4】审查验证 → 【阶段 5】测试执行 → 【阶段 6】提交汇报
```

**核心原则**:
- **契约先行**: 先写接口契约表，作为 SSOT
- **并行执行**: 前后端独立任务并行开发
- **自动审查**: Reviewer 对照契约表检查
- **无人值守**: 简单问题自解，严重问题标记 blocked 最后汇报

**详细文档**: `docs/workflows/auto-pipeline.md`
**契约模板**: `docs/templates/contract-template.md`

### 任务文档

开发前请阅读对应子任务文档：
- `docs/tasks/2026-03-25-子任务 A-实盘引擎热重载与稳定性重构.md`
- `docs/tasks/2026-03-25-子任务 B-策略工作台与 CRUD 接口开发.md`
- `docs/tasks/2026-03-25-子任务 C-信号结果动态标签系统重构.md`
- `docs/tasks/2026-03-25-子任务 E-递归表单驱动与动态预览重构.md`
- `docs/tasks/2026-03-25-子任务 F-强类型递归引擎与 Schema 自动化开发.md`

### 架构规范

- `docs/arch/系统开发规范与红线.md` - **必须首先阅读**
- `docs/arch/系统重构与架构演进梳理报告.md` - 系统使命与技术债

### 规划文件

- `docs/planning/task_plan.md` - 任务阶段与进度追踪
- `docs/planning/findings.md` - 研究发现与技术笔记
- `docs/planning/progress.md` - 会话日志与错误记录

---

## 开发注意事项

### 文件命名规范 ⚠️

**重要**：为避免读取失败，所有文件名必须遵循以下规范：

| 规则 | 示例 ✅ | 示例 ❌ |
|------|---------|---------|
| 禁止使用空格 | `子任务 F-强类型递归引擎.md` | `子任务 F - 强类型递归引擎.md` |
| 使用连字符替代空格 | `2026-03-25-子任务 A-重构.md` | `2026-03-25-子任务 A - 重构.md` |
| 使用 UTF-8 无 BOM 编码 | 所有 `.md` 文件 | - |
| 中文文件名使用 NFC 格式 | `叮盘狗 - 系统演进.md` | `叮盘狗 - 系统演进.md` (NFD) |

**修复工具**：
```bash
# 自动修复文件名中的 Unicode 和空格问题
python3 scripts/fix_filenames.py
```

**读取中文文件**：
```bash
# 使用引号包裹路径
cat "docs/tasks/叮盘狗 - 系统演进全景路线图.md"

# 或使用 Python 脚本
python3 scripts/read_markdown.py "docs/tasks/文件名.md"
```

### WebSocket
- 自动重连（指数退避：1s 初始，60s 最大）
- 仅在 `is_closed=True` 时触发策略计算

### MTF 映射
- 15m → 1h, 1h → 4h, 4h → 1d, 1d → 1w

### 通知格式
- 纯文本 Markdown，禁止截图
- 核心字段：币种、周期、方向、入场价、止损、仓位、动态标签

### 脱敏
- `mask_secret(value, visible_chars=4)` 保留首尾各 4 字符

### 配置
- 启动时静态加载（不支持逻辑热重载）
- `core_symbols`（BTC、ETH、SOL、BNB）不可被用户配置移除
- 所有生效参数必须在启动时打印到控制台（脱敏后）

---

## 文件引用

- `README.md` - 用户文档
- `docs/` - 架构与任务文档
- `.claude/skills/` - 项目角色技能定义

---

## 📝 读取中文 MD 文档

如遇中文文件名的 MD 文档读取失败，使用以下脚本：

```bash
# 自动处理 Unicode 和空格问题
python3 scripts/read_markdown.py "docs/tasks/叮盘狗 - 系统演进全景路线图.md"
```

**问题原因**：macOS 文件系统使用 NFD 格式存储 Unicode 文件名，且文件名中的空格可能导致匹配失败。

---

*本系统仅为行情观测与通知工具，不构成任何投资建议。*
