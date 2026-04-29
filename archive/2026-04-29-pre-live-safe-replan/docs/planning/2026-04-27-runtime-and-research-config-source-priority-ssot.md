# 2026-04-27 Runtime / Research 配置来源优先级 SSOT

> 状态：执行中
> 目的：将 runtime execution 与 research/backtest 的配置来源优先级正式写清，避免 fallback 漂移和跨链污染

---

## 1. 结论摘要

后续所有配置讨论都应基于一个前提：

> **runtime 和 research 不只是“不同调用方”，而是两条不同的配置消费链。**

因此它们必须有不同的来源优先级和 fallback 纪律。

---

## 2. Runtime 链配置优先级

### 2.1 Runtime execution 的唯一业务真源

对 execution runtime 而言，业务配置真源应固定为：

1. **`ResolvedRuntimeConfig`**
2. **`RuntimeConfigProvider`**（process-local holder）

这条链适用于：

1. market
2. strategy
3. risk
4. execution

### 2.2 Runtime environment 的真源

以下内容属于 runtime environment，而非业务 profile：

1. `.env`
2. process env

适用项：

1. `PG_DATABASE_URL`
2. exchange API key / secret
3. webhook / notification secret
4. backend port
5. testnet / exchange name（其中 exchange execution semantics 会进入 hash，secret 不会）

### 2.3 Runtime fallback 纪律

允许的 fallback：

1. **启动期防御型 fallback**
   - provider 缺失时短暂回退到旧 `ConfigManager`
   - 仅允许发生在过渡期兼容代码里
   - 必须带日志警告
2. **只读面 fallback**
   - 当 runtime provider 缺失时，console 可回报 `no_provider` / `unavailable`
   - 不得伪装成真实 runtime config

不允许的 fallback：

1. runtime execution 运行中静默回落到研究/回测参数
2. runtime execution 运行中从 `config_entries_v2` 读 `backtest.*` 参数
3. runtime execution 依赖 `ConfigManager.set_instance()` 被别处注入后的全局状态

---

## 3. Research / Backtest 链配置优先级

### 3.1 Research/backtest 的主原则

research/backtest 不应再隐式读取 runtime process state。

其优先级应固定为：

1. **显式传入的 request / spec**
2. **显式传入的 `runtime_overrides` / overrides**
3. **显式注入的局部 config provider / config manager**
4. **研究链自身允许的 KV/defaults**
5. **代码默认值**

### 3.2 当前保留的兼容 fallback

为了兼容历史调用方，当前允许：

1. `Backtester` 在未注入 `config_manager` 时 fallback 到 `ConfigManager.get_instance()`

但这条规则必须被视为：

- `legacy_fallback`
- 非推荐路径
- 后续应继续压缩使用面

### 3.3 Research 链禁止项

1. 不允许通过 `ConfigManager.set_instance()` 改写 runtime 全局单例作为默认做法
2. 不允许把 candidate / optuna / replay 结果直接写回 runtime active profile
3. 不允许 research 脚本无确认切换 active profile

---

## 4. Profile 切换规则

### 4.1 Runtime profile

`runtime_profiles` 的使用规则：

1. `ResolvedRuntimeConfig` 只在启动期解析
2. 当前运行中的 runtime 不应被 profile switch 静默热切换
3. profile 切换必须显式确认（`confirm=true`）
4. 切换生效应面向“下次启动 / 显式 reload 流程”，而不是默认影响当前运行主链

### 4.2 Config profile

`config_profiles` / `config_entries_v2` 的切换规则：

1. 它们仍属于 config 域
2. 可以服务于研究、配置管理、历史兼容
3. 但不能再被默认为 runtime execution 的直接真源

---

## 5. 按对象划分的来源优先级

### 5.1 Runtime execution objects

| 对象 | 真源 | 允许 fallback | 禁止 fallback |
|------|------|---------------|---------------|
| orders | PG | 无 | SQLite execution path |
| execution_intents | PG | 无 | SQLite / memory-only |
| positions projection | PG | 交易所 snapshot enrich | 交易所 snapshot 覆盖 execution truth |
| recovery tasks | PG | 无 | SQLite pending_recovery |

### 5.2 Runtime config objects

| 对象 | 真源 | 允许 fallback | 禁止 fallback |
|------|------|---------------|---------------|
| market | ResolvedRuntimeConfig | 过渡期 ConfigManager + warning | 研究链 KV/backtest overrides |
| strategy | ResolvedRuntimeConfig | 过渡期 ConfigManager + warning | candidate/backtest params |
| risk | ResolvedRuntimeConfig | 过渡期 ConfigManager + warning | backtest KV |
| execution | ResolvedRuntimeConfig | 过渡期旧路径 + warning | `SignalResult.take_profit_levels` 重新变回真源 |

### 5.3 Research/backtest objects

| 对象 | 真源 | 允许 fallback | 禁止 fallback |
|------|------|---------------|---------------|
| BacktestRequest | explicit request/spec | runtime_overrides / local config_manager | runtime provider 静默覆盖 |
| Optuna trial params | explicit params | fixed params / runtime_overrides | runtime active profile 静默读取 |
| candidate report | explicit trial result | source profile hash for traceability | 直接 promote runtime |

---

## 6. 现在还需要继续收紧的点

### P1

1. `api.py:set_dependencies()` 里仍会 `ConfigManager.set_instance(config_manager)`
   - 这是 runtime 主链的合法 owner
   - 但需要在文义上与 research 脚本的禁止路径区分开
2. `Backtester` 仍保留 `ConfigManager.get_instance()` 兼容 fallback
   - 需要在注释/日志中标成 `legacy_fallback`
3. `config_entries_v2` 的 research/backtest 参数边界仍需更显式标识

### P2

1. profile switch 当前虽已确认门槛化，但“是否立即影响当前进程”仍需更清晰说明
2. console/config snapshot 可以进一步把 source-of-truth hints 做得更明确

---

## 7. 下一轮建议

### 由 Codex / GPT 继续承担

1. 把本 SSOT 与 runtime/config/research 现有文档对齐
2. 明确 `signals` 作为 pre-execution state 的迁移准入条件
3. 判断 profile switch 是否要继续收成“仅下次启动生效”

### 适合 Claude / GLM 的杂活

1. 给 `Backtester` 的 fallback 路径加清晰注释/日志
2. 为 config snapshot / runtime snapshot 补 source-of-truth hints 测试
3. 为 profile switch 的“立即生效 vs 下次启动生效”当前行为补文档或响应字段说明
