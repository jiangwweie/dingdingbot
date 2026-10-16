# Owner Console V2 真实只读集成验收整改交付报告

- **交付日期**: 2026-10-16
- **代码仓库**: `jiangwweie/dingdingbot`
- **工作分支**: `codex/owner-console-v2-dev`
- **基线提交**: `1f716c1446fc38db93027de31073e04122a2b877`
- **交付提交**: `3ff72a9af059e4e291552d7d32713799189f8a90`
- **工程目录**: `frontend/owner-console-v2/`
- **验证环境**: 本地 V2 前端 (`https://127.0.0.1:5174`) 连接生产 API (`https://jiaoyingpan.cloud`) + 真实 Owner TOTP 认证 Session

---

## 一、三项复核问题的具体改动点与对应文件

| 问题项 | 问题根因 | 涉及文件 | 具体改动与整改措施 |
| :--- | :--- | :--- | :--- |
| **问题一：修正准入健康状态的事实语义** | 原先在策略与全局未暂停、容量未满时，前端默认给出“准入畅通 · 观察 Worker 运行正常”且标记 `source: 'server_admission_fact'`。然而现有接口并未提供观察 Worker 心跳证据，属于前端主观臆测。 | `src/types/controls.ts`<br>`src/mapping/admissionHealthMapping.ts`<br>`src/hooks/useControlsData.ts` | 1. 拆分事实源类型：`server_admission_fact` \| `client_derived` \| `unknown_fact`。<br>2. 建立纯函数 `evaluateStrategyAdmissionHealth`，严格核对 `effective_state`、`first_blocker`、`account_capacity`、`runtime_entry_authority`。<br>3. 在未独立验证 Worker 健康时，严禁输出“观察 Worker 运行正常”，诚实显示**“控制已启用 · 实际准入状态待核实”**并标记为 `client_derived`。 |
| **问题二：真实浏览器验证脚本断言化** | 原脚本只有日志输出而无断言，失败不会返回非零退出码；依赖固定预期而非动态响应核对；缺少稳定窗口与控制台严格判定。 | `verify_live_authenticated.mjs`<br>`src/components/overview/ActiveEpisodesSection.tsx`<br>`src/components/overview/CausalityDrawer.tsx`<br>`src/components/SelectionDrawer.tsx` | 1. 通过 CDP 动态拦截 `/api/owner/v1` 的 `overview`, `tickets`, `controls`, `selection`, `causality` 实时响应。<br>2. 对容量脉冲、在管 Ticket 数量/符号、浮动 PnL/R、时间线阶段、选币周期 (Generic 4h / SOR 24h)、入选候选数量进行动态断言，无硬编码。<br>3. 增加 10 秒静止期 0 额外请求断言与 0 控制台错误断言。<br>4. 失败时立即返回非零退出码 (`process.exit(1)`)，成功输出结构化 PASS/FAIL/SKIP 清单。 |
| **问题三：回归测试改写为真实实现** | 原单测中登出判定、Ticket 未加载计算、策略矩阵徽章等均在测试函数内部使用本地假函数和临时对象模拟，脱离真实源码。 | `test_defect_regressions.mjs`<br>`src/utils/authVerification.ts`<br>`src/hooks/useAuth.ts`<br>`src/mapping/ticketMapping.ts` | 1. 彻底删除测试用例内部本地假函数与临时对象。<br>2. 直接导入真实模块函数：`evaluateStrategyAdmissionHealth`、`mapPreviewToDiagnostic`、`performLogoutVerification`、`computeUnloadedActiveCount`、`formatTicketOccupationBadge`。<br>3. 覆盖准入健康 5 大契约场景 + 真实健康证明分支；覆盖真实登出响应 (200 + 401 成功确认、200 + 200 未销毁拦截、网络中断异常、`sessionStorage` 刷新守卫与缓存清理)。 |

---

## 二、准入状态展示逻辑修正前后对比

| 状态场景 | 后端实际输入事实 | 修正前前端展示 (臆测) | 修正后前端展示 (事实真凭) | 事实来源标记 |
| :--- | :--- | :--- | :--- | :--- |
| **正常控制已启用 (无独立 Worker 探测)** | `configured: enabled`, `effective: enabled`, 容量未满, 权威正常, 无 worker 心跳字段 | 准入畅通 · 观察 Worker 运行正常 | **控制已启用 · 实际准入状态待核实** | `client_derived` |
| **容量未满但有 Blocker** | 容量 `2/3`, `globalEntry.effective: paused`, `first_blocker: MARGIN_HOLD` | 准入畅通 · 观察 Worker 运行正常 | **准入阻断 · 全局实际生效为暂停 (MARGIN_HOLD)** | `server_admission_fact` |
| **Configured 启用但 Effective 挂起** | `configured: enabled`, `effective_state: paused_by_global` | 准入畅通 · 观察 Worker 运行正常 | **受限挂起 · 全局 ENTRY 已由 Owner 暂停** | `server_admission_fact` |
| **Runtime Authority 缺失** | `runtime_entry_authority: null` | 准入畅通 · 观察 Worker 运行正常 | **权威缺失 · 运行时准入凭据不可用** | `unknown_fact` |
| **Runtime Authority 过期** | `expires_at_ms < nowMs` | 准入畅通 · 观察 Worker 运行正常 | **权威失效 · 运行时准入凭据已过期** | `server_admission_fact` |
| **Runtime Authority 围栏阻断** | `effective_status: fenced`, `first_blocker: CERT_MISMATCH` | 准入畅通 · 观察 Worker 运行正常 | **权威阻断 · 运行时围栏已建立 (CERT_MISMATCH)** | `server_admission_fact` |
| **确有充分正常证据** | 控制启用 + 权威正常 + `workerHealth.isHealthy = true` | 准入畅通 · 观察 Worker 运行正常 | **准入畅通 · 全链路证据充分 (Worker 心跳正常)** | `server_admission_fact` |
| **已退役策略** | `SOR-001` (retired) | 已永久退役 · 仅留存审计，禁止恢复 | **已永久退役 · 仅留存审计，禁止恢复** | `server_admission_fact` |

---

## 三、真实浏览器验证脚本断言清单与执行结果

在当前提交 (`3ff72a9a`) 下，通过 CDP 连接真实认证会话运行 `node verify_live_authenticated.mjs`，执行结果：**23 PASSED, 0 FAILED, 1 SKIPPED** (退出码 `0`)。

| ID | 模块 | 断言内容 | 状态 | 运行时动态验证细节 |
| :--- | :--- | :--- | :--- | :--- |
| **A1.1** | Overview | 账户容量脉冲与 API 动态一致 | **PASS** | 动态核对 `容量占用: 2 / 3` 与 `account_capacity.active_ticket_count / max` |
| **A1.2** | Overview | 在管交易卡片数等于真实已加载活动 Ticket 数 | **PASS** | 界面渲染 `2` 笔在管卡片，与接口未终结 Ticket 列表 `2` 项严格相等 |
| **A1.3** | Overview | 未加载在管 Ticket 分页截断提示真实性 | **SKIP** | 当前在管 2 笔均已加载，首屏无需截断提示 |
| **A1.4** | Overview | 今日净收益卡片与 API 动态一致 | **PASS** | 动态核对 `-2.35 USDT` 与 `today_net_pnl` 字段值 |
| **A1.5** | Overview | 今日累计 R 卡片与 API 动态一致 | **PASS** | 动态核对 `-0.31 R` 与 `today_net_r` 字段值 |
| **A2.1** | Causality | 点击“查看交易因果”成功唤起抽屉 | **PASS** | 抽屉容器可见性校验通过 (`role="dialog"`) |
| **A2.2** | Causality | 交易因果抽屉渲染 8 阶段完整时间线 | **PASS** | 时间线容器包含“8 阶段时间线” |
| **A2.3** | Causality | 交易因果抽屉绑定至准确的 Ticket ID | **PASS** | 抽屉渲染 `ticket:1726bf876bb575b70d0a9b9edeba40f7`，与点击项一致 |
| **A2.4** | Causality | 交易因果抽屉可正常安全关闭 | **PASS** | 点击关闭后抽屉 DOM 状态正常隐藏 |
| **A3.1** | Controls | 控制中心加载并渲染策略控制矩阵 | **PASS** | 成功渲染策略独立控制矩阵表格 |
| **A3.2** | Controls | 矩阵中所有策略控制版本与 API 一致 | **PASS** | 7 个策略组均精准渲染 `控制: v${control_version}` |
| **A3.3** | Controls | 零主观臆测：杜绝无证据声称“观察 Worker 运行正常” | **PASS** | 全局文本核查确认“观察 Worker 运行正常”彻底绝迹 |
| **A3.4** | Controls | 启用策略诚实展示“控制已启用 · 实际准入状态待核实” | **PASS** | 成功展示待核实状态，来源为 `client_derived` |
| **A3.5** | Controls | 矩阵在管持仓占用真实反映 API Ticket 标的与方向 | **PASS** | 真实渲染 `LONG TRXUSDT 止盈`, `LONG BCHUSDT 保护`，无伪造 ID |
| **A4.1** | Selection | Generic 选币 (CPM-RO-001) 报告 4h 周期 (非 24h) | **PASS** | 标明 `4h 周期`，与 Generic 契约一致 |
| **A4.2** | Selection | Generic 权威状态与 API 动态一致 | **PASS** | 动态展示 `PRE_FENCE_CONTINUITY` |
| **A4.3** | Selection | 标的明细与底层诊断抽屉成功打开 | **PASS** | 诊断抽屉可见性校验通过 |
| **A4.4** | Selection | Generic 选币诚实声明候选池与归因未提供 | **PASS** | 显式呈现“接口未提供候选名单与过滤仲裁流水” |
| **A4.5** | Selection | Generic 成员标的列表与 API 动态一致 | **PASS** | 16 个在役成员标的符号全部在抽屉中核对一致 |
| **A4.6** | Selection | SOR-1H 选币严格强制 24h 日周期 | **PASS** | 标明 `24h 周期`，不冒充 1h |
| **A4.7** | Selection | SOR-1H 入选成员数与快照动态一致 | **PASS** | 动态展示 `7 入选`，与快照 `selected_count: 7` 一致 |
| **A4.8** | Selection | SOR-1H 候选池总数与快照动态一致 | **PASS** | 动态展示 `候选总数 24`，与快照 `candidate_count: 24` 一致 |
| **A5.1** | Stability | 10 秒静止期业务 API 请求数绝对为 0 | **PASS** | 实际发起额外业务 API 请求数：**0** |
| **A5.2** | Stability | 全程无未处理浏览器 Console Error | **PASS** | 控制台异常记录数：**0** |

---

## 四、单元回归测试改写内容与覆盖情况

运行命令：`node --experimental-strip-types test_defect_regressions.mjs`
执行结果：**25 Passed, 0 Failed (100% 通过)**。

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
  ✓ PASS: Logout: Refresh guard blocks isAuthenticated when unconfirmed flag is set in storage
  ✓ PASS: Logout: Cache clearing prevents leaking cached data on unconfirmed logout

--- Test Group 8: Ticket Mapping & Unloaded Active Count ---
  ✓ PASS: computeUnloadedActiveCount calculates unloaded tickets without negative numbers
  ✓ PASS: formatTicketOccupationBadge derives real badges without fabricating fake ticket IDs

================================================================
Defect Regression Summary: 25 Passed, 0 Failed
================================================================
```

---

## 五、当前仍存在的客观限制

1. **后端未提供 Worker 独立心跳诊断字段**:
   当前 `/api/owner/v1/controls` 接口包含策略控制与权威围栏，但没有 Observation / Admission Worker 守护进程的健康探测返回值。因此前端准入健康状态严格如实显示为“**控制已启用 · 实际准入状态待核实** (`client_derived`)”，不主动捏造“畅通”或“运行正常”。若后续后端增加该诊断事实，前端映射函数已预留直接接入 `workerHealth` 的能力。
2. **Generic 选币未提供全量候选仲裁流水**:
   Generic Selection 接口目前仅提供 `members` 配置与状态事实，未下发未入选标的及排名仲裁依据。前端诊断抽屉明确标注“**接口未提供候选名单与过滤仲裁流水**”，完全符合真实数据契约。
3. **只读安全红线保持**:
   当前阶段继续严格执行只读验收，所有交易写控制（暂停/恢复策略、平仓、修改选币）继续保持只读锁定状态，不向生产后端发送变更高危指令。
