# 盯盘狗 🐶 系统完整技术文档

**文档版本**: v2.0
**最后更新**: 2026-03-30
**文档用途**: 系统架构与技术决策讨论

---

## 一、系统概述

### 1.1 系统定位

**盯盘狗** 是一个**完全动态化、高并发、强状态一致性**的加密货币量化交易信号监控与回测沙箱系统。

**核心原则**: **Zero Execution Policy（零执行政策）** — 系统仅为观测与通知工具，严禁集成任何交易下单接口。

**核心目标**: 允许高级交易员通过"积木化"的零代码前端工作台，自由拼装多态的触发器（Triggers）与拦截滤网（Filters），形成环境隔离的组合策略。

### 1.2 目标用户

| 用户类型 | 需求 | 系统价值 |
|---------|------|---------|
| 个人交易者 | 实时监控多个币种，不错过交易机会 | 24/7 自动监控，多渠道通知 |
| 策略开发者 | 快速验证策略想法，回测历史表现 | 零代码策略拼装，即时回测 |
| 量化团队 | 策略模板管理，团队协作 | 策略模板库，配置版本化 |

### 1.3 核心价值主张

```
┌─────────────────────────────────────────────────────────┐
│                   盯盘狗价值金字塔                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│                         ▲                                │
│                        /│\                               │
│                       / │ \   财务自由工具               │
│                      /  │  \  (帮助用户验证并执行        │
│                     /   │   \   可盈利的策略)            │
│                    /────┼────\                          │
│                   /     │     \                         │
│                  /      │      \  策略工厂               │
│                 /       │       \ (分钟级从灵感到实盘)    │
│                /────────┼────────\                       │
│               /         │         \                      │
│              /          │          \ 零代码平台          │
│             /───────────┼───────────\ (积木化拼装)       │
│            /            │            \                   │
│           /             │             \                  │
│          ───────────────┴───────────────                 │
│        可靠的基础设施 (高并发 + 强状态一致性)              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 二、技术选型

### 2.1 技术栈总览

| 领域 | 技术选型 | 版本 | 选型理由 |
|------|---------|------|---------|
| **后端语言** | Python | 3.11+ | 量化生态丰富，Decimal 精度高 |
| **Web 框架** | FastAPI | 最新 | 异步支持，自动 Schema 生成 |
| **异步运行时** | asyncio + Uvicorn | - | 高并发 I/O 友好 |
| **交易所网关** | CCXT + CCXT.Pro | 4.5.14+ | 统一 API，支持 REST+WebSocket |
| **数据验证** | Pydantic | v2 | 类型安全，自动 Schema |
| **金融精度** | decimal.Decimal | - | 严禁 float，避免精度丢失 |
| **数据库** | SQLite (aiosqlite) | - | 轻量，适合个人部署 |
| **测试框架** | pytest + pytest-asyncio | - | 异步测试支持 |
| **前端框架** | React | 18 | 组件生态成熟 |
| **前端语言** | TypeScript | 5 | 类型安全 |
| **样式框架** | TailwindCSS | 3 | 快速开发 |
| **图表库** | Lightweight Charts | - | TradingView 出品，专业 K 线 |

### 2.2 架构分层 (Clean Architecture)

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
├── web-front/                      # 前端策略工作台
├── docs/                           # 架构文档
└── tests/
    ├── unit/                       # 单元测试
    ├── integration/                # 集成测试
    └── e2e/                        # E2E 测试
```

### 2.3 核心架构决策

| 决策 | 选择 | 理由 | 替代方案 |
|------|------|------|---------|
| **领域层纯净性** | domain/ 严禁 I/O 依赖 | 业务逻辑可测试，易维护 | - |
| **Decimal everywhere** | 所有金额用 Decimal | 金融计算精度保证 | float（被拒绝） |
| **API 密钥只读权限** | 启动时校验权限 | 安全红线，防止误操作 | - |
| **类型安全** | Pydantic v2 + Discriminator | 自动 Schema，类型推导 | Dict[str, Any]（被拒绝） |
| **异步优先** | asyncio 全异步 I/O | 高并发，WebSocket 友好 | 多线程 |
| **信号覆盖机制** | 更高分信号自动替代 | 智能去重，不错过好信号 | 固定冷却缓存（已废弃） |

### 2.4 多交易所支持 (2026-03-30 新增)

| 交易所 | 状态 | 配置模板 |
|--------|------|---------|
| **Binance** | ✅ 已完成 | `config/user.yaml.example` |
| **Bybit** | ✅ 已完成 | `config/user.bybit.yaml.example` |
| **OKX** | ✅ 已完成 | `config/user.okx.yaml.example` |

**快速切换**:
```bash
# 切换到 Bybit
cp config/user.bybit.yaml.example config/user.yaml

# 切换到 OKX
cp config/user.okx.yaml.example config/user.yaml
```

**核心功能**:
- ✅ 配置驱动切换交易所
- ✅ 核心币种池兼容性（BTC/ETH/SOL/BNB）
- ✅ CCXT.Pro WebSocket 支持
- ✅ 完整的单元测试和集成测试覆盖

---

## 三、核心功能模块

### 3.1 动态策略系统

**策略 = 触发器 (Triggers) + 过滤器 (Filters)**

#### 触发器（Triggers）

| 触发器 | 说明 | 参数 |
|--------|------|------|
| Pinbar | 针 bar 形态检测 | min_wick_ratio, max_body_ratio, body_position_tolerance |
| Engulfing | 吞没形态检测 | min_body_ratio, require_full_engulf |
| Doji | 十字星形态 | max_body_ratio, min_total_range |
| Hammer | 锤子线形态 | min_lower_wick_ratio, max_upper_wick_ratio |

#### 过滤器（Filters）

| 过滤器 | 说明 | 参数 |
|--------|------|------|
| EMA | EMA 趋势校验 | period, trend_direction |
| MTF | 多周期趋势验证 | require_confirmation |
| ATR | ATR 波动率过滤 | period, min_atr_ratio |
| Volume Surge | 成交量激增检测 | multiplier, lookback_periods |
| Volatility Filter | 波动率过滤 | min_atr_ratio, max_atr_ratio, atr_period |
| Time Filter | 时间窗口过滤 | session, exclude_weekend |
| Price Action | 价格行为过滤 | min_body_size, max_body_size |

#### 策略配置示例

```yaml
active_strategies:
  - id: strategy-001
    name: 01pinbar-ema60-mtf
    is_global: true
    logic_tree:
      gate: AND
      children:
        - type: trigger
          config:
            type: pinbar
            params:
              min_wick_ratio: 0.5
              max_body_ratio: 0.35
        - type: filter
          config:
            type: ema
            params:
              period: 60
        - type: filter
          config:
            type: mtf
            params:
              require_confirmation: true
```

### 3.2 回测沙箱系统

**功能**:
- 即时回测：支持自定义时间范围
- 策略预览：实盘前 Dry Run 即时验证
- 性能统计：胜率、盈亏比、过滤统计
- 信号持久化：回测信号自动保存到数据库

**回测指标**:
- 总信号数 / 总过滤数
- 各过滤器过滤统计
- 胜率 / 亏损率
- 总盈亏 / 平均盈亏
- 执行时间 / K 线分析数

**API 端点**:
```
POST /api/backtest    - 运行回测
GET  /api/backtest/signals - 查询回测信号
```

### 3.3 信号全生命周期跟踪

**状态机**:
```
GENERATED → PENDING → ACTIVE → FILLED/WON/LOST
```

**止盈级别** (S6-3 多级别止盈):
```yaml
take_profit_levels:
  - tp_id: TP1
    position_ratio: 0.5    # 50% 仓位
    risk_reward: 1.5       # 1:1.5 盈亏比
    status: PENDING        # PENDING/WON/CANCELLED
  - tp_id: TP2
    position_ratio: 0.3    # 30% 仓位
    risk_reward: 3.0       # 1:3 盈亏比
    status: PENDING
```

### 3.4 信号覆盖系统 (S6-2)

**核心逻辑**:
- 新信号分数 > 旧信号分数 → 覆盖旧信号
- 覆盖通知含评分对比
- 反向信号检测含市场分歧提示

**评分公式**:
```
score = pattern_ratio × 0.7 + min(atr_ratio, 2.0) × 0.3
```

**评分标准**:
| 分数范围 | 质量等级 | 说明 |
|----------|----------|------|
| 0.8 - 1.0 | 优秀 | 形态完美，强烈关注 |
| 0.6 - 0.8 | 良好 | 形态标准，可关注 |
| 0.5 - 0.6 | 一般 | 形态勉强，谨慎观察 |
| < 0.5 | 较差 | 形态不合格，建议忽略 |

### 3.5 实时通知系统

**支持渠道**:
- 飞书（Feishu）
- 企业微信（WeChat Work）
- Telegram

**通知格式示例**:
```
【交易信号提醒】

币种：BTC/USDT:USDT
周期：15m
方向：🟢 看多 (LONG)
入场价：68500
止损位：68000
建议仓位：0.52 BTC
当前杠杆：5x

指标标签:
  MTF: Confirmed
  EMA: Bullish
  ATR: Normal

风控信息：Risk 1.00% = 100.00 USDT
形态评分：0.78

---
⚠️ 本系统仅为观测与通知工具，不构成投资建议
```

### 3.6 配置快照版本化 (S4-1)

**功能**:
- 配置版本保存
- 版本对比
- 一键回滚

**API 端点**:
```
GET  /api/config/snapshots      - 获取快照列表
POST /api/config/snapshots      - 创建快照
POST /api/config/snapshots/{id}/activate - 激活快照（回滚）
```

### 3.7 多交易所适配 (S7-1 ✅ 2026-03-30)

**实现方式**:
- CCXT 统一 API 抽象
- 配置驱动切换
- 交易所适配器模式

**测试覆盖**:
```
tests/unit/test_exchange_gateway.py: 66/66 通过
tests/integration/test_multi_exchange_integration.py: 25/25 通过
tests/integration/test_exchange_live_connection.py: 2/2 通过
总计：93 项测试全部通过 (100%)
```

---

## 四、当前阶段完成情况

### 4.1 整体进度

| 阶段 | 名称 | 状态 | 完成日期 | 发布版本 |
|------|------|------|----------|----------|
| Phase 1 | 架构筑基 | ✅ 已完成 | 2026-03-26 | v0.1.0 |
| Phase 2 | 交互升维 | ✅ 已完成 | 2026-03-26 | v0.2.0 |
| Phase 3 | 风控执行 | ✅ 已完成 | 2026-03-27 | v0.3.0 |
| Phase 4 | 工业化调优 | ✅ 已完成 | 2026-03-27 | v0.6.0 |
| Phase 5 | 状态增强 | ✅ 已完成 | 2026-03-27 | v0.6.0 |
| Phase 6 | 优化与改进 | 🔄 进行中 | - | - |
| Phase 7 | 多交易所 | ✅ 已完成 | 2026-03-30 | v0.7.0 |

### 4.2 已完成功能清单

| 功能域 | 已完成功能 | 成熟度 |
|--------|-----------|--------|
| **数据采集** | WebSocket 实时 K 线（Binance/Bybit/OKX） | ✅ 成熟 |
| **策略引擎** | 递归逻辑树 (AST) + 多策略并行 | ✅ 成熟 |
| **触发器** | Pinbar, Engulfing, Doji, Hammer | ✅ 成熟 |
| **过滤器** | EMA, MTF, ATR, Volume Surge, Volatility, Time, Price Action | ✅ 成熟 |
| **风控计算** | 止损计算、多级别止盈、仓位试算 | ✅ 成熟 |
| **信号覆盖** | 更优信号自动替代旧信号 | ✅ 成熟 |
| **回测沙箱** | 历史回测、策略预览、时间范围支持 | ✅ 成熟 |
| **通知推送** | 飞书/企业微信/Telegram 多模板 | ✅ 成熟 |
| **信号持久化** | SQLite 存储、全生命周期跟踪 | ✅ 成熟 |
| **前端工作台** | 递归表单渲染、策略拼装 | ✅ 成熟 |
| **配置管理** | 热重载、快照版本化 | ✅ 成熟 |
| **日志系统** | 文件轮转、脱敏、溯源追踪 | ✅ 成熟 |
| **容器化** | Docker Compose 一键部署 | ✅ 成熟 |
| **多交易所** | Binance/Bybit/OKX 配置切换 | ✅ 新完成 |

### 4.3 测试状态

```
单元测试：400+ passed, 0 failed
集成测试：90+ passed, 0 failed
TypeScript 编译：通过
代码审查：P0/P1 问题已修复
```

---

## 五、待办事项与后续规划

### 5.1 剩余待办事项

| 优先级 | 任务 | 预计工作量 | 状态 | 说明 |
|--------|------|-----------|------|------|
| **P0** | 止盈追踪逻辑 | 6-8h | ⏸️ 待执行 | 实盘核心功能，自动更新 WON/LOST 状态 |
| **P1** | 可视化 - 逻辑路径 | 4-6h | ⏸️ 待执行 | 策略判定 Trace 树展示 |
| **P1** | 可视化 - 资金监控 | 4-6h | ⏸️ 待执行 | 实时资金曲线 |
| **P2** | 性能统计 | 5-8h | ⏸️ 待执行 | 异步导出 + Python 分析 |
| **P2** | 立即测试增强 | 2-3h | ⏸️ 待执行 | 多 K 线测试 + 高周期预热 |

### 5.2 已废弃任务

| 任务 | 废弃日期 | 原因 | 替代方案 |
|------|----------|------|---------|
| S6-1 冷却缓存优化 | 2026-03-30 | 信号覆盖机制已解决 | S6-2 信号覆盖逻辑 |

### 5.3 执行计划

```
第 1 周：止盈追踪逻辑 (6-8h)
         └─ 复用 PerformanceTracker，集成到 K 线处理流程
第 2 周：可视化 - 逻辑路径 (4-6h)
         └─ 树形缩进 MVP，展示策略判定 Trace 树
第 3 周：可视化 - 资金监控 (4-6h)
         └─ Lightweight Charts 绘制资金曲线
第 4 周：性能统计 (5-8h)
         └─ CSV 导出 + Jupyter 分析模板
第 5 周+: 实盘测试与迭代优化
```

---

## 六、系统终极愿景

### 6.1 产品愿景

**成为加密货币交易员的"策略工厂"** — 让每一个有交易想法的人，无需编写一行代码，就能将策略从灵感到回测再到实盘，全流程在分钟级完成。

### 6.2 演进路线

```
Phase 1-2 (已完成)      Phase 3-5 (已完成)      Phase 6-7 (进行中)      Phase 8+ (愿景)
架构筑基 + 交互升维      风控执行 + 工业化        优化改进 + 多交易所      智能化 + 生态

┌─────────────┐         ┌─────────────┐        ┌─────────────┐       ┌─────────────┐
│ ✅ 递归引擎  │    ──►  │ ✅ 止盈追踪  │   ──►  │ 🔄 可视化   │  ──►  │ ⏸️ AI 辅助  │
│ ✅ Schema 驱动│        │ ✅ 信号覆盖  │        │ ⏸️ 性能统计 │       │ ⏸️ 参数优化 │
│ ✅ 动态过滤器│        │ ✅ 配置快照  │        │ ✅ 多交易所 │       │ ⏸️ 异常检测 │
└─────────────┘         └─────────────┘        └─────────────┘       └─────────────┘
                                                                        │
                                                                        ▼
                                                              ┌─────────────┐
                                                              │ ⏸️ 策略市场 │
                                                              │ ⏸️ 团队协作 │
                                                              │ ⏸️ 多语言   │
                                                              └─────────────┘
```

### 6.3 长期功能蓝图

| 领域 | 终极形态 |
|------|---------|
| **策略工厂** | 支持任意复杂策略表达式 `(A AND B) OR (C AND NOT D)`，可视化 DAG 编排 |
| **回测引擎** | 多策略并行回测、参数网格搜索、Walk-Forward 优化 |
| **性能分析** | 策略 leaderboard、Sharpe/Sortino 比率、最大回撤分析 |
| **风控系统** | 跨策略仓位限额、动态风险预算、相关性感控 |
| **通知系统** | 多渠道智能路由、告警分级、静默时段、升级机制 |
| **协作功能** | 策略分享、团队权限、策略市场 |
| **AI 辅助** | 形态自动发现、参数智能推荐、异常检测 |

---

## 七、技术债与风险

### 7.1 已识别技术债

| 编号 | 问题 | 严重性 | 建议修复时间 |
|------|------|--------|-------------|
| #TP-1 | 回测分批止盈模拟未实现 | 低 | 有空时 |
| #2 | 立即测试无高周期数据预热 | 中 | 2 周内 |

### 7.2 架构风险点

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| SQLite 性能瓶颈 | 中 | 高 | 预留 PostgreSQL 接口 |
| WebSocket 稳定性 | 低 | 高 | 指数退避重连 (1s→60s) |
| 单点故障 | 中 | 高 | Docker Compose + 健康检查 |

---

## 八、API 接口概览

### 8.1 信号相关

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/signals` | GET | 查询信号列表 |
| `/api/signals/{id}` | GET | 查询单个信号详情 |
| `/api/signals/{id}/context` | GET | 查询信号上下文 K 线 |
| `/api/signals/{id}/status` | GET | 查询信号状态 |
| `/api/signals` | DELETE | 批量删除信号 |

### 8.2 回测相关

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/backtest` | POST | 运行回测 |
| `/api/backtest/signals` | GET | 查询回测信号 |

### 8.3 策略相关

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/strategies` | GET | 获取策略列表 |
| `/api/strategies/templates` | GET | 获取策略模板 |
| `/api/strategies/{id}/apply` | POST | 应用策略到实盘 |
| `/api/strategies/preview` | POST | 预览策略（Dry Run） |
| `/api/strategies/meta` | GET | 获取策略元数据 |

### 8.4 配置相关

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 获取系统配置 |
| `/api/config` | PUT | 更新系统配置 |
| `/api/config/snapshots` | GET | 获取配置快照列表 |
| `/api/config/snapshots` | POST | 创建配置快照 |
| `/api/config/snapshots/{id}` | DELETE | 删除快照 |
| `/api/config/snapshots/{id}/activate` | POST | 激活快照（回滚） |

---

## 九、确认事项清单

以下是与 Gemini 讨论前**需要确认**的内容：

### 9.1 待确认决策

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D1** | 止盈追踪实时性方案 | A: 复用 K 线流 / B: 独立价格监控 | ✅ 推荐 A（简单够用） |
| **D2** | 多交易所优先级 | Binance 测试 → OKX/Bybit 实盘 | ✅ 推荐 |
| **D3** | 可视化技术方案 | A: 树形缩进 MVP / B: 交互式流程图 | ✅ 推荐 A（先行验证） |
| **D4** | 性能统计方式 | 异步 CSV 导出 + Python 分析 | ✅ 已确认 |
| **D5** | 实盘测试节奏 | 先测试盘再实盘 | ⏸️ 待确认 |

### 9.2 与 Gemini 讨论的核心议题

1. **止盈追踪架构** - 如何设计实时价格监控与状态更新机制
2. **可视化技术选型** - 逻辑路径可视化的最佳实践
3. **性能统计设计** - 异步导出与数据分析的架构
4. **实盘风险控制** - 测试盘到实盘的过渡策略
5. **系统扩展性** - 未来多用户、策略市场的架构预留

---

## 十、快速开始

### 10.1 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 10.2 配置系统

```bash
# Binance 配置
cp config/user.yaml.example config/user.yaml
# 编辑 config/user.yaml 填入 API 密钥（只读权限！）

# Bybit 配置
cp config/user.bybit.yaml.example config/user.yaml

# OKX 配置
cp config/user.okx.yaml.example config/user.yaml
```

### 10.3 运行系统

```bash
# 运行主程序（实时监控 + REST API）
python src/main.py

# 运行回测
python tests/backtest.py

# 访问前端
cd web-front && npm run dev
```

### 10.4 运行测试

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
```

---

## 十一、文档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| 开发指南 | `CLAUDE.md` | 项目开发规范与快速开始 |
| 架构规范 | `docs/arch/` | 系统架构与编码规范 |
| 任务文档 | `docs/tasks/` | 子任务说明 |
| 发布说明 | `docs/releases/` | 各版本发布记录 |
| 进度日志 | `docs/planning/progress.md` | 开发进度追踪 |
| 任务计划 | `docs/planning/task_plan.md` | 任务优先级与规划 |
| 归档文档 | `docs/archive/` | 已完成/已废弃文档 |

---

## 十二、重要声明

**本系统仅为行情观测与通知工具，不构成任何投资建议。**

使用本系统进行交易所产生的任何损失，系统开发者不承担任何责任。

---

*盯盘狗 🐶 项目*
*2026-03-30*
