# 2026-04-27 前端双轨并行执行计划

> 状态：准备并行实施
> 范围：Research 策略研究台 + Runtime 交易驾驶舱
> 目标：在不互相污染的前提下，同时推进“研究体验”和“运行观察体验”两条前端产品化主线

---

## 1. 是否可以双轨并行

结论：可以，而且应该并行。

原因：

1. 两条线对应不同一级菜单：
   - Research：`/research/*`
   - Runtime：`/runtime/*`、`/signals`、`/execution`
2. 两条线用户目标不同：
   - Research：提出假设、跑回测、看结果、复用参数、沉淀候选
   - Runtime：看资金、看风险、看执行链、看异常、必要时接管
3. 两条线数据域不同：
   - Research 读取 research jobs / runs / artifacts / candidates
   - Runtime 读取 runtime overview / portfolio / positions / signals / execution / health / events
4. 两条线写操作边界不同：
   - Research 只允许创建研究任务和候选策略
   - Runtime 第一阶段仍以只读观察为主，危险操作只做规划，不直接开放

因此双轨并行不会天然冲突，但必须管理共享文件和设计语义。

---

## 2. 共享边界与冲突点

### 2.1 允许共享

1. UI 基础组件
   - `Card`
   - `Badge`
   - `Table`
   - filter / sort 工具
2. 金融数字格式化理念
   - 盈利绿色
   - 亏损 / 风险红色
   - 状态灰/蓝
3. 图表能力
   - Research 优先使用 ECharts 做权益曲线、回撤、热力图
   - Runtime 后续也可复用相同图表封装展示风险趋势
4. 全局布局
   - 可以共享 Header / Sidebar 的视觉规范

### 2.2 必须隔离

1. Research 不能写 runtime profile
2. Runtime 不承载策略参数试验
3. Research 的候选策略不能直接下发 live
4. Runtime 的暂停 / 平仓能力不归 Research 页面管理
5. 两个 Claude 窗口不能同时大改：
   - `gemimi-web-front/src/services/api.ts`
   - `gemimi-web-front/src/types/index.ts`
   - `gemimi-web-front/src/components/layout/AppLayout.tsx`
   - `gemimi-web-front/package.json`

如果确实要改共享文件，必须小范围、追加式修改，并在输出中明确列出。

---

## 3. 并行任务拆分

### Track A：Research 策略研究台

目标：把研究台从“工程任务列表”升级为“假设-验证-迭代工作台”。

主要页面：

1. `/research/new`
2. `/research/jobs`
3. `/research/runs/:run_result_id`
4. `/research/candidates`
5. `/research/compare`

第一阶段重点：

1. 新建回测分区化
2. 支持 Clone & Tweak
3. 回测历史资产化
4. 详情页策略诊疗室
5. 正式图表能力
6. 候选策略状态业务翻译

参考文档：

1. `docs/planning/architecture/2026-04-27-research-ui-usability-enhancement-plan.md`

### Track B：Runtime 交易驾驶舱

目标：把运行环境从“工程监控面板”升级为“资金、风险、执行链优先”的交易驾驶舱。

主要页面：

1. `/runtime/overview`
2. `/runtime/portfolio`
3. `/runtime/health`
4. `/runtime/events`
5. `/signals`
6. `/execution`

第一阶段重点：

1. SIM / LIVE 环境条
2. 资金与风险首屏
3. 告警横幅
4. Portfolio 持仓风险增强
5. Signals / Execution 中文化和因果链入口
6. 工程字段折叠降噪

参考文档：

1. `docs/planning/architecture/2026-04-27-runtime-cockpit-experience-upgrade-plan.md`

---

## 4. 实施顺序

### Step 1：Research Track 继续前端 v2 产品化

原因：

1. 当前 Research UI 已有未提交改动
2. 已经引入 report endpoint、artifact 读取、回测详情骨架
3. 现在最需要把这批改动收敛成可用体验，避免半成品长期挂在工作区

验收重点：

1. `npm run lint`
2. API adapter tests
3. 浏览器冒烟：
   - `/research/new`
   - `/research/jobs`
   - `/research/runs/:id`

### Step 2：Runtime Track 启动只读驾驶舱增强

原因：

1. Runtime 当前已部署模拟盘观察
2. UI 需要快速从工程面板转向资金风险驾驶舱
3. 第一阶段只读增强风险较低

验收重点：

1. 不增加危险交易按钮
2. 不改 PG execution truth
3. 不写 runtime profile
4. Runtime 页面可在无数据、空仓、health degraded 时正常展示

---

## 5. 并行窗口建议

### Claude 窗口 1：Research UI v2

所有权：

1. `gemimi-web-front/src/pages/research/*`
2. `gemimi-web-front/src/lib/research-format.ts`
3. 只允许追加式修改 `api.ts` / `types/index.ts`

禁止：

1. 修改 Runtime 页面
2. 修改执行主线后端
3. 修改 runtime profile / PG execution truth

### Claude 窗口 2：Runtime Cockpit 只读增强

所有权：

1. `gemimi-web-front/src/pages/runtime/*`
2. `gemimi-web-front/src/pages/runtime/Execution.tsx`
3. `gemimi-web-front/src/pages/runtime/Signals.tsx`
4. 可新增 `gemimi-web-front/src/lib/runtime-format.ts`

禁止：

1. 修改 Research 页面
2. 增加真实平仓 / 暂停 / 清仓写操作
3. 修改后端 execution 语义
4. 修改 runtime profile 管理逻辑

---

## 6. 当前 Codex 判断

1. 双轨并行成立。
2. Research Track 应先把当前未提交 UI 改动收敛。
3. Runtime Track 第一阶段应只做只读体验增强，不做危险操作。
4. 两条线都应遵守同一套金融 UI 语言：
   - 钱和风险优先
   - hash 和内部 ID 降噪
   - 中文主文案
   - 异常高可见
   - 空状态和错误状态可解释

