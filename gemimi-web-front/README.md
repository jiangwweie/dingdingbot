# 交易控制台 (Trading Console / Read-only)

这是一个面向 Sim-1 交易观察和策略研究评审的内部控制台 (Internal Dashboard)。

## 设计约束与系统行为
- **仅限只读 (Read-only interface)**: 无配置编辑，无环境重置或候选策略手动提升的操作。只用于观察、诊断和分析。
- **纯 Mock 数据层 (Mock Data Layer)**: 页面逻辑完全脱离后端依赖，使用内置 `mockApi` 生成模拟数据。
- **无 Websockets / 强制手动刷新 (No Websockets)**: 避免在单页面驻留产生性能瓶颈。控制台外层框架提供了统一的 "Manual Refresh" 拦截器。
- **环境健康状态检测展示**: 运行时页面（尤其是概览和健康度）的数据表现会随着每次手动刷新主动轮转展示 (`正常` -> `延迟` -> `疑似宕机`)，用于展示界面的容错兜底效果。
- **极简工程美学 (Restrained Styling)**: 大量运用高密度信息布局、等宽字体 (Monospace) 及强对比展示，服务于运维和量化分析的数据扫视需求，拒绝浮夸花哨。

## 领域划分 (Domain Separation)

在侧边导航清晰地划分了两个主要领域：

### 1. 运行环境 (Runtime)
负责追踪交易算法引擎的运行状态：
- **系统概览 (Overview)**: 系统组件心跳检测，基础配置确认。
- **交易信号 (Signals)**: 拦截机制日志和最终生成的开平仓意图。
- **执行情况 (Execution)**: 发送到交易所侧的订单和成交明细。
- **系统健康度 (Health)**: 严格拆分熔断器摘要 (Breaker) 和 恢复进程 (Recovery)。

### 2. 策略研究 (Research)
负责历史策略参数评估和 Optuna 实验集产物审查：
- **候选策略 (Candidates)**: 通过 Optuna 生成的参数评审池。
- **候选详情 (Candidate Detail)**: 解析单一实验集产物中的顶级策略组合。
- **回测上下文 (Replay Context)**: 本地策略复现指令集与参数。
- **回测记录 (Backtests)**: 大规模回测执行生成的历史度量追踪。
- **策略对比 (Compare)**: 横向对比多策略的实验表现及超越基准的能力。

## 本地开发指南

```bash
# 1. 安装依赖包
npm install

# 2. 启动 Vite 开发服务器 (默认为只读控制台模式)
npm run dev
```

该系统依赖 TailwindCSS `v4` 和 `lucide-react`。开发阶段可修改 `/src/services/mockApi.ts` 来动态调整展示的数据效果。后期在移除 Mock 环境，接入真实 API 时，只需改变该文件的 Provider 实现即可。
