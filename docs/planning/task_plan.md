# Task Plan: 盯盘狗策略优化项目

> **Created**: 2026-04-15
> **Last updated**: 2026-04-23 00:40
> **Status**: ETH 1h LONG-only 主线已冻结；执行链 MVP 持续补稳，PG 双轨迁移已完成主进程执行链接线，并开始把风控配置切到 ConfigManager 真源；`backtest-studio` 作为低优先级并行线进入设计准备

---

## 当前阶段总结（2026-04-22 18:10）

### 核心结论

**ETH 1h LONG-only 是唯一可行路径，最优配置已锁定；当前阶段已完成 2021-2026Q1 环境边界验证，并确认简单不开仓条件暂时不可用。**

### 跨币种/跨周期搜索结果

| 币种/周期 | 可行解 | 结论 |
|-----------|--------|------|
| **ETH 1h** | **有** | ✅ 唯一可行，最优配置已锁定 |
| ETH 4h | 0/48 | ❌ 交易太少 (~17/年)，统计意义不足 |
| ETH 15m | 0/48 | ❌ 交易过多 (~140/年)，信号质量差 |
| BTC 1h | 0/48 | ❌ 2024 全负，策略不适用 |
| SOL 1h | 0/48 | ❌ 两年皆负，策略不适用 |

### 最优参数配置（全局冻结）

#### 策略结构基线（固定）

```python
# ETH/USDT:USDT 1h LONG-only
{
    “ema_period”: 50,
    “min_distance_pct”: 0.005,
    “max_atr_ratio”: 移除,  # 已验证冗余
    “tp_ratios”: [0.5, 0.5],
    “tp_targets”: [1.0, 3.5],
    “breakeven_enabled”: False,
    “allowed_directions”: [“LONG”],
}
```

#### 资金管理参数（分层）

**默认档（推荐）**：
```python
{
    “max_loss_percent”: 0.01,  # 1%
    “max_leverage”: 20,
}
```

**激进档（高波动）**：
```python
{
    “max_loss_percent”: 0.02,  # 2%
    “max_leverage”: 20,
}
```

### 性能表现对比（BNB9 口径）

#### 默认档（max_loss_percent=1.0%）

| 年份 | PnL | 交易数 | Max DD | Sharpe |
|------|-----|--------|--------|--------|
| 2023 | -3583 | 60 | 49.19% | -2.63 |
| 2024 | **+5952** | 80 | 15.75% | 1.91 |
| 2025 | **+4399** | 77 | 11.56% | 2.01 |
| **总计** | **+6768** | 217 | - | 0.71 |

#### 激进档（max_loss_percent=2.0%）

| 年份 | PnL | 交易数 | Max DD | Sharpe |
|------|-----|--------|--------|--------|
| 2023 | -6245 | 60 | 74.45% | -2.72 |
| 2024 | **+11908** | 80 | 22.98% | 1.93 |
| 2025 | **+12299** | 77 | 16.75% | 2.04 |
| **总计** | **+17962** | 217 | - | 0.69 |

### 已验证结论

#### 结构层验证（已完成）

1. **LONG-only 优于双向**：3年总 PnL 改善 +5348 USDT（+175%）
2. **breakeven_enabled=False 更优**：3年总 PnL 改善 +2715 USDT（+47%）
3. **ATR 过滤器冗余**：有无 ATR 结果完全相同，可移除
4. **2023 失败非出场问题**：测试 4 种出场变体全部恶化
5. **2023 归因口径修正完成**：`TP1=0%` 旧结论已撤销；修正后确认 `2023` 并非完全打不到 `TP1`，但失效主因仍是环境不适配，`exit` 不是独立主因

#### 参数层验证（已完成）

1. **参数敏感性**：ema_period 高敏感，ATR 不敏感，distance 中等敏感
2. **币种/周期适用性**：仅 ETH 1h 适用
3. **最优参数组合**：ema=50, min_distance_pct=0.005, tp=[1.0,3.5], tp_ratios=[0.5,0.5]

#### 资金层验证（已完成）

1. **max_loss_percent 分层配置**：
   - 默认档（1.0%）：稳健运营，回撤可控（<50%），适合长期运行
   - 激进档（2.0%）：盈利翻倍（+165%），但回撤风险大（>70%），需严格监控
2. **选择建议**：
   - 推荐默认档用于生产环境
   - 激进档仅用于短期高波动市场或测试环境

#### 环境边界验证（新增完成）

1. **年度环境谱系已明确**：
   - `2021`：严重失效
   - `2022`：轻度失效 / 过渡态
   - `2023`：严重失效
   - `2024`：适配
   - `2025`：适配
   - `2026 Q1`：forward check 优秀
2. **2023 失效主因已钉牢**：
   - `MFE` 显著低于 `2024/2025`
   - `first-touch` 更容易先到 `-0.5R`
   - `+1R / +2R / +3.5R` 可达率显著更低
   - 结论：主因是 **LONG 信号后续延续性不足 / 可达空间不足**
3. **简单不开仓条件候选已证伪**：
   - `ema_distance_1h`：有解释力，但阈值验证会明显伤害 `2024/2025`

---

## 后续规划候选：Signal-Only Advisory 部署形态

### 背景

- 当前主线仍在重构订单链路与对账
- 但系统已具备较完整的：
  - 信号检测
  - 过滤器链
  - 止损/仓位试算
  - 飞书 webhook 通知能力
- 因此存在一个低耦合候选方向：先部署“只检测信号并给出交易建议”的 advisory 形态

### 目标边界

- 只做：
  - 信号检测
  - 止盈/止损/建议仓位计算
  - 飞书 webhook 推送
- 不做：
  - 订单编排
  - 下单执行
  - 订单状态机
  - 对账
  - 前端 / REST 工作台

### 推荐方案

- **优先方案 A**：在现有系统中增加 `signal-only` / `advisory` 运行模式
- 运行时仅初始化：
  - 行情输入
  - 策略检测
  - 风控试算
  - 飞书通知
- 主流程在“生成交易建议并推送”后结束，不进入订单链路

### 预估工作量

- 第一版（能跑、能推送、能给建议）：
  - **1 ~ 3 天**
- 如果顺手做模式边界清理、方便长期维护：
  - **3 ~ 5 天**

### 后续推进建议

1. 新开独立分支与工作区推进，避免干扰执行链主线
2. 先做运行模式裁剪与消息模板
3. 再做最小真实 K 线流验证
4. 稳定后再决定是否长期保留为独立部署形态
   - `4h` 结构连续性：区分度不足，且出现反向效果
   - 结论：暂不将简单 hard filter 纳入主线

### 完整基线结构（已冻结）

```
- 策略结构基线：ETH 1h LONG-only
- 执行结构基线：BE=False, tp=[1.0,3.5], tp_ratios=[0.5,0.5]
- 过滤结构基线：ema=50, min_distance_pct=0.005, ATR 移除
- 资金默认基线：max_loss_percent=1.0%
- 资金激进档：max_loss_percent=2.0%
```

### 下一步

1. 将当前主线定版为“阶段性实盘候选基线”
2. 按最小执行主链设计收口实盘执行层
3. 第一优先级先做：WS 回写契约核对 -> ExecutionOrchestrator -> ENTRY/TP/SL 闭环

### 并行规划（新增，低优先级）

#### `backtest-studio` 独立前端计划

当前已确认：

1. **基准参数已完成**
   - 因此新前端不再承担“探索策略定义”的职责，而是服务已冻结基线下的回测执行、参数微调和结果比较
2. **现有 `web-front` 不再作为主承载**
   - 仓库内已有 PMS 回测页与回测报告页
   - 但其信息架构混有旧策略工作台、旧导航、旧模板导入语义
   - 后续不再把现有模块作为主要演进方向
3. **采用 B 方案**
   - 与订单对账主线并行推进
   - 先做设计与静态壳子
   - 后续再接真实回测 API

后续路径建议：

1. **阶段 S1：设计**
   - 新建独立子项目，建议目录：`apps/backtest-studio`
   - 明确 MVP 页面结构、字段清单、API 边界
   - 设计稿已产出：`docs/planning/architecture/2026-04-22-backtest-studio-prd.md`
2. **阶段 S2：静态壳子**
   - 先用 mock 数据完成界面和交互流
   - 暂不深度绑定真实后端
3. **阶段 S3：API 接线**
   - 接入回测执行、结果总览、基准参数对比
   - 历史报告/高级分析放后续迭代

边界约束：

1. `backtest-studio` **只服务回测**
2. 不承接实盘、订单、仓位、旧策略工作台职责
3. 不抢占订单对账 / 执行链 / PG 迁移主线优先级

### 执行链实现进度（新增，2026-04-22 20:35）

本阶段已从“设计收口”进入“可运行闭环”的实现期，当前落地情况：

1. ✅ WS 回写契约闭环（P0）
   已修复 WS 回写契约错位（参数/类型），并补齐 `exchange_order_id -> local order` 的映射闭环，避免 WS 回写断链。
2. ✅ ExecutionOrchestrator MVP（信号 -> ENTRY 下单）（P0/P1）
   已处理“交易所返回失败但不抛异常”的失败分支，并对齐“市价单直接 FILLED / PARTIALLY_FILLED”的返回状态语义。
3. ✅ WS 业务回调异常保护（P0）
   回调异常不会中断消费循环；失败订单进入 pending recovery，供对账兜底。
4. ✅ 启动对账最小版（P0）
   启动时扫描 `SUBMITTED/OPEN/PARTIALLY_FILLED` + pending recovery；`fetch_order -> 推进本地状态 -> 清除 pending recovery`。
5. ✅ 受保护持仓闭环 Step1（ENTRY FILLED -> 自动挂载 TP/SL）（P0）
6. ✅ 受保护持仓闭环 Step2（ENTRY PARTIALLY_FILLED -> 按已成交数量挂载保护单）（P1）
   重要语义修正：partial-fill 保护单与 full-fill 使用同一份策略快照（`tp_ratios/tp_targets/SL RR`），不再退化为默认单 TP。

当前剩余的高优先级缺口（下一阶段）：

1. P0：ExecutionIntent 持久化（进程重启可恢复）
2. P0：partial fill 多次增量成交的“补挂 / 调整保护单”机制（幂等）
3. P1：unknown_submitted（place_order 超时未知态）+ 对账接管
4. P1：保护单提交集幂等（跳过已成功子单）+ recovery_required + circuit breaker（停开新仓）
5. P1：定期对账 / 订单超时查询

### 数据库迁移方向（新增，2026-04-22 22:25）

已确认数据库迁移采用以下方向：

1. **SQLite 不删除**
   - 保留现有实现，保证旧业务链路可继续运行
2. **PostgreSQL 以新增实现方式接入**
   - 不直接改写旧 SQLite Repository
   - 通过新增 PG 基础设施与仓储实现承接核心链路
3. **核心表先切 PG**
   - 第一批核心表：`orders / execution_intents / positions`
4. **迁移时同步优化表设计，不做 1:1 搬表**
   - PG 端不复制 SQLite 的历史坏设计
   - 纳入迁移的核心表必须同步收口：
     - 数值字段类型
     - 时间字段口径
     - 最小必要约束
     - 真实查询索引
   - 若本轮故意保留某个设计债，必须在实现输出中明确说明原因

### PG 迁移验收约束（新增，2026-04-22 23:58）

后续每一轮核心表迁移都必须同时满足以下验收标准：

1. **不是 1:1 搬表**
   - 不允许把 SQLite 的 `TEXT` 数值字段、混乱时间口径、缺失约束原样复制到 PG
2. **必须回答 4 个问题**
   - 这张表相对 SQLite 修了哪些设计问题
   - 哪些问题这轮故意不修
   - 应用层是否仍可无感接入
   - 是否还存在会阻塞 PG 真源化的缺口
3. **当前优先级**
   - `orders`：强收口，作为核心执行链真源
   - `execution_intents`：一次成型，替代内存态
   - `positions`：先做稳定核心列 + 扩展载荷的过渡版
   - 第一批核心表：`orders / execution_intents / positions`
4. **双轨并行、渐进迁移**
   - 核心执行链逐步切 PG
   - signals/config/backtest 等旧模块暂留 SQLite
5. **开发顺序**
   - 先设计文档
   - 再测试计划
   - 再骨架代码
   - 最后由执行开发补具体实现与测试

### PG 骨架进度（新增，2026-04-22 22:55）

当前已完成：

1. `database.py` 已补 PG 核心链路入口（惰性初始化，不影响旧 SQLite 默认链路）
2. 已新增核心仓储协议：
   - `OrderRepositoryPort`
   - `ExecutionIntentRepositoryPort`
   - `PositionRepositoryPort`
3. 已新增 PG 核心模型：
   - `orders`
   - `execution_intents`
   - `positions`
4. 已新增 PG 仓储骨架：
   - `PgOrderRepository`
   - `PgExecutionIntentRepository`
   - `PgPositionRepository`
5. `OrderLifecycleService` 已改为面向订单仓储协议类型，而不是写死 SQLite 具体类

当前未做：

1. 尚未把 `ExecutionOrchestrator` 正式接到 PG intent repo
2. 尚未把 `StartupReconciliationService` 正式切到 PG order repo
3. 尚未执行测试（仅做了语法级检查）

### PG 目标真源基线（新增，2026-04-23 00:12）

当前已完成：

1. 已在 `db_scripts/` 下落盘核心 PG 基线脚本与设计附录：
   - `2026-04-22-pg-core-baseline.sql`
   - `2026-04-22-pg-core-baseline-appendix.md`
2. 基线已明确三张核心表的目标设计：
   - `orders`：强收口，作为核心执行链真源
   - `execution_intents`：一次成型，替代内存态
   - `positions`：过渡版，稳定核心列 + `JSONB` 扩展载荷
3. `pg_models.py` 已开始按批准基线对齐，不再停留在旧骨架状态
4. 对齐过程中已修正两类初版偏差：
   - `orders` 的状态/类型集合改为当前领域模型真实值
   - `execution_intents` 的状态集合改为当前领域模型真实值（小写）
5. `blocked_message` 已明确保留为当前执行链兼容字段

当前仍未做：

1. PG repository 仍需继续按新 schema 补齐映射和连通性
2. `positions` 尚未进入完整领域模型转换阶段
3. 尚未执行测试（仅完成语法级检查）

### 核心接线进度（更新，2026-04-22 23:45）

当前已完成：

1. `ExecutionOrchestrator` 已支持注入 `ExecutionIntentRepositoryPort`
2. `ExecutionIntent` 新建、状态推进、partial-fill 回调后的状态更新，均可通过统一 helper 落到仓储
3. partial-fill 路径已支持通过 `order_id` 从仓储恢复 `ExecutionIntent`
4. 已新增 `core_repository_factory.py`：
   - `CORE_ORDER_BACKEND` 现在可真正选择 SQLite / PG 订单仓储实现
   - `CORE_EXECUTION_INTENT_BACKEND` 可决定是否初始化 PG 执行意图仓储
5. API `lifespan()` 已开始托管：
   - order repo 工厂装配
   - `ExecutionIntentRepository` 的初始化与关闭
6. PG 严格模式已补上：
   - 仅当核心后端明确配置为 `postgres` 时才触发
   - `PG_DATABASE_URL` 缺失/非法时，启动阶段直接按 `F-003` 失败
   - 默认 SQLite 链路不受影响
7. 主进程 `main.py` 已完成核心执行运行时初始化：
   - `OrderLifecycleService`
   - `CapitalProtectionManager`
   - `ExecutionOrchestrator`
   - `ExecutionIntentRepository`（按配置启用）
8. `SignalPipeline` 已新增执行 hook，fired signal 可直接进入 orchestrator 执行链
9. `CapitalProtectionManager` 已开始使用 `ConfigManager` 派生配置：
   - 不再依赖默认 `CapitalProtectionConfig()`
   - `risk.max_loss_percent / max_leverage / daily_max_trades / daily_max_loss` 已进入风控派生链

当前仍未做：

1. `ExecutionIntent` 已开始切到 PG 主真源：
   - `get_intent()/list_intents()` 已改为 repo-first
   - `_intents` 降级为热缓存/回退
   - intent 与 order 现已复用同一 `signal_id`
2. 独立 uvicorn 模式虽已补齐执行运行时装配，但同进程反复 startup/shutdown 的 PG 生命周期收口仍可继续加强
3. 尚未把 `StartupReconciliationService` / 更多核心服务正式切到 PG
4. 风控派生配置尚未接入热更新后的运行时刷新
5. 尚未执行测试（仅完成语法级检查）

### 执行层设计决策（新增）

1. **自动执行入口**：信号触发，不走 API
2. **主编排层**：新增薄的 `ExecutionOrchestrator`
3. **订单事实层**：继续复用 `OrderLifecycleService`
4. **关键危险状态**：引入 `entry_filled_unprotected`
5. **第一版兜底原则**：先做重试 + 告警 + `recovery_required`，暂不默认自动强平
6. **TP 数据边界**：
   - `signal_take_profits` 继续表示信号层建议目标位
   - 真实执行的 `TP1 / TP2 / SL` 统一进入 `orders` 订单链
   - 不新增执行层 TP 独立事实表
7. **低频个人量化取舍**：
   - 按低频、个人量化、加密货币场景收口
   - 第一版保留关键真源与危险状态识别
   - 但不引入机构级多实例协同与默认自动强平复杂度
8. **新增必须补的边界**：
   - `PARTIALLY_FILLED` 的保护单策略
   - `unknown_submitted` 超时未知态
   - 保护单提交集幂等 / 跳过已成功子单
   - `asyncio.Lock(symbol)` 串行化执行编排
   - `recovery_required` 后停止该币种新开仓
   - `WS` 回写契约错位为 `P0` 前置任务

> 详细设计稿：
> [2026-04-22-minimal-live-execution-chain-design.md](/Users/jiangwei/Documents/final/docs/planning/architecture/2026-04-22-minimal-live-execution-chain-design.md)

---

## 参数系统演进（已确认）

### 搜索前 Gate（新增）

> `2026-04-21` 审计补充：后续不允许直接从”候选假设”跳到”参数搜索”。
> 进入搜索前，必须先通过以下 gate：

- `MTF` 的 `ema_period / mapping / closed-candle rule` 真源统一（✅ 已完成）
- `min_distance_pct` 与 `max_atr_ratio` 的真实语义已经写清
- 回测撮合口径显式标记为 `stress`
- ETH 1h 最小验证完成，且结果不再依赖旧研究链（✅ 已完成：LONG-only 新基线可复现）

### 当前研究基线（条件冻结候选）

> 注：该基线仅适用于 2024-2026Q1 窗口，2023 年失效。

- 模式：`v3_pms`
- 口径：`stress`
- 标的：`ETH/USDT:USDT`，`1h`
- 方向：`LONG-only`
- 过滤器候选：`Pinbar + EMA(trend) + MTF + ATR`
- 条件冻结参数：
  - `ema_period=55~60`（高敏感，需继续探索）
  - `min_distance_pct=0.007`（已收敛）
  - `max_atr_ratio=0.006`（不敏感）
  - `mtf_ema_period=60`（来自 system config / live 同源）
  - `mtf_mapping={“15m”:”1h”,”1h”:”4h”,”4h”:”1d”,”1d”:”1w”}`
  - `breakeven_enabled=False`
  - `tp_ratios=[0.5,0.5]`
  - `tp_targets=[1.0,3.5]`

### 风险口径（新）

- `equity_curve` 已升级为 `true_equity = balance + unrealized_pnl`
- `max_drawdown` 主值正确；peak/trough 调试输出已修复
- 因此后续不得再用 realized-only 回撤作为风控依据

### 演进路线

- **Phase 1（当前）**：条件冻结 + 机制验证
- **Phase 2（后续）**：交易级重叠分析 + 稳健性确认

### 已确认原则

- 参数优先级统一为：`runtime overrides > request > profile KV > model/code default`
- Optuna 后续采用运行时注入，不再依赖写全局 SQLite KV
- 当前协作模式：
  - `Codex / GPT`：架构审查、分析、决策、review
  - `Claude Code / GLM`：实现、测试、执行

### 方案 A 的目标

- 新增统一参数解析层（如 `ResolvedBacktestParams` / `BacktestRuntimeOverrides`）
- 回测主流程只消费解析后的参数对象
- 消除 `backtester.py` 内部散落的业务默认值
- 保留向方案 B 演进的适配层，不做一次性大重构

### 第一批纳入正式参数链

- 锁定默认值（当前优化 preset，不进 Optuna 搜索）
  - `breakeven_enabled = False`
  - `tp_ratios = [0.6, 0.4]`
  - `tp_targets = [1.0, 2.5]`
- 纳入正式参数链 + 可搜索
  - `strategy.atr.max_atr_ratio`
  - `strategy.ema.min_distance_pct`
  - `strategy.ema.period`
- 第二阶段考虑
  - `strategy.pinbar.min_wick_ratio`
  - `strategy.pinbar.max_body_ratio`
  - `strategy.pinbar.body_position_tolerance`

## `2026-04-20` 研究结论状态（已冻结）

> 说明：昨天不仅观察到了 ETH 盈利，还把“ETH 盈利”上升为“策略 alpha 已确认”，并据此推进了参数方向、Optuna 搜索和测试盘优先级。
> 当前已确认这条推理链不可继续作为决策依据。
> 因此本节只保留为历史快照，不再代表当前推荐方向。

| 参数 | 值 | 来源 | 证据 |
|------|------|------|------|
| 触发器 | Pinbar（默认） | 不变 | — |
| 过滤器 | EMA + MTF + **ATR(max=1%)** | 7组×3年扫描 | +52% 改善 ⭐⭐⭐ |
| 订单 | TP1=1.0R×60%, TP2=2.5R×40%, **BE=OFF** | 3年×3币种验证 | +5607 USDT ⭐⭐⭐ |
| 币种 | BTC/ETH/SOL | 不变 | — |
| 周期 | 1h | 不变 | — |

### 各币种表现（Group 2: ATR=1%, BE=OFF）

| 币种 | 2023 | 2024 | 2025 | 3年合计 | 状态 |
|------|------|------|------|---------|------|
| BTC | +1863 | -7026 | -2470 | **-7633** | ❌ 持续亏损 |
| ETH | -3944 | **+2661** | **+143** | **-1140** | ⚠️ 近2年盈利 |
| SOL | -914 | +33 | -759 | **-1640** | ⚠️ 接近平衡 |
| **合计** | **-2995** | **-4331** | **-3086** | **-10412** | — |

### 已否决方向

| 方向 | 否决理由 | 证据 |
|------|---------|------|
| ~~TP2=1.5R~~ | 所有年份更差（恶化41%），大赢单是盈利来源 | ⭐⭐⭐ 3年×3币种 |
| ~~BTC 4h 直接采用~~ | 方向对（改善+7125）但年均仅5.7笔，无统计显著性 | ⭐⭐ 3年 |
| ~~TTP（上调TP订单）~~ | 撮合T+0与TTP T+1矛盾，0次调价 | ⭐⭐ 代码+日志 |
| ~~Trailing Exit 0.3R~~ | 过早截断盈利，胜率从52.5%降到39.2% | ⭐⭐ 3年 |
| ~~EMA 距离单独加严~~ | 反而更差，BTC从正转负 | ⭐⭐ 7组扫描 |

---

## `2026-04-20` 成果分级

### 可保留的工程能力

- 回测参数优先级链：`runtime overrides > request > profile KV > model/code default`
- `BacktestRuntimeOverrides / ResolvedBacktestParams` 参数解析层
- Optuna 通过 runtime overrides 注入回测参数的工程链路
- 时间顺序修正、funding 净值闭环、MTF 数据窗口 / `end_time` 修复

### 暂停引用的研究结论

- “ETH 在真实滑点 / BNB9 下已证明存在稳定 alpha”
- “ETH 是当前最优先上线币种”
- “昨天锁定的参数组合可直接作为 Optuna 搜索基线”
- “BTC / ETH / SOL 的强弱排序已经成立”

### 待重新认证的参数结论

> 下列结论在工程上仍可保留为候选假设，但在研究上不得继续当作正式基线引用，直到新基线验证完成。

| # | 改动 | 原观察 | 当前状态 |
|---|------|------|------|
| 1 | `breakeven_enabled=False` | +5607 (36%) | 候选假设，待新基线复验 |
| 2 | `max_atr_ratio=0.01` | +11420 (52%) | 候选假设，待新基线复验 |
| 3 | `TP2=1.0R/2.5R` | 当前最优 | 候选假设，待新基线复验 |

## 历史候选改动（待复验）

| # | 改动 | 效果 | 证据 |
|---|------|------|------|
| 1 | **BE=OFF**（关闭Breakeven止损） | +5607 (36%)，ETH翻正 | ⭐⭐⭐ 3年×3币种 |
| 2 | **ATR过滤 max_atr_ratio=0.01** | +11420 (52%) | ⭐⭐⭐ 3年×3币种 |

### 回测数据三层校验

| 层 | 内容 | 结果 |
|---|------|------|
| 第一层 | 常识校验（交易数/胜率/跨组逻辑） | **通过** — 0项失败 |
| 第二层 | 抽样验证（5笔交易 Pinbar/EMA/ATR/SL） | **通过** — 全部PASS |
| 第三层 | 反向验证（ATR=0.1% / EMA=10% 荒谬参数） | **通过** — 信号降至0 |

---

## 下一步：Optuna 自动化 + 策略探索

> 2026-04-21 17:35 注：Optuna 只保留“工程能力已就绪”这个结论。
> 不再保留“昨天的先验知识已经足够可靠，可以直接缩窄搜索空间”这一结论。
> 当前 Optuna 搜索冻结，等待研究基线重建后再恢复。

### 为什么保留 Optuna 链路

昨天的问题不在于“是否要做 Optuna”，而在于“把失效的研究结论当成了 Optuna 的先验”。因此当前保留的是执行框架，不是搜索边界。

### Optuna 集成方案

```python
import optuna

def objective(trial):
    """目标函数：最大化训练集总PnL"""
    # 搜索空间（基于今天的先验知识缩小范围）
    max_atr_ratio = trial.suggest_float("max_atr_ratio", 0.005, 0.03, step=0.005)
    min_distance_pct = trial.suggest_float("min_distance_pct", 0.003, 0.02)
    tp2_target = trial.suggest_float("tp2_target", 2.0, 3.5, step=0.5)
    # 固定已验证结论
    breakeven = False  # 已验证必须关
    tp1_target = 1.0   # 已验证不变

    total_pnl = 0
    for symbol in SYMBOLS:
        result = await run_one(symbol, "2023-01-01", "2024-01-01", params)
        total_pnl += result["pnl"]
    return total_pnl

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=200)
```

### 暂停使用的旧先验

> 以下内容仅保留为历史记录，当前不得直接拿来约束搜索空间。

| 参数 | 今天的结论 | Optuna 搜索范围 |
|------|-----------|---------------|
| breakeven | 必须关闭 | **固定 False**（不搜索） |
| tp1_target | 1.0R 不变 | **固定 1.0**（不搜索） |
| tp2_target | 不能低于2.5R | 2.0 ~ 3.5（下限放宽，上限保守） |
| max_atr_ratio | 有效区间 ~1% | 0.005 ~ 0.03（放宽探索） |
| min_distance_pct | 单独无效 | 0.003 ~ 0.02（保留探索） |
| ema_period | 默认60 | 40 ~ 80（今天未测，缩小范围） |

### ⚠️ 并发限制

当前回测器通过写 SQLite 全局 KV 配置 (`config_entries_v2`) 传递参数，并发跑会互相覆盖。Optuna 串行模式（默认）无此问题。如需并发，需改造 BacktestRequest 支持运行时覆写。

---

## 新增后续规划：研究基线重建 + 实盘预期映射收口

> 2026-04-21 22:10 注：时间顺序修正、funding 净值闭环、MTF 真源统一、风险口径修正均已完成。
> 当前优先级从“追最优参数”切换为“最小验证矩阵 -> 先验分层 -> 小规模搜索”。

### 当前共识（2026-04-21 重排）

- 当前回测系统已经足够支持 **单品种 / 主流币 / 小资金（3w U 以内）** 的策略筛选与测试盘决策
- 当前“悲观撮合”更适合作为 **stress 口径**，用于判断策略能否扛住高摩擦环境
- 当前“真实/BNB9”结果只能保留为**旧语义下观察值**，不能直接设定测试盘预期
- 当前阶段的主要风险不是容量，而是 **把失效研究结果继续写入参数方向和排期**

### 必修修正项（在继续扩大实盘预期前完成）

| 优先级 | 项目 | 原因 | 预估 |
|------|------|------|------|
| **P0** | **撤销 `2026-04-20` 的 ETH alpha / ETH 主线 / 旧先验叙事** | 昨天已将“ETH 盈利观察”上升为正式方向，必须先从计划和沟通口径中清理 | 0.5h |
| **P0** | **确认 MTF 单一真源（定义、周期映射、EMA 周期、closed-candle 规则）** | 问题已不是单点 bug，而是研究语义、代码实现、planning 排期漂移 | ✅ 已完成 |
| **P0** | **重写 `min_distance_pct / max_atr_ratio` 的研究语义说明** | 当前 planning 中把参数外延说大了，容易把局部过滤器误当成全局 alpha 维度 | 0.5h |
| **P0** | **基于新研究真源重跑最小验证** | 需要先确认 ETH 盈利是否仍然存在，再决定是否恢复 Optuna / ETH 主线 | ✅ 已完成（LONG-only 基线可复现） |
| **P0** | **风险口径修正（true equity + 可追溯峰谷）** | 回撤口径若失真，会直接污染“是否可上测试盘”的判断 | ✅ 已完成 |
| **P1** | **回测模式显式拆分为 `stress` / `expected`** | 避免同一套参数同时承担筛选线和收益预测，减少语义混乱 | 1h |
| **P1** | **重写 slippage 归因统计** | 当前 `total_slippage_cost` 统计口径过弱，无法真实解释成本来自 ENTRY/TP/SL 哪一段 | 1h |
| **P2** | **SL gap-through 建模增强** | 加密 24h + 主流币下优先级下降，但仍应保留更保守的跳价处理能力 | 1h |

### 当前下一步（收敛版）

1. 最小验证矩阵（固定新基线语义）：`ETH 1h 2025`、`ETH 1h 2024`、`BTC 1h 2025`
2. 先验分层：强/弱/禁止先验
3. 恢复小规模搜索（先稳健性、后最优值），并显式拆分 `stress` / `expected`

### 当前阶段暂不优先的事项

| 事项 | 暂缓原因 |
|------|------|
| 深度/容量/冲击成本 | 小资金、单品种、主流币阶段不是第一矛盾 |
| 多品种组合成交仿真 | 当前目标是验证单策略到测试盘的映射，不急于做组合层建模 |
| 高频/盘口级别撮合 | 1h 周期下收益主要受撮合语义和成本分层影响，盘口仿真性价比低 |

### 建议的实盘预期解释框架

| 口径 | 用途 | 当前对应 |
|------|------|------|
| `stress` | 判断策略是否足够强，是否值得上测试盘 | 当前悲观撮合 |
| `expected` | 设定测试盘期间的预期收益/回撤中枢 | 仅在新基线验证后恢复 |
| `live` | 用测试盘真实成交反校准回测参数 | 暂未开放，等待新基线 |

### 与当前路线的衔接（已重排）

- **ETH 单币种测试盘** 冻结，直到 ETH 盈利不再只是旧语义下的观察值
- **Optuna** 工程链路保留，但策略搜索冻结，等待新研究真源落地
- **BTC / SOL / ETH 强弱排序** 失效，不再引用昨天的跨币结论
- **昨天的工程收口成果** 保留，但不得自动继承昨天的研究结论

### 新的推荐执行顺序

```
现在
  ↓
[阶段 A0] 撤销昨天 ETH alpha 叙事，冻结旧研究结论
  ↓
[阶段 A1] 确认 MTF 单一真源（定义/映射/EMA 周期/closed-candle）
  ↓
[阶段 A2] 重写参数语义说明（EMA distance / ATR max ratio）
  ↓
[阶段 A3] 用新真源做 ETH 1h 最小验证（2025 优先）
  ↓
[阶段 A4] 判断是否恢复 ETH 主线 / 恢复 Optuna
  ↓
[阶段 B] 拆分 stress / expected 两档回测口径
  ↓
[阶段 C] 小规模 Optuna / OOS（仅在 A3 通过后）
  ↓
[阶段 D] Walk-Forward / Monte Carlo
  ↓
[阶段 E] BTC / SOL 再评估
```

---

## 后续备忘：实盘执行风险（摘要）

> 当前阶段仍以**回测优化**为主，以下仅做摘要备忘，不并入当前主任务正文。
> 详细分析见：
> [实盘执行链风险与缺失功能分析（2026-04-21）](/Users/jiangwei/Documents/dingdingbot/docs/planning/architecture/2026-04-21-live-execution-gap-analysis.md)

### 摘要结论

- 当前系统已经具备较完整的实盘组件雏形：`ExchangeGateway`、`OrderLifecycleService`、`OrderRepository`、`ReconciliationService`
- 当前主要风险不在策略逻辑，而在 **自动执行主链尚未完全收口**
- 当前更像“回测/信号/订单/对账组件齐备”，但缺少一个稳定的统一编排器把它们串成单一闭环
- 因为尚未进入实盘准备阶段，这些问题先作为 **架构债清单** 记录，不挤占当前回测优化主线

### 摘要级风险清单

| 优先级 | 风险/缺口 | 当前处理原则 |
|------|------|------|
| P0 | 自动执行入口分裂（`SignalPipeline` 与订单执行链未见统一 orchestrator） | 先记录，待实盘阶段集中收口 |
| P0 | API 下单看起来直接调用 `gateway.place_order()`，本地生命周期未必先落库 | 先记录，待实盘阶段核对并改造 |
| P0 | WebSocket 订单回写与生命周期服务的接口协议疑似不一致 | 先记录，待实盘阶段专项验证 |
| P1 | ENTRY 成交后自动挂 TP/SL 的实盘闭环不清晰 | 先记录，待测试盘前补齐 |
| P1 | Position / Order / Reconciliation 的单一真源尚不够明确 | 先记录，待实盘阶段统一事件源 |
| P1 | CapitalProtection 主要挂在 API 前置校验，未来内部自动执行可能绕过 | 先记录，待执行链收口时统一门禁 |

---

## 阶段总览

| 阶段 | 内容 | 工时 | 状态 |
|------|------|------|------|
| **阶段 A0** | 回测语义修正（时间顺序 + funding 闭环） | 1.5-2.5h | **已完成** |
| **阶段 A1** | 撤销昨天 ETH alpha 叙事并冻结旧研究结论 | 0.5h | **已完成** |
| **阶段 A2** | 确认 MTF 单一真源 | 1-2h | **当前** |
| **阶段 A3** | 重写参数语义说明（EMA distance / ATR max ratio） | 0.5h | A2 后 |
| **阶段 A4** | 新研究真源下的 ETH 1h 最小验证 | 1h | A3 后 |
| **阶段 B** | `stress` / `expected` 双口径回测模式 | 1h | A4 后 |
| **阶段 C** | 小规模 Optuna / OOS（仅在 A4 通过后） | 2-3h | 待启动 |
| **阶段 D** | Walk-Forward 验证 | 1-2h | 阶段C后 |
| **阶段 E** | Monte Carlo 鲁棒性测试 | 0.5h | 阶段D后 |
| **阶段 F** | 月度收益热力图 | 0.5h | 可与B并行 |
| **阶段 G** | BTC 单独攻坚（仅在新 MTF 语义下重评后） | 1-2h | 阶段D后 |
| **阶段 H** | 前端归因可视化 | 4h | 阶段G后 |
| **总计** | | **~12-15h** | |

### 推荐执行顺序

```
现在
  ↓
[阶段 A0] MTF 定义修正
    → 先做
  ↓
[阶段 A1] ETH 1h 最小验证（基线参数）
    → ~1h
  ↓
[阶段 A2] 判断是否恢复 ETH 主线 / Optuna
    → 立即
  ↓
[阶段 B] stress / expected 双口径
    → ~1h
  ↓
[阶段 C] 小规模 Optuna（仅在 A2 通过后）
    → ~2-3h
  ↓
[阶段 D] Walk-Forward 验证
    → ~1-2h
  ↓
[阶段 E] Monte Carlo 测试
    → ~30min
  ↓
[阶段 F] 月度热力图（可与 B-C 并行）
    → ~30min
  ↓
[测试盘/实盘] 用验证后的参数，保守仓位
  ↓
[阶段 H] 前端归因可视化（最后）
    → ~4h
```

---

## 暂缓事项

| 事项 | 理由 |
|------|------|
| BNB 数据修复 | 需补充 4h 历史数据，等 Optuna 阶段后 |
| BTC 4h 放宽 ATR | 等 A0/A1 完成后再做，避免撮合语义误判成策略缺陷 |
| SOL 动态止损 | 代码改动大，等 Optuna 确认方向后再做 |
| MTF 归因修复 | 不影响交易，优先级低 |

---

## 已完成阶段

| 阶段 | 内容 | 日期 |
|------|------|------|
| P0 | 回测正确性验证 + 分批止盈 + TTP 修复 | 04-16 |
| 5.1-5.4 | 策略归因系统 | 04-18 |
| 5.7 | 归因分数诊断 + 配置锁定 | 04-19 |
| 手动调参 | BE=OFF / ATR=1% / TP2=1.5R否决 / BTC 4h | 04-20 |
| 数据校验 | 三层回测数据验证 | 04-20 |

---

*Last updated: 2026-04-21 22:10*
