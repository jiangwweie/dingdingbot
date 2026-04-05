# 配置重构测试补全任务规划

> **规划版本**: v1.0  
> **执行工具**: Puppeteer (E2E) + React Testing Library (单元测试)  
> **排除范围**: 并发测试、性能测试  

---

## 📋 任务总览

| 类别 | 任务数 | 预计总工时 | 优先级 |
|------|--------|-----------|--------|
| 前端单元测试 | 3 | 6h | P0 |
| 前端 E2E 测试 | 3 | 8h | P0 |
| 后端 API 边界测试 | 2 | 4h | P1 |
| 集成测试补充 | 2 | 4h | P1 |
| **总计** | **10** | **22h** | - |

---

## 🔴 P0 - 前端单元测试（3 个任务）

### TASK-F1: StrategiesTab 单元测试
**描述**: 策略管理 Tab 组件测试
**文件**: `web-front/src/pages/config/__tests__/StrategiesTab.test.tsx`
**Agent**: /frontend
**工时**: 2h
**覆盖场景**:
- [ ] 策略列表加载/刷新
- [ ] 策略启用/禁用切换
- [ ] 策略删除确认对话框
- [ ] 空状态展示
- [ ] 错误状态处理
**依赖**: 无
**并行**: 可与 F2、F3 并行

---

### TASK-F2: AdvancedStrategyForm 单元测试
**描述**: 高级策略表单组件测试
**文件**: `web-front/src/pages/config/__tests__/AdvancedStrategyForm.test.tsx`
**Agent**: /frontend
**工时**: 2h
**覆盖场景**:
- [ ] 触发器添加/删除
- [ ] 过滤器链配置
- [ ] 表单验证（必填项、数值范围）
- [ ] 动态字段渲染
- [ ] 提交成功/失败处理
**依赖**: 无
**并行**: 可与 F1、F3 并行

---

### TASK-F3: SystemTab 单元测试
**描述**: 系统配置 Tab 组件测试
**文件**: `web-front/src/pages/config/__tests__/SystemTab.test.tsx`
**Agent**: /frontend
**工时**: 2h
**覆盖场景**:
- [ ] 配置表单渲染
- [ ] 参数修改保存
- [ ] 重启提示显示
- [ ] 表单验证
- [ ] 恢复默认值
**依赖**: 无
**并行**: 可与 F1、F2 并行

---

## 🟠 P0 - 前端 E2E 测试（3 个任务）

### TASK-E1: Puppeteer 环境搭建
**描述**: 配置 Puppeteer 测试框架和基础工具
**文件**:
- `web-front/e2e/puppeteer.config.js`
- `web-front/e2e/utils/setup.ts`
- `web-front/e2e/utils/helpers.ts`
**Agent**: /frontend
**工时**: 2h
**交付物**:
- [ ] Puppeteer 配置文件
- [ ] 测试辅助工具（登录、清理、截图）
- [ ] Jest/Puppeteer 集成配置
- [ ] 测试数据工厂（mock 配置数据）
**依赖**: 无
**阻塞**: E2、E3

---

### TASK-E2: 策略管理 E2E 测试
**描述**: 策略管理全流程端到端测试
**文件**: `web-front/e2e/config/strategies.e2e.test.ts`
**Agent**: /qa
**工时**: 3h
**覆盖场景**:
- [ ] 登录 → 进入配置页面 → 切换到策略 Tab
- [ ] 创建新策略（填写表单、提交）
- [ ] 启用/禁用策略
- [ ] 编辑策略参数
- [ ] 删除策略（确认流程）
- [ ] 策略搜索/筛选
- [ ] 表单验证错误提示
**依赖**: E1
**并行**: 可与 E3 并行

---

### TASK-E3: 导入导出 E2E 测试
**描述**: 配置导入导出功能端到端测试
**文件**: `web-front/e2e/config/backup.e2e.test.ts`
**Agent**: /qa
**工时**: 3h
**覆盖场景**:
- [ ] 登录 → 进入备份恢复页面
- [ ] 导出配置（下载 YAML 文件）
- [ ] 导入配置预览（上传 YAML → 显示预览）
- [ ] 导入确认（应用到系统）
- [ ] 导入冲突处理
- [ ] 无效 YAML 文件错误提示
- [ ] 大文件导入（边界测试）
**依赖**: E1
**并行**: 可与 E2 并行

---

## 🟡 P1 - 后端 API 边界测试（2 个任务）

### TASK-B1: 权限检查 API 边界测试
**描述**: 401/403 场景补充测试
**文件**: `tests/unit/test_api_v1_config_permissions.py`
**Agent**: /backend
**工时**: 2h
**覆盖场景**:
- [ ] 未登录访问受保护端点 → 401
- [ ] 普通用户访问管理员端点 → 403
- [ ] Token 过期处理
- [ ] 无效 Token 处理
- [ ] 权限变更后会话处理
**依赖**: 无
**并行**: 可与 B2 并行

---

### TASK-B2: 风控配置边界值测试
**描述**: 极端数值场景测试
**文件**: `tests/unit/test_risk_config_boundary.py`
**Agent**: /backend
**工时**: 2h
**覆盖场景**:
- [ ] 数值为 0 的处理
- [ ] 负数值处理（是否拒绝）
- [ ] 极大值处理（> Decimal MAX）
- [ ] 小数精度测试
- [ ] 字符串注入测试
**依赖**: 无
**并行**: 可与 B1 并行

---

## 🟢 P1 - 集成测试补充（2 个任务）

### TASK-I1: 热重载功能测试
**描述**: 配置变更后系统热重载测试
**文件**: `tests/integration/test_config_hot_reload.py`
**Agent**: /backend
**工时**: 2h
**覆盖场景**:
- [ ] 配置修改后触发 reload
- [ ] 热重载后配置生效验证
- [ ] 热重载失败回滚
- [ ] 热重载期间请求处理
**依赖**: 无
**并行**: 可与 I2 并行

---

### TASK-I2: 配置历史记录测试
**描述**: 配置变更历史追踪功能测试
**文件**: `tests/integration/test_config_history.py`
**Agent**: /backend
**工时**: 2h
**覆盖场景**:
- [ ] 配置修改记录创建
- [ ] 历史记录查询（分页、筛选）
- [ ] 历史记录详情查看
- [ ] 回滚到指定版本
- [ ] 历史记录清理
**依赖**: 无
**并行**: 可与 I1 并行

---

## 🔄 任务依赖图

```
Phase 1: 基础搭建 (并行)
├── F1 (前端单元) ──┐
├── F2 (前端单元) ──┼──→ 单元测试完成
├── F3 (前端单元) ──┘
└── E1 (Puppeteer 环境) ──→ 阻塞 Phase 2

Phase 2: E2E 执行 (并行)
├── E2 (策略管理 E2E) ──┐
└── E3 (导入导出 E2E) ──┴──→ E2E 完成

Phase 3: 后端补充 (并行)
├── B1 (权限边界) ──┐
├── B2 (风控边界) ──┼──→ API 测试完成
├── I1 (热重载) ────┤
└── I2 (历史记录) ──┘
```

---

## 👥 Agent 分配方案

| Agent | 负责任务 | 工时 | 说明 |
|-------|----------|------|------|
| /frontend | F1, F2, F3, E1 | 8h | 前端单元测试 + Puppeteer 环境 |
| /qa | E2, E3 | 6h | E2E 测试执行 |
| /backend | B1, B2, I1, I2 | 8h | 后端边界测试 + 集成测试 |
| /reviewer | 全部 | 4h | 代码审查（与开发并行） |

---

## 📅 执行计划（推荐）

### Day 1 (8h)
- **上午**: F1, F2, F3 并行（前端单元测试）
- **下午**: E1（Puppeteer 环境搭建）

### Day 2 (8h)
- **上午**: E2, E3 并行（E2E 测试）
- **下午**: B1, B2 并行（后端 API 边界）

### Day 3 (6h)
- **上午**: I1, I2 并行（集成测试）
- **下午**: 代码审查 + 回归测试

---

## ✅ 验收标准

| 任务 | 验收标准 |
|------|----------|
| F1-F3 | 单元测试覆盖率 ≥ 80%，测试通过 |
| E1 | `npm run test:e2e` 命令可正常执行 |
| E2-E3 | 所有 E2E 场景通过，无 flaky 测试 |
| B1-B2 | API 边界测试通过，覆盖所有错误码 |
| I1-I2 | 集成测试通过，数据库状态正确 |

---

## 📊 预期产出

```
web-front/
├── src/pages/config/__tests__/
│   ├── StrategiesTab.test.tsx          [NEW]
│   ├── AdvancedStrategyForm.test.tsx   [NEW]
│   └── SystemTab.test.tsx              [NEW]
└── e2e/
    ├── puppeteer.config.js             [NEW]
    ├── utils/
    │   ├── setup.ts                    [NEW]
    │   └── helpers.ts                  [NEW]
    └── config/
        ├── strategies.e2e.test.ts      [NEW]
        └── backup.e2e.test.ts          [NEW]

tests/
├── unit/
│   ├── test_api_v1_config_permissions.py    [NEW]
│   └── test_risk_config_boundary.py         [NEW]
└── integration/
    ├── test_config_hot_reload.py            [NEW]
    └── test_config_history.py               [NEW]
```

---

## ⚠️ 风险说明

1. **Puppeteer 环境**: 需要 Chromium 下载，可能影响 CI/CD
2. **E2E 测试稳定性**: 需要处理异步加载、动画等不稳定因素
3. **后端 API 变更**: 如果 API 有未合并的变更，可能需要调整

---

**请确认后，我将启动 Team Agent 并行执行这些任务。**
