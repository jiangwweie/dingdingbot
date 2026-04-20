# Optuna 第一轮窄搜索脚本 - 交接文档

> **日期**: 2026-04-21
> **任务**: 新增 Optuna 第一轮窄搜索执行脚本，验证 runtime_overrides 优化链路

---

## 📋 任务完成情况

### ✅ 已完成

1. **新增脚本**: `scripts/run_optuna_narrow_search.py`
   - 可直接运行
   - 使用本地数据仓库（不需要 API key）
   - 轮询任务状态，打印进度
   - 输出试验结果列表

2. **修复 OptimizationHistory 模型**
   - 问题：`params_json` 和 `metrics_json` 字段未正确填充
   - 修复：`_build_optimization_history()` 方法改为构建 JSON 字符串
   - 文件：`src/application/strategy_optimizer.py`

3. **修复 OptimizationJob.best_trial 字段**
   - 问题：使用了不存在的 `best_params` 属性
   - 修复：改为使用 `OptimizationTrialResult` 对象
   - 文件：`src/application/strategy_optimizer.py`, `scripts/run_optuna_narrow_search.py`

4. **添加默认策略配置**
   - 问题：`BacktestRequest` 未包含策略配置，导致 0 trades
   - 修复：`_build_backtest_request()` 添加默认 pinbar + EMA + MTF + ATR 策略
   - 文件：`src/application/strategy_optimizer.py`

---

## 🔧 技术细节

### 数据流验证

```
Optuna trial.suggest_*()
       ↓
params = {"max_atr_ratio": 0.015, "min_distance_pct": 0.008, "ema_period": 50}
       ↓
_build_runtime_overrides(params)
       ↓
BacktestRuntimeOverrides(max_atr_ratio=Decimal("0.015"), ...)
       ↓
run_backtest(request, runtime_overrides=overrides)
       ↓
resolve_backtest_params(runtime_overrides=overrides)
       ↓
ResolvedBacktestParams (最终消费对象)
```

### 日志验证

从运行日志可以看到参数正确传递：

```
[INFO] Running v3 PMS backtest with config: slippage=0.001, fee=0.0004, 
       initial_balance=10000, tp_slippage=0.0005, funding_enabled=True, 
       funding_rate=0.0001, 
       min_distance_pct=0.01877969512744685,    ← runtime_overrides 注入
       max_atr_ratio=0.02383887138101717,        ← runtime_overrides 注入
       breakeven_enabled=False
```

### 参数空间

| 参数 | 范围 | 类型 |
|------|------|------|
| `max_atr_ratio` | 0.005 ~ 0.03 | FLOAT |
| `min_distance_pct` | 0.003 ~ 0.02 | FLOAT |
| `ema_period` | 40 ~ 80 | INT |

### 实验配置

| 配置项 | 值 |
|--------|-----|
| 交易对 | ETH/USDT:USDT |
| 周期 | 1h |
| 时间范围 | 2024-01-01 ~ 2024-12-31 |
| 优化目标 | SHARPE |
| 试验次数 | 30 |
| 初始资金 | 10000 |
| 滑点率 | 0.001 |
| 手续费率 | 0.0004 |

---

## ⚠️ 发现的问题

### 问题 1: 所有试验 0 trades

**现象**: 所有 30 个 trial 都返回 0 trades

**原因分析**:
1. 策略过滤器组合过于严格（ATR + EMA distance + MTF 三重过滤）
2. ETH 1h 数据在 2024 年可能 pinbar 信号较少
3. 参数范围可能需要调整

**建议下一步**:
- 先用 BTC 数据测试（历史回测显示 BTC 信号更多）
- 放宽参数范围或减少过滤器
- 单独验证 pinbar 策略是否产生信号

### 问题 2: OptimizationHistory 模型不匹配

**现象**: Pydantic 验证错误，缺少 `params_json` 和 `metrics_json` 字段

**修复**: 更新 `_build_optimization_history()` 和相关方法

---

## 📁 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `scripts/run_optuna_narrow_search.py` | 新增脚本 |
| `src/application/strategy_optimizer.py` | 修复 OptimizationHistory、OptimizationJob、添加默认策略 |

---

## 🚀 运行方式

```bash
PYTHONPATH=. python3 scripts/run_optuna_narrow_search.py
```

---

## 📊 运行结果示例

```
============================================================
Optuna 第一轮窄搜索 - runtime_overrides 链路验证
============================================================

📍 实验配置:
   交易对: ETH/USDT:USDT
   周期: 1h
   时间范围: 2024-01-01 00:00:00 UTC ~ 2024-12-31 23:59:59 UTC
   优化目标: sharpe
   试验次数: 30

📐 参数空间:
   max_atr_ratio: [0.005, 0.03]
   min_distance_pct: [0.003, 0.02]
   ema_period: [40, 80]

🔧 初始化组件...
   ✅ 数据仓库: data/v3_dev.db
   ✅ Backtester 初始化完成
   ✅ StrategyOptimizer 初始化完成

🚀 启动优化任务...

📋 任务信息:
   job_id: opt_bc363c4e
   status: running
   total_trials: 30

⏳ 等待优化完成...
   进度: 4/30
   进度: 9/30
   ...

✅ 任务结束: completed

📊 试验结果（前 10 名）:
   [1] Trial #0
       objective_value: 0.0000
       params: {'max_atr_ratio': 0.023, 'min_distance_pct': 0.018, 'ema_period': 42}
       ...
```

---

## ✅ 验收标准完成情况

| 标准 | 状态 | 说明 |
|------|------|------|
| 脚本可以直接运行 | ✅ | 无需 API key，使用本地数据 |
| 能看到 trial 进度变化 | ✅ | 每 2 秒轮询，打印进度 |
| 能拿到 trial 结果列表 | ✅ | 输出前 10 名结果 |
| 参数空间只包含这 3 个参数 | ✅ | max_atr_ratio, min_distance_pct, ema_period |
| 全程走 runtime_overrides 链路，不写 KV | ✅ | 日志验证参数正确注入 |

---

## 📝 下一步建议

1. **验证策略信号**: 先用 BTC 数据测试，确认 pinbar 策略能产生信号
2. **调整参数范围**: 根据历史回测结果调整参数搜索范围
3. **减少过滤器**: 暂时禁用 ATR 或 MTF 过滤器，观察信号数量
4. **扩展参数空间**: 后续可加入 TP 参数（tp_ratios, tp_targets）

---

*交接文档 - 2026-04-21*
