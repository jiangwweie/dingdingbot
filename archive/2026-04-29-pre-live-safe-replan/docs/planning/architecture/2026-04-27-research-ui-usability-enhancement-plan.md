# 2026-04-27 策略研究 UI 可用性增强方案

> 状态：执行中
> 范围：现有策略研究页面增强，不推倒重建
> 目标：把 Research Control Plane 从“工程对象列表”改成“围绕假设-验证-迭代闭环”的专业量化研究工作台

---

## 1. 当前判断

当前策略研究模块链路已通，但产品不可用。原因不是页面少，而是现有页面把工程对象直接暴露给用户：

1. `Job / Run / Spec / Artifact / Candidate` 等术语过于工程化
2. 回测历史只像任务队列，不能快速判断哪次实验值得打开
3. 回测详情只展示少量 metrics 和 artifact 路径，看不到实际参数、收益曲线、逐笔交易
4. 旧研究资产页和新 Research Control Plane 页并存，但语义边界不清

因此本阶段不新增一个全新“研究首页”，也不废弃现有页面；优先改造主链路：

1. `/research/new`
2. `/research/jobs`
3. `/research/runs/:run_result_id`

---

## 2. 页面去留判断

| 页面 | 当前路由 | 处理方式 | 理由 |
| --- | --- | --- | --- |
| 新建回测 | `/research/new` | 保留增强 | 已能创建真实 Research job |
| 研究任务 | `/research/jobs` | 改名并增强为“回测历史” | 是当前研究主入口 |
| 回测结果详情 | `/research/runs/:run_result_id` | 重点重构 | 是判断策略是否有价值的核心页面 |
| 历史报告 | `/research/backtests` | 保留但降级为旧版报告 | 兼容旧 `/api/research/backtests` 数据 |
| 候选策略 | `/research/candidates` | 保留，后续分新旧 tab | 仍有研究资产沉淀价值 |
| 候选详情 | `/research/candidates/:name` | 保留为旧候选详情 | 服务旧 candidate/optuna 资产 |
| 策略对比 | `/research/compare` | 保留，后续接新 candidate | 对比能力仍有价值 |
| 回测上下文 / Review Summary | `/research/replay/*`、`/research/review/*` | 保留为详情入口 | 不做一级入口 |

---

## 3. UI 约束与产品价值观

1. 不做新的 landing page；研究模块第一屏必须是可操作工作台。
2. 不做装饰型大卡片堆叠；控制台应紧凑、可扫读、信息优先。
3. 不用临时 SVG 作为长期图表方案；正式图表能力应直接围绕研究体验设计，优先考虑 ECharts 承载权益曲线、回撤图、热力图、雷达图、散点图。
4. 中文主名 + 英文/工程字段作为辅助，不直接把内部对象名作为用户主文案。
5. Artifacts / JSON / 路径归入“调试信息”，默认不作为业务主内容。
6. 工程噪音降级：
   - `rj_*` / `rr_*` / Git hash / 文件路径默认不进主视图
   - 仅放在详情页底部、折叠面板或 tooltip
7. 统一金融色彩：
   - 绿色：盈利、正向指标、改善
   - 红色：亏损、风险、退步
   - 灰/蓝：状态、事实、辅助信息
8. 回测耗时必须有反馈：
   - 提交按钮 loading
   - 运行中状态明确
   - 历史页刷新失败保留旧数据并提示

---

## 4. 术语映射

| 工程词 | UI 主文案 |
| --- | --- |
| Research Control Plane | 策略研究台 |
| Job | 回测任务 |
| Run Result | 回测结果 |
| Spec Snapshot | 回测设置快照 |
| Resolved Runtime Overrides | 实际生效参数 |
| Order Strategy | 出场规则 |
| Candidate | 候选策略 |
| Artifact | 结果文件 / 调试文件 |
| Return | 收益率 |
| Total PnL | 总收益 |
| Final Balance | 最终权益 |
| Sharpe Ratio | 夏普比率 |
| Max Drawdown | 最大回撤 |
| Trades | 交易次数 |
| Win Rate | 胜率 |
| Slippage | 开仓滑点 |
| TP Slippage | 止盈滑点 |
| Fee Rate | 手续费率 |

---

## 5. 第一阶段已落地骨架

### 5.1 后端只读 report endpoint

新增：

```text
GET /api/research/runs/{run_result_id}/report
```

用途：

1. 读取 `artifact_index.result` 指向的 `result.json`
2. 给前端提供权益曲线、逐笔交易、平仓事件等可视化数据
3. 不写 runtime、不写 research 元数据，只读 artifact

### 5.2 回测历史增强

`/research/jobs` 改为“回测历史”：

1. 增加概览统计：全部回测、已完成、失败、最佳收益、最低回撤
2. 列表展示市场、时间窗口、参数摘要、总收益、最大回撤、胜率、交易次数
3. 状态中文化：等待中 / 运行中 / 已完成 / 失败 / 已取消
4. 操作入口改为“查看”

### 5.3 回测详情增强

`/research/runs/:run_result_id` 重构为研究报告骨架：

1. 顶部显示市场、周期、UTC 时间窗口
2. 核心指标卡：最终权益、总收益、收益率、最大回撤、胜率、交易次数
3. 权益曲线：使用 `debug_equity_curve`
4. 实际生效参数：基线、方向、EMA、ATR、止盈结构、成本模型
5. 逐笔交易：使用 `positions`
6. 候选策略区中文化
7. artifact 路径折叠到“调试信息与结果文件”

### 5.4 新建回测语义增强

`/research/new`：

1. 表单 label 中文化
2. 增加默认 ETH 基线说明
3. 明确不会修改模拟盘/实盘配置
4. 时间字段标注 UTC

---

## 6. 下一阶段

## 6. v2.0 产品优先级调整

PM 评审后，Research UI 的优先级从“先把报告页面画出来”调整为“先打通研究员的迭代闭环”。

### Phase 1：研究闭环与主页面体验（立即优先）

1. `/research/new` 新建回测中心
   - 页面分区：
     - 基础信息：回测名称、业务备注、交易对、K线周期
     - 时间窗口：开始/结束时间、快捷选项（最近 1 个月、最近半年、2025 全年）
     - 策略与资金：基线配置、初始资金、可开放参数入口
     - 高级设置：最大 K 线数、开仓滑点、止盈滑点、手续费率
   - 支持 `clone_run` 参数，从已有回测结果复用配置
   - 右侧或顶部摘要：展示“本次将运行什么”
   - 可后续扩展数据覆盖率预检
2. `/research/jobs` 回测历史看板
   - 从任务流水账变为研究资产列表
   - 隐藏 hash ID
   - 显示名称、备注、市场、时间窗口、参数摘要、总收益、最大回撤、胜率、交易数
   - 收益/风险按金融颜色表达
   - 支持核心筛选：
     - 交易标的
     - 状态
     - 基线配置
     - 收益区间
   - 支持 2-4 条勾选进入横向对比（可做骨架）
3. `/research/runs/:id` 策略诊疗室
   - 顶部主动作：
     - 基于此配置新建回测（Clone & Tweak）
     - 晋升为候选策略
   - 核心指标增加：
     - 盈亏比 Profit Factor
     - 最大连续亏损次数（如数据可得）
     - 年化收益率（如数据可得）
   - 权益曲线必须配合回撤展示：
     - 优先使用正式图表组件
     - 标记最大回撤区间或回撤水下图
   - 逐笔交易表保留紧凑模式
   - 调试信息折叠

### Phase 2：正式图表能力与端到端验证

1. 引入正式图表能力，优先 ECharts。
2. 建立研究图表组件：
   - `EquityDrawdownChart`
   - `MonthlyReturnHeatmap`
   - `TradeScatterChart`
   - `StrategyRadarChart`
3. 先允许 mock 数据支撑 UI 体验；再逐步接真实 `result.json` artifact。
4. 补测试与浏览器冒烟。

适合交给 Claude：

1. API adapter 测试补 `getResearchRunReport`
2. `api_research_jobs` 单测补 `/runs/{id}/report`
3. 前端冒烟：创建回测 -> 历史页 -> 详情页 -> 权益曲线/逐笔交易展示

### Phase 3：候选策略资产化

1. `/research/candidates` 从 CI/CD 风格列表改为候选策略资产库
2. 分 tab：
   - 新研究候选 `CandidateRecord`
   - 历史候选 `Candidate`
3. 状态业务化：
   - `PASS_LOOSE` -> 初步达标
   - `REJECT` -> 未通过风控校验 / 不建议
   - `sortino_missing_or_suspect` -> 索提诺比率异常
4. 每个候选必须展示收益、回撤、胜率、交易数、迷你权益曲线
5. 从回测详情创建候选后可跳转候选详情

### Phase 4：策略对比与研究资产管理

1. `/research/compare` 废除不可识别的长下拉体验
2. 选择对象改为可搜索 modal：
   - 显示候选别名、收益、回撤、交易数
   - 支持从回测历史或候选策略中选择
3. 对比能力：
   - 多策略权益曲线叠加
   - 指标表差异红绿表达
   - 雷达图（收益、夏普、盈亏比、胜率、抗回撤能力）
4. 回测历史支持批量归档/隐藏

