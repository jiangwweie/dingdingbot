# BRC Owner Console 2.0 · 控制中心首轮视觉与原型交付报告

> 归档时间：2026-10-16  
> 对应工程：`frontend/owner-console-v2/`  
> 关联截图：`frontend/owner-console-v2/screenshots/`

---

## 一、 交付概述

本轮交付已按 Owner 要求停止纯文字方案编写，完成全新独立前端工程的搭建，并以「控制中心（Controls）」作为首个样板页面完成 1440px 桌面视口的高保真实现与真实浏览器渲染截图捕获。

工程采用 **Modern Fintech × Trading System** 设计语言，彻底剔除了传统运维后台的数据库粗糙感与 AI 模板的浮夸装饰，严格遵循五层正交控制模型与不可逆防御交互。

---

## 二、 核心截图归档 (1440px 视口)

1. **Controls 默认完整页面**：
   - 路径：`frontend/owner-console-v2/screenshots/screenshot_1_controls_default.png`
   - 说明：顶层态势条、策略独立启停矩阵（区分配置与实际准入事实）、动态选币治理面板、精简容量看板、紧急熔断入口。

2. **动态选币治理与底层工程诊断抽屉 (Selection Drawer)**：
   - 路径：`frontend/owner-console-v2/screenshots/screenshot_2_selection_drawer.png`
   - 说明：将 `PRE_FENCE_CONTINUITY`、Vacuum、快照截断年龄、24 个标的仲裁事实收拢至右侧 576px 抽屉，不再污染主屏。

3. **受控平仓两阶段确认弹窗 (Controlled Flatten Modal)**：
   - 路径：`frontend/owner-console-v2/screenshots/screenshot_3_flatten_modal.png`
   - 说明：服务端冻结范围实时预览、6 位 Google Authenticator TOTP 校验、精确文本输入确认。

---

## 三、 本地运行指南

```bash
cd frontend/owner-console-v2

# 安装依赖 (已通过 pnpm 完成)
pnpm install

# 启动开发服务器 (默认 5174 端口)
pnpm dev

# 构建与生产预览验证
pnpm build
pnpm preview --port 5174 --host 127.0.0.1
```

---

## 四、 待核实业务字段清单 (For Codex / Owner 确认)

1. **策略实时准入阻断事实聚合**：
   - 当前 `GET /api/owner/v1/controls` 仅包含策略配置状态，细分第一阻断原因分布在 selection 接口。待确认是由前端聚合还是后端在控制响应中提供直接字段。
2. **受控平仓服务端工作流原子性**：
   - 确认平仓提交后，“暂停全局 ENTRY”与“向 Lifecycle 发出退出指令”在服务端的事务保障顺序。
3. **SOR-1H-001 独立选币参数**：
   - SOR-1H-001 采用独立 ORB 选币接口（参数为 `effective_session_start_ms`），新前端已完成独立建模。
