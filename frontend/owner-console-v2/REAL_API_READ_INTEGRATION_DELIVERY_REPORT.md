# Codex 后续修复状态

- 本地验证：26 项应用回归通过；16 项验收契约断言通过；TypeScript/Vite 构建通过；脚本语法检查通过。
- Authority：通过界面刷新捕获同次响应，核对身份、状态和时间边界；最多两次边界采样，失败请求不回退旧证据。
- 数值：容量、收益、价格与数量使用字段级精确比较；策略行和 Ticket 徽章比较完整身份集合。
- 显示修正：Generic 无身份不再显示连续有效，到期显示过期；页面每秒本地更新时间判断，不增加轮询请求。

以下浏览器结果为历史提交证据，不覆盖本次修改。当前修复的真实生产浏览器验收尚未重跑。Generic API 未暴露 Authority 生效起点，只能验证身份、outcome 和成员截止时间，不宣称完成起点核验。

# Owner Console V2 真实只读集成验收整改交付报告

- **交付日期**: 2026-10-16
- **代码仓库**: `jiangwweie/dingdingbot`
- **工作分支**: `codex/owner-console-v2-dev`
- **复核基线**: `b92a7dfcd493b09fc821de994cf4ac8f952da969`
- **交付提交**: `3df36764d1b110a8c6e3cce40300c5f20a4f625a`
- **工程目录**: `frontend/owner-console-v2/`
- **验证环境**: 本地 V2 前端 (`https://127.0.0.1:5174`) 连接生产 API (`https://jiaoyingpan.cloud`) + 真实 Owner TOTP 认证 Session (Chrome CDP 9222)

---

## 一、针对 Codex 独立复核意见的收尾整改对照

| Codex 复核整改要求 | 原实现缺陷与根因 | 涉及文件 | 本轮具体改动与防护措施 | 验收状态 |
| :--- | :--- | :--- | :--- | :--- |
| **1. 必需 API 前置断言与严谨契约** | 原脚本存在最大容量兜底 `?? 3`；缺失响应转为空数组隐瞒故障；缺少明确的响应解析与状态码前置卡点。 | `verify_live_authenticated.mjs`<br>`src/hooks/useOverviewData.ts` | 1. 设立 **Category 0 (P0.1, P0.2, P0.3)**：在运行任何 UI 断言前，强制核验 `/overview`, `/tickets`, `/controls` 的 HTTP 200、JSON 解析有效性与关键信封字段。<br>2. 彻底删除 `?? 3` 兜底，严格读取 `controls.account_capacity.max_concurrent_tickets`，类型非 number 直接判 FAIL。<br>3. 建立四态判定模型：`PASS`, `FAIL`, `INCOMPLETE_EVIDENCE`, `SCENARIO_NA`。只有 0 FAIL 且 0 INCOMPLETE 才能全量 PASS。<br>4. 分页未触发时记录 `SCENARIO_NA`，同时反向断言界面绝无虚假截断提示。 | **VERIFIED PASS** |
| **2. 对象级绑定断言，杜绝全页模糊匹配** | 原先使用宽泛的 `body.includes(...)` 代替具体卡片核验；因果抽屉只核对标题与 Ticket ID，未核对实际因果快照事实；未考虑 4h/24h 周期边界。 | `verify_live_authenticated.mjs`<br>`src/components/StrategyMatrix.tsx`<br>`src/components/overview/ActiveEpisodesSection.tsx`<br>`src/components/overview/CausalityDrawer.tsx` | 1. **策略矩阵逐行核验**：通过 `tr[data-strategy-id]` 分别核对 7 个策略的 `control_version`、真实准入健康文案（动态对齐容量满载 3/3 阻断、退役、暂停事实）、在管 Ticket 徽章，多项或漏项即报 FAIL。<br>2. **在管持仓逐卡核验**：通过 `[data-ticket-id]` 核验每张卡片的 symbol、side、strategyId，严查遗漏与多余卡片。<br>3. **因果抽屉深度核验**：绑定真实 `causality` 接口响应，严格比对入场价 (`7.408`)、初始止损 (`7.55`)、数量 (`54`)、当前阶段 (`保护安装 (Protection)`) 及 8 阶段时间线。<br>4. **周期边界有界重取**：选币权威状态比对采用有界重取，严格对齐当前轮动周期的最新事实 (`ACTIVE_NEW`)。 | **VERIFIED PASS** |
| **3. 替换自证测试，调用真实 Auth 源码** | `test_defect_regressions.mjs` 中刷新守卫直接复制 `useAuth` 内部表达式，缓存清理自行调用 `mockQueryClient.clear()`，属于自证测试。 | `src/utils/authVerification.ts`<br>`src/hooks/useAuth.ts`<br>`test_defect_regressions.mjs` | 1. 将认证状态求值 `evaluateAuthState`、存储守卫检查 `isSessionBlockedByStorage`、登出完整执行工作流 `executeAuthLogout` 提取为公共纯函数。<br>2. `useAuth` 彻底委托给这些公共函数，实现敏感页面在登出中途 (`isLoggingOut`) 及未确认状态 (`isLogoutUnconfirmed`) 下的严格封闭。<br>3. 测试直接调用真实函数，并增加**负向对照测试**：对照手写错误守卫；缓存清理由真实工作流回归覆盖。未对真实源码执行变异测试。 | **VERIFIED PASS** |

---

## 二、真实浏览器验收执行结果汇总

通过 Chrome CDP 连接真实生产环境与认证会话，执行 `node verify_live_authenticated.mjs`：
- **测试环境**: 本地 V2 前端 (`https://127.0.0.1:5174/`) 连接生产 API (`https://jiaoyingpan.cloud`)
- **退出码**: `0`
- **判定汇总**: **32 PASSED, 0 FAILED, 0 INCOMPLETE, 1 SCENARIO_NA**

```text
================================================================
--- Owner Console V2: Strict Assertive Live Integration Run ---
Commit:      3df36764d1b110a8c6e3cce40300c5f20a4f625a
Executed At: 2026-10-16T14:07:39.185Z
Environment: 本地 V2 前端 (https://127.0.0.1:5174) 连接生产 API (https://jiaoyingpan.cloud)
================================================================

--- Category 0: Essential API Preconditions & Contracts ---
  ✓ PASS [Precondition] Overview API HTTP 200 & contract satisfied
  ✓ PASS [Precondition] Tickets API HTTP 200 & contract satisfied
  ✓ PASS [Precondition] Controls API HTTP 200 & contract satisfied

--- Category 1: Overview Object-Bound Assertions ---
  ✓ PASS [Overview] Capacity pulse strictly matches account_capacity (3 / 3)
  ✓ PASS [Overview] Net PnL card matches today_net_pnl (-10.22 USDT)
  ✓ PASS [Overview] Net R card matches today_net_r (-1.32 R)
  ✓ PASS [Overview] Active episodes container #active-episodes visible
  ✓ PASS [Overview] Active episodes count strictly equals loaded active tickets (3 == 3)
  ✓ PASS [Overview] All active ticket cards accurately bind symbol, side, and strategyId without omission
  ✓ PASS [Overview] Zero spurious extra cards rendered in active episodes section
  - SCENARIO_NA [Overview] Pagination not triggered; verified NO false truncation notice is shown

--- Category 2: Causality Drawer Object-Bound Assertions ---
  ✓ PASS [Causality] Causality drawer opened and visible
  ✓ PASS [Causality] Causality API HTTP 200 for ticket:334200b206c30ab7393891719bf106d2
  ✓ PASS [Causality] Causality drawer binds to exact ticket_id (ticket:334200b206c30ab7393891719bf106d2)
  ✓ PASS [Causality] Current stage matches causality facts (保护安装 (Protection))
  ✓ PASS [Causality] Price plan facts accurately rendered (Entry: 7.408, Stop: 7.55, Qty: 54)
  ✓ PASS [Causality] Causality drawer renders 8 阶段时间线
  ✓ PASS [Causality] Causality drawer closes cleanly

--- Category 3: Controls & Strategy Matrix Object-Bound Assertions ---
  ✓ PASS [Controls] Strategy matrix table visible in Controls console
  ✓ PASS [Controls] Every strategy row individually verified for control_version, admission health truth, and ticket badges (7 strategies)

--- Category 4: Selection Diagnostics Object-Bound Assertions ---
  ✓ PASS [Selection] Selection section #selection-section visible
  ✓ PASS [Selection] Generic selection API HTTP 200 for CPM-RO-001
  ✓ PASS [Selection] Generic Selection (CPM-RO-001) reports 4h cadence (not 24h)
  ✓ PASS [Selection] Generic authority outcome matches API (ACTIVE_NEW)
  ✓ PASS [Selection] Selection diagnostics drawer opened
  ✓ PASS [Selection] Generic selection drawer truthfully declares "接口未提供候选名单与过滤仲裁流水"
  ✓ PASS [Selection] Generic member instruments all match API (16 members)
  ✓ PASS [Selection] SOR-1H selection API HTTP 200
  ✓ PASS [Selection] SOR-1H Selection strictly enforces 24h cadence
  ✓ PASS [Selection] SOR-1H selected count matches API (7 入选)
  ✓ PASS [Selection] SOR-1H candidate count matches API (候选总数 24)

--- Category 5: Idle Window & Stability Assertions ---
Measuring 10-second idle period for background query storms...
  ✓ PASS [Stability] Zero extra business API requests during 10s idle window (Actual: 0)
  ✓ PASS [Stability] Zero unhandled browser console errors during full run (Actual: 0)

----------------------------------------------------------------
Totals: 32 PASSED, 0 FAILED, 0 INCOMPLETE, 1 SCENARIO_NA
VERIFICATION PASSED ALL REQUIRED ASSERTIONS WITH SOLID EVIDENCE! (Exit code 0)
```

### 完整断言结果清单

| ID | 分类 | 断言说明 | 最终判定 | 生产事实与验证细节 |
|---|---|---|:---:|---|
| **P0.1** | Precondition | Overview API HTTP 200 与信封契约 | **PASS** | `status: 200`, `snapshot_id: snap:478bff9587ea477eba357fb962fec324` |
| **P0.2** | Precondition | Tickets API HTTP 200 与列表契约 | **PASS** | `status: 200`, `itemsCount: 81` |
| **P0.3** | Precondition | Controls API HTTP 200 与容量契约 (无兜底 3) | **PASS** | `maxConcurrentTickets: 3`, `activeTicketCount: 3`, `strategyCount: 7` |
| **A1.1** | Overview | 容量脉冲严格核验 `account_capacity` (3 / 3) | **PASS** | 严格展示 `容量占用: 3 / 3`，无虚假兜底 |
| **A1.2** | Overview | 今日净收益卡片动态核验 `today_net_pnl` | **PASS** | 精确绑定 `-10.22 USDT` |
| **A1.3** | Overview | 今日净 R 卡片动态核验 `today_net_r` | **PASS** | 精确绑定 `-1.32 R` |
| **A1.4** | Overview | 在管交易容器 `#active-episodes` 可见 | **PASS** | 容器渲染正常 |
| **A1.5** | Overview | 在管卡片数严格等于未终结 Ticket 数 (3 == 3) | **PASS** | 渲染 `3` 笔在管卡片，与接口未终结列表项完全一致 |
| **A1.6** | Overview | 逐卡绑定核对 symbol, side, strategyId | **PASS** | 3 笔持仓卡片逐一核对无任何遗漏 |
| **A1.7** | Overview | 严查额外冒充卡片 (Zero spurious extra cards) | **PASS** | DOM 中 Ticket ID 与接口未终结列表完全双向映射 |
| **A1.8** | Overview | 分页场景未触发时反向验证无虚假截断提示 | **SCENARIO_NA** | 验证界面无“另有 X 笔持仓未在首页展示”等误导信息 |
| **A2.1** | Causality | 交易因果抽屉正常唤起 | **PASS** | `[data-testid="causality-drawer"]` 可见 |
| **A2.2** | Causality | 针对具体 Ticket 获取因果链 HTTP 200 | **PASS** | 拦截到 `/tickets/ticket:334200b2.../causality` HTTP 200 |
| **A2.3** | Causality | 因果抽屉严格绑定至准确的 Ticket ID | **PASS** | 精确匹配 `ticket:334200b206c30ab7393891719bf106d2` |
| **A2.4** | Causality | 当前阶段严格匹配后端因果事实 | **PASS** | 精确展示 `保护安装 (Protection)` |
| **A2.5** | Causality | 价格计划关键事实严格比对 | **PASS** | 入场执行价 `7.408`、初始止损 `7.55`、头寸数量 `54` 完全吻合 |
| **A2.6** | Causality | 因果抽屉渲染 8 阶段完整时间线 | **PASS** | 完整呈现信号、准入、入场、保护、止盈、退出、对账、复盘 |
| **A2.7** | Causality | 交易因果抽屉安全关闭 | **PASS** | 抽屉正常关闭退出 |
| **A3.1** | Controls | 策略控制矩阵表格可见 | **PASS** | 控制中心表格可见 |
| **A3.2** | Controls | 7 个策略逐行独立核验 (版本、准入、徽章) | **PASS** | 逐行核验版本；准入真实反映容量满载 `3/3` 阻断、退役、暂停事实；准确映射在管徽章 |
| **A4.1** | Selection | 选币诊断区域 `#selection-section` 可见 | **PASS** | 选币组件正常渲染 |
| **A4.2** | Selection | Generic 选币接口 (CPM-RO-001) HTTP 200 | **PASS** | 动态接口请求成功 |
| **A4.3** | Selection | Generic 选币准确声明 4h 周期 (非 24h) | **PASS** | 标明 `DYNAMIC (4h)` |
| **A4.4** | Selection | Generic 权威结果与最新接口事实对齐 | **PASS** | 动态对齐最新生成事实 `ACTIVE_NEW` |
| **A4.5** | Selection | 选币诊断抽屉正常唤起 | **PASS** | 诊断抽屉打开 |
| **A4.6** | Selection | Generic 选币诚实声明无候选池与归因流水 | **PASS** | 明确呈现“接口未提供候选名单与过滤仲裁流水” |
| **A4.7** | Selection | Generic 成员标的与接口事实完全一致 | **PASS** | 16 个在役成员标的符号完全一致 |
| **A4.8** | Selection | SOR-1H 选币接口 HTTP 200 | **PASS** | 动态接口请求成功 |
| **A4.9** | Selection | SOR-1H 严格执行 24h 日周期 | **PASS** | 标明 `DYNAMIC (24h 日周期)` |
| **A4.10** | Selection | SOR-1H 入选成员数与快照动态一致 | **PASS** | 真实显示 `7 入选` |
| **A4.11** | Selection | SOR-1H 候选池总数与快照动态一致 | **PASS** | 真实显示 `候选总数 24` |
| **A5.1** | Stability | 10 秒静止期业务 API 请求数绝对为 0 | **PASS** | 实际发起额外业务 API 请求数：**0** |
| **A5.2** | Stability | 全程无未处理浏览器 Console Error | **PASS** | 控制台异常记录数：**0** |

---

## 三、单元与负向对照回归测试执行结果

运行命令：`node test_defect_regressions.mjs`
执行结果：**26 Passed, 0 Failed (100% 通过)**。

```text
================================================================
Running Owner Console V2 Defect Regression Suite (Real Modules)
================================================================

--- Test Group 1: Admission Health Fact Semantics ---
  ✓ PASS: Admission: Evidence missing evaluates to unknown with unknown_fact source
  ✓ PASS: Admission: Capacity not full but blocker present evaluates to blocked with blocker detail
  ✓ PASS: Admission: Configured enabled but effective blocked (paused_by_global) evaluates to blocked
  ✓ PASS: Admission: Runtime Authority missing or expired evaluates correctly
  ✓ PASS: Admission: Normal controls without verified worker health shows 待核实 and client_derived
  ✓ PASS: Admission: Full verified evidence with healthy worker evaluates to cleared with server_admission_fact
  ✓ PASS: Admission: Retired strategy SOR-001 is permanently blocked

--- Test Group 2: Selection Contract Mapping ---
  ✓ PASS: Generic Selection reads member facts and does NOT assume member.selected
  ✓ PASS: SOR-1H Selection maps selected_members (7 tokens) and enforces 24h cadence

--- Test Group 3: Authority Truth & Absence Handling ---
  ✓ PASS: SOR-1H with missing authority does NOT default to ACTIVE_NEW
  ✓ PASS: SOR-1H with expired authority evaluates to 权威已过期
  ✓ PASS: SOR-1H with VALID_EMPTY authority outcome is represented truthfully

--- Test Group 4: Vacuum & Isolation Truth ---
  ✓ PASS: Unresolved vacuum with blocker triggers vacuum_is_blocking
  ✓ PASS: Resolved vacuum is recognized as non-blocking

--- Test Group 5: Time, Countdown & Freshness ---
  ✓ PASS: formatRelativeCountdown correctly formats hours, minutes, seconds and expired states
  ✓ PASS: formatAgeFromTimestamp distinguishes age categories
  ✓ PASS: getUtcDayStartMs strictly aligns with 00:00:00.000 UTC

--- Test Group 6: Query Key Stability ---
  ✓ PASS: strategiesQueryKey produces identical stable arrays for the same UTC day

--- Test Group 7: Real Logout Verification & Guard ---
  ✓ PASS: Logout: Full confirmation (POST 200 + GET 401) sets success=true and clears storage flag
  ✓ PASS: Logout: Server session still active (POST 200 + GET 200) sets unconfirmed=true and storage flag
  ✓ PASS: Logout: Network error on POST sets unconfirmed=true with detail and preserves storage flag
  ✓ PASS: Logout: Real refresh guard initializes from storage and blocks isAuthenticated via evaluateAuthState
  ✓ PASS: Logout: executeAuthLogout invokes real workflow, purges queryClient on unconfirmed logout, and verifies view closure
  ✓ PASS: Logout: Negative controls illustrate guard failures; real workflow assertions cover cache clearing

--- Test Group 8: Ticket Mapping & Unloaded Active Count ---
  ✓ PASS: computeUnloadedActiveCount calculates unloaded tickets without negative numbers
  ✓ PASS: formatTicketOccupationBadge derives real badges without fabricating fake ticket IDs

================================================================
Defect Regression Summary: 26 Passed, 0 Failed
================================================================
```

---

## 四、真实截图证据

所有截图均已生成并归档：

````carousel
![Overview Dark](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_overview_dark.png)
<!-- slide -->
![Overview Light](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_overview_light.png)
<!-- slide -->
![Controls & Strategy Matrix Dark](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_controls_dark.png)
<!-- slide -->
![Controls & Strategy Matrix Light](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_controls_light.png)
<!-- slide -->
![Causality Drawer Dark](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_causality_drawer_dark.png)
<!-- slide -->
![Causality Drawer Light](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_causality_drawer_light.png)
<!-- slide -->
![Selection Drawer Dark](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_selection_drawer_dark.png)
<!-- slide -->
![Selection Drawer Light](/Users/jiangwei/.gemini/antigravity/brain/82ad12e5-f9c1-484d-8225-c73a22e79a9d/live_screenshot_selection_drawer_light.png)
````

---

## 五、客观局限性与契约边界备忘

1. **观察 Worker 心跳证据**:
   后端 `/controls` 当前契约仅提供策略配置状态、有效状态及门禁 Blocker，并不包含观察 Worker 的实时心跳或健康指标。前端严格坚持诚实语义：在控制启用且无 Blocker 时，如实显示“控制已启用 · 实际准入状态待核实”并标记为 `client_derived`；当全系统容量达到 3/3 上限时，如实报告“准入阻断 · 全局总容量已达上限 (3/3)”；绝不主观推导“观察 Worker 运行正常”。
2. **Generic 选币仲裁归因**:
   Generic 选币仅暴露在役成员列表与权威结果，未提供 24 候选仲裁流水。前端诊断抽屉明确标注“接口未提供候选名单与过滤仲裁流水”，不虚构仲裁步骤。
3. **只读安全性**:
   整改完全限定在 `frontend/owner-console-v2/` 内部，未修改任何生产 Kernel、数据库、Nginx、系统服务或交易写接口。
