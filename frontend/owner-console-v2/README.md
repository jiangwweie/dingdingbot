# BRC Owner Console 2.0 · 控制中心首轮视觉与原型交付报告

> **工程定位**：全新独立前端工程 `frontend/owner-console-v2`，采用 **Modern Fintech × Trading System** 设计语言，彻底摆脱传统数据库后台感与 AI 模板化外壳，以 100% 独立代码实现「控制中心（Controls）」首个样板页面。

---

## 一、 真实浏览器渲染截图 (1440px 视口)

截图文件保存在工程目录：`./screenshots/`

### 1. 控制中心默认完整页面 (Controls Default View)
文件路径：`./screenshots/screenshot_1_controls_default.png`

- **核心特点**：
  - 顶层态势条：明确区分 **全局 ENTRY 开关（允许新开仓）** 与存量持仓保护；
  - 策略矩阵：严格区分 **“配置状态”** 与 **“实际准入状态”**（CPM-RO-001 明确标出 `⚠ 准入阻断 · 同向多头容量已达上限 (2/2)`，避免误判为正常）；在管持仓直接以 `LONG TRXUSDT -0.32 R` 业务标签展示，摒弃生硬的 UUID 乱码；
  - 选币治理：Dynamic 4h 轮动、Authority 有效性、回退至 Static 基线按钮与刷新按钮清晰外露；
  - 精简容量：将过去占半屏的 14 行文本重构为紧凑进度条，仅高亮活动占用（CPM Long 2 笔，BRF2 Short 1 笔）。

---

### 2. 动态选币治理与底层工程诊断抽屉 (Selection Drawer)
文件路径：`./screenshots/screenshot_2_selection_drawer.png`

- **核心特点**：
  - 点击「底层工程诊断 (Drawer)」从右侧滑出 576px 抽屉；
  - 将 `PRE_FENCE_CONTINUITY`、`Snapshot 完成年龄 (6186s)`、`Materialization: DESIRED`、`Vacuum` 等工程排障指标收拢在抽屉内；
  - 标的池 24 个成员全量仲裁明细在抽屉中分类审计，不再污染主屏。

---

### 3. 高危操作：受控平仓两阶段确认弹窗 (Controlled Flatten Modal)
文件路径：`./screenshots/screenshot_3_flatten_modal.png`

- **核心特点**：
  - 严格遵守两阶段提交防手误机制；
  - 服务端冻结清单实时预览：显示 UNIUSDT (+1.24R)、TRXUSDT (-0.32R)、BCHUSDT (+0.88R)；
  - 强校验：必须输入 6 位数字 Google Authenticator TOTP，且必须输入精确文本 `确认平仓全部持仓` 才能解锁红色高危按钮；
  - 模拟异步提交过程与成功反馈。

---

## 二、 新前端工程结构与运行方式

项目位于仓库独立目录：`frontend/owner-console-v2/`

```text
frontend/owner-console-v2/
├── package.json               # 独立依赖定义 (React 19, Tailwind 3.4, Radix Primitives)
├── vite.config.ts             # 独立 Vite 8 构建配置 (端口 5174)
├── tailwind.config.js         # 专业金融深色主题扩展 (canvas, surface-1/2/3, border-base)
├── screenshots/               # 真实 1440px 截图归档
│   ├── screenshot_1_controls_default.png
│   ├── screenshot_2_selection_drawer.png
│   └── screenshot_3_flatten_modal.png
├── src/
│   ├── types/controls.ts      # 严格对应业务事实的 TypeScript 接口定义
│   ├── mock/controlsData.ts   # 集中管理的 Mock 数据 (明确标注 MOCK PROTOCOL)
│   ├── components/
│   │   ├── Navbar.tsx         # 沉稳克制的顶部导航栏
│   │   ├── TopStatusBar.tsx   # 全局 ENTRY 与系统态势条
│   │   ├── StrategyMatrix.tsx # 策略启停与准入阻断矩阵
│   │   ├── SelectionSection.tsx # 动态选币治理与 Static 回退操作面板
│   │   ├── SelectionDrawer.tsx  # 底层工程证据与 24 标的抽屉
│   │   ├── DangerZoneCard.tsx   # 紧急熔断控制入口
│   │   ├── ControlledFlattenModal.tsx # 受控平仓防手误双校验弹窗
│   │   ├── TotpActionModal.tsx  # 策略/全局恢复专用的 TOTP 弹窗
│   │   ├── CapacitySection.tsx  # 精简的组合容量进度看板
│   │   └── RecentOperations.tsx # 最近 3 笔控制操作审计流水
│   ├── App.tsx                # 主页面装配与全闭环 Mock 交互状态
│   └── index.css              # 等宽数字与极简深色滚动条样式
└── capture_screenshots.mjs    # 自动化浏览器高保真截图脚本
```

### 本地启动指令
```bash
# 进入新工程目录
cd frontend/owner-console-v2

# 开发模式运行 (默认端口 5174)
pnpm dev

# 或构建后预览
pnpm build
pnpm preview --port 5174 --host 127.0.0.1
```

---

## 三、 待核实与对接的业务字段清单 (For Codex / Owner 确认)

为确保下一步真实 API 接入时不出现前端自作主张的偏差，以下字段与行为需要结合后端代码做最后事实核验：

1. **各策略的即时准入阻断诊断来源**：
   - *现状*：当前 `GET /api/owner/v1/controls` 的 `StrategyControlView` 仅返回 `configured_state`、`effective_state` 和 `reason`，各策略的最新 `first_blocker` 分布在 `GET .../selection` 中。
   - *待确认*：后续是由前端通过 React Query 并发聚合展示，还是在后端 `ControlsResponse` 中为每个策略增加一个权威的 `primary_blocker` 摘要？
2. **受控平仓的服务端事务原子性**：
   - *待确认*：`POST /api/owner/v1/controls/exposure/flatten-all` 提交后，“挂起全局 ENTRY”与“冻结当前活动 Ticket 并发送退出指令”是否由后端单一事务/工作流强制保证？
3. **SOR-1H-001 的选币接口差异**：
   - *现状*：代码中 generic 策略调用 `/selection/dynamic/activate`，而 SOR-1H-001 独立调用 `submitOrbDynamicIntent`（参数为 `effective_session_start_ms` 而非 `effective_period_anchor_ms`）。
   - *已对齐*：新版前端已对该差异进行了类型层面的独立建模。
