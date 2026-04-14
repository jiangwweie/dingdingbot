# 系统模块依赖关系图

> **文档目的**: 解决 R7.2 (隐式依赖难以维护) 和 R8.1 (隐式依赖链可能形成循环)
> **最后更新**: 2026-04-05

---

## 启动顺序依赖图

```
┌─────────────────────────────────────────────────────────────────┐
│                        系统启动流程 (main.py)                      │
└─────────────────────────────────────────────────────────────────┘

Phase 1: 基础设施初始化
┌─────────────────┐
│  ConfigManager  │ ◄── 必须先初始化，所有其他模块依赖配置
│   (initialize)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ConfigHistory   │ ◄── 记录配置变更历史
│  Repository     │
└─────────────────┘

Phase 2: 核心服务初始化
         │
         ▼
┌─────────────────┐
│ ExchangeGateway │ ◄── 依赖 ConfigManager.user_config.exchange
│   (initialize)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│SignalRepository │ ◄── 依赖数据库连接
│   (initialize)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Notification   │ ◄── 依赖 ConfigManager.user_config.notification
│    Service      │
└─────────────────┘

Phase 3: 业务逻辑初始化
         │
         ▼
┌─────────────────┐
│ SignalPipeline  │ ◄── 依赖：
│   (initialize)  │   - ConfigManager
└────────┬────────┘   - SignalRepository
         │             - NotificationService
         │             - RiskConfig
         │
         ▼
┌─────────────────┐
│  StrategyEngine │ ◄── 依赖 ConfigManager 获取策略配置
│     (runner)    │
└─────────────────┘
```

---

## 模块依赖矩阵

| 模块 | 被谁依赖 | 依赖谁 | 依赖类型 |
|------|---------|--------|----------|
| **ConfigManager** | SignalPipeline, ExchangeGateway, NotificationService, API层 | None | 基础设施 |
| **ExchangeGateway** | SignalPipeline, API层 | ConfigManager | 运行时配置 |
| **SignalPipeline** | main.py, API层 | ConfigManager, SignalRepository, NotificationService, RiskCalculator | 核心服务 |
| **SignalRepository** | SignalPipeline, API层 | 数据库 | 数据持久化 |
| **RiskCalculator** | SignalPipeline | RiskConfig (纯数据) | 计算服务 |
| **NotificationService** | SignalPipeline, API层 | ConfigManager | 运行时配置 |

---

## 关键依赖约束

### 1. ConfigManager 初始化约束 (R7.1)

```python
# 必须在其他模块使用前完成初始化
config_manager = load_all_configs()
await config_manager.initialize_from_db()  # ✓ 必须 await

# 其他模块可以安全使用
exchange_gateway = ExchangeGateway(config_manager.user_config.exchange)
signal_pipeline = SignalPipeline(config_manager, ...)
```

**违反约束的后果**: 
- `F-003` 错误: ConfigManager 未初始化
- 模块使用空配置导致异常行为

### 2. SignalPipeline 观察者依赖 (R3.2)

```python
# SignalPipeline 注册为 ConfigManager 观察者
config_manager.add_observer(signal_pipeline.on_config_updated)

# 配置热重载时依赖关系：
# ConfigManager.reload_all_configs_from_db()
#   └── 调用所有观察者的 on_config_updated()
#       └── SignalPipeline 重建 _runner
```

**循环依赖风险**: 无（单向依赖 ConfigManager → SignalPipeline）

### 3. RiskCalculator 配置依赖 (R3.3)

```python
# RiskCalculator 依赖 RiskConfig
risk_calculator = RiskCalculator(risk_config)

# 配置更新时：
# 1. ConfigManager 加载新配置
# 2. SignalPipeline.on_config_updated() 被调用
# 3. SignalPipeline 创建新的 RiskCalculator(new_risk_config)
```

**注意**: RiskCalculator 不直接依赖 ConfigManager，通过 SignalPipeline 传递配置

---

## 隐式依赖检查清单

### 启动时检查 (main.py)

```python
# ✓ 检查 ConfigManager 已初始化
config_manager.assert_initialized()

# ✓ 检查关键配置存在
user_config = await config_manager.get_user_config()
assert user_config.exchange.api_key, "交易所 API 密钥未配置"

# ✓ 检查数据库连接
await signal_repository.initialize()
```

### 运行时检查

```python
# SignalPipeline.process_kline()
if self._config_manager is None:
    raise DependencyNotReadyError("ConfigManager not available")

# API 层调用
if _config_manager is None:
    raise HTTPException(status_code=503, detail="Config manager not initialized")
```

---

## 依赖循环风险分析 (R8.1)

### 当前依赖链

```
ConfigManager
    ↓ (被 SignalPipeline 依赖)
SignalPipeline
    ↓ (使用 RiskCalculator)
RiskCalculator
    ↓ (依赖 RiskConfig - 纯数据类)
RiskConfig ◄── 无进一步依赖，链终止 ✓
```

**结论**: 当前无循环依赖风险

### 潜在循环风险点

| 风险点 | 说明 | 预防措施 |
|--------|------|----------|
| ConfigManager ↔ SignalPipeline | 双向依赖 | ConfigManager 使用观察者模式，不直接依赖 SignalPipeline |
| SignalPipeline ↔ ExchangeGateway | 双向依赖 | SignalPipeline 通过 AccountSnapshot 间接使用，无直接引用 |
| API 层循环导入 |  FastAPI 路由导入 | 使用延迟导入 (`TYPE_CHECKING`) |

---

## Clean Architecture 依赖规则

```
┌─────────────────────────────────────┐
│           Interfaces 层              │ ◄── API 路由、HTTP 处理
│  (FastAPI routers, WebSocket handlers)│
└──────────────┬──────────────────────┘
               │ 依赖
┌──────────────▼──────────────────────┐
│         Application 层              │ ◄── 应用服务、配置管理
│  (ConfigManager, SignalPipeline,    │
│   ConfigProfileService, etc.)       │
└──────────────┬──────────────────────┘
               │ 依赖
┌──────────────▼──────────────────────┐
│           Domain 层                 │ ◄── 核心业务逻辑
│  (StrategyEngine, RiskCalculator,   │
│   PatternDetector, etc.)            │
└──────────────┬──────────────────────┘
               │ 依赖 (通过接口)
┌──────────────▼──────────────────────┐
│       Infrastructure 层             │ ◄── 技术实现细节
│  (ExchangeGateway, SignalRepository,│
│   NotificationService, etc.)        │
└─────────────────────────────────────┘
```

**规则**:
- ✅ Domain 层不依赖 Infrastructure 层
- ✅ Application 层协调 Domain 和 Infrastructure
- ✅ Interfaces 层只依赖 Application 层
- ❌ 禁止 Infrastructure 层直接调用 Interfaces 层

---

## 重构建议

### 短期（文档化）

1. 在模块顶部添加依赖声明注释
2. 使用本依赖图进行代码审查
3. 添加启动时依赖检查断言

### 长期（需求驱动时）

1. 引入依赖注入容器（如 `dependency-injector`）
2. 使用接口抽象（`Protocol` 类）
3. 添加架构测试（如 `import-linter`）

---

## 相关风险

- **R7.2**: 隐式依赖难以维护 → 本文档解决
- **R8.1**: 隐式依赖链可能形成循环 → 经分析当前无风险
- **R3.2**: 观察者重建窗口期 → ConfigManager 版本号机制已解决

---

*文档生成时间: 2026-04-05*
