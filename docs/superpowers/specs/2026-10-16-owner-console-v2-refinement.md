# BRC Owner Console 2.0 — Controls 精修与 Dark / Light 双主题交付报告

> **环境与定位**：独立工程 `frontend/owner-console-v2` · 纯净 Mock 协议隔离  
> **交付阶段**：第一阶段第二轮（Controls 精修 + 语义化双主题架构）  
> **设计基准**：Modern Fintech × Tokyo Trading Kernel · 专业金融科技控制台  

---

## 一、双主题设计系统架构 (Theme Architecture)

按照要求，系统没有采用简单的“颜色反转”，而是在底层建立了一套共享的**语义化 Design Token**。无论是 Dark 还是 Light，组件均共享同一套 DOM 结构和语义 Class（例如 `bg-surface`, `bg-background`, `border-border`, `text-text-primary`, `text-text-secondary`, `text-status-green`, `text-status-red` 等）。

### 1. 语义 Token 对照表

| 语义 Token 标识 | Dark Theme 映射值 (Tokyo Kernel) | Light Theme 映射值 (Fintech Console) | 语义用途与视觉说明 |
| :--- | :--- | :--- | :--- |
| `--color-background` | `#080A0D` (深色画布底) | `#F1F4F8` (柔和冷灰蓝底) | 全站底色，Light 模式避免纯白刺眼铺满 |
| `--color-surface` | `#0F1318` (卡片表面 1 级) | `#FFFFFF` (纯白卡片表面) | 主要卡片、控制板背景 |
| `--color-surface-subtle` | `#121820` (微底表面 2 级) | `#F8FAFC` (极浅灰表面) | 表头、输入框背景、次级状态标签底 |
| `--color-surface-elevated` | `#151B22` (浮层表面 3 级) | `#FFFFFF` (高对比浮层) | 模态弹窗、侧滑抽屉、下拉悬停状态 |
| `--color-border` | `#222933` (微弱线) | `#E2E8F0` (清晰边框) | 标准组件、卡片与表格分割线 |
| `--color-border-strong` | `#2D3745` (结构线) | `#CBD5E1` (强化轮廓) | 输入框、按钮未聚焦轮廓线 |
| `--color-text-primary` | `#F0F6FC` (高亮正文) | `#0F172A` (深板岩黑) | 策略名称、关键指标、大标题、主数据 |
| `--color-text-secondary` | `#94A3B8` (副文字) | `#475569` (深灰次级字) | 状态解释、操作副标题，保证清晰可读 |
| `--color-text-muted` | `#64748B` (注释弱文字) | `#64748B` (弱灰文字) | 倒计时标签、次要指标标签 |
| `--color-text-disabled` | `#475569` (禁用文字) | `#94A3B8` (浅灰禁用) | 按钮禁用状态、未激活占位符 |
| `--color-accent` | `#F59E0B` (东京琥珀金) | `#D97706` (深琥珀金) | 品牌重点指示、激活 Tab、当前焦点 |
| `--color-success` | `#10B981` (明亮翠绿) | `#059669` (深稳翡翠绿) | 允许开仓、运行正常、合格入围 |
| `--color-warning` | `#F59E0B` (预警琥珀) | `#D97706` (深琥珀) | 准入阻断、容量满额、Static 模式 |
| `--color-danger` | `#EF4444` (警报亮红) | `#DC2626` (警戒深红) | 受控平仓、高危动作、空头亏损 |

### 2. 状态双向防眩目校准

- **受控平仓高危区 (Controlled Flatten)**：
  - **Dark**：`border-status-red/50 bg-surface text-status-red`，深色底下的警示红线与柔和背景。
  - **Light**：避免了纯红大色块对视网膜的刺激；采用 `#DC2626` 轮廓配合柔和背景，危险平仓按钮采用明确的高优先级红色实底，Disabled 状态灰度对比鲜明。
- **Theme Switcher**：
  - 入口置于 Header 右侧，采用 Sun / Moon 微型切换图标；
  - 自动读取系统 `prefers-color-scheme`，持久化至 `localStorage`；
  - 切换纯粹驱动 `html.dark` 与 `html.light` class，**零 DOM 抖动、零布局偏移**。

---

## 二、精修要点实施对照

### 1. 策略矩阵 (Strategy Matrix)
- **从 6 列精简为 5 列**：移除了独立的「版本 / 变更」列。
- **版本下沉为副标题**：版本与变更说明作为策略名下方的二级信息（如：`均线回踩做多 · v1 (系统初始化启用)`），不再白白侵占横向空间。
- **准入诊断横向空间拓展**：诊断列宽度从 20% 扩展至 32% 以上，中文字句如 `准入阻断 · 同向多头容量已达上限 (2/2)` 舒展排布，绝不折行拥挤。
- **字体与行高放大**：表头升级至 `text-xs font-semibold`，策略组名称升级至 `text-sm font-bold`，状态与诊断采用 `text-xs font-medium`，阅读体验大幅提升。

### 2. Selection 首屏与高密指挥台
- **移除首屏 24 标的冗余徽章**：主界面彻底摆脱“24 个徽章铺满屏幕”的杂乱感。
- **首屏单行高密指挥台**：
  ```text
  [ DYNAMIC (4h) ] · 🛡️ 权威有效 · 承接上一周期连续性 · 16 入围 / 8 过滤 · 年龄: 2h 前  |  [回退 Static]  [刷新]  [标的明细与诊断 ↗]
  ```
- **1440px 桌面完全首屏化**：在标准 1440x960 视口下，全局 ENTRY、策略矩阵 6 策略、Selection 治理区、受控平仓、容量条与审计历史**全部在首屏尽收眼底，无需滚动任何像素**。

### 3. Selection Drawer 底层工程诊断
- **时间语义彻底清晰**：
  - 之前：`有效期截止 (Stale Deadline) 14:08:21`（含义模糊）
  - 现在：`有效期截止 (Stale Deadline) 10/16 14:08 UTC (剩余 02:43:18)`（绝对 UTC 时间 + 精确倒计时并存）
- **标的池全量仲裁明细**：24 个全量 Universe 标的、入围状态、未入选的具体门禁拦截原因（如：`成交量门禁不足`、`未达动量阈值` 等）整齐归入抽屉第四部分。

### 4. 受控平仓二次防呆弹窗 (Controlled Flatten Modal)
- **文案消除后端技术字段**：将内部诊断代码统一重构为 Owner 业务语言：`生命周期保护中`。
- **防呆闭环保留**：
  1. 服务端冻结持仓清单（品种、方向、保护阶段、浮动损益 R）；
  2. 生命周期有序退出约束说明；
  3. Google Authenticator 6 位动态验证码校验；
  4. 精确文字签名确认（必须准确键入 `"确认平仓全部持仓"`）；
  5. 提交前按钮严密 Disabled，防止手误。

### 5. Header 导航净化
- 移除 `Policy v28`（下沉至组合容量区块显示，主导航专注产品级路由）。
- 保留 `MOCK PROTOCOL · 离线原型数据` 标识与脉冲指示灯。

---

## 三、6 张 1440px 桌面真实渲染截图清单

- `frontend/owner-console-v2/screenshots/screenshot_1_controls_dark_default.png` (Dark / Controls 默认页面)
- `frontend/owner-console-v2/screenshots/screenshot_2_controls_light_default.png` (Light / Controls 默认页面)
- `frontend/owner-console-v2/screenshots/screenshot_3_selection_drawer_dark.png` (Dark / Selection Drawer)
- `frontend/owner-console-v2/screenshots/screenshot_4_selection_drawer_light.png` (Light / Selection Drawer)
- `frontend/owner-console-v2/screenshots/screenshot_5_flatten_modal_dark.png` (Dark / Flatten Modal)
- `frontend/owner-console-v2/screenshots/screenshot_6_flatten_modal_light.png` (Light / Flatten Modal)
