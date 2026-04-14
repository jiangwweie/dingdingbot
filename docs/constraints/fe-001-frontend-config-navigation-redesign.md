# FE-001 前端配置导航重构 - 架构设计文档

> **文档版本**: 1.0  
> **创建日期**: 2026-04-06  
> **架构师**: Claude (前端开发专家)  
> **状态**: 已批准  
> **相关 PRD**: `docs/products/frontend-config-optimization-prd.md`  
> **审查报告**: `docs/reviews/fe-001-frontend-design-review.md`

---

## 一、架构概述

### 1.1 设计目标

本次重构旨在解决以下问题:

| 问题 | 现状 | 目标 |
|------|------|------|
| **配置分散** | 用户需要访问 3 个不同页面才能完成完整配置 | 统一配置入口，清晰分类 |
| **分类不清** | 全局配置、策略配置、回测配置混在一起 | 按配置层级 (Level 1/2/3) 明确分离 |
| **信息架构复杂** | ConfigProfiles 一个页面有 4 个 Tab，内容深度不一致 | 独立页面，各司其职 |

### 1.2 核心原则

1. **配置分层** - 按影响范围和变更频率分类
2. **快速访问** - 常用配置 (Level 2) 放在容易访问的位置
3. **避免冗余** - 回测配置 (Level 3) 默认不保存，避免配置爆炸

---

## 二、路由设计

### 2.1 路由规划总表

| 路径 | 组件 | 说明 | 优先级 |
|------|------|------|--------|
| `/dashboard` | `Dashboard` | 仪表盘 (保持不变) | P0 |
| `/backtest` | `Backtest` | 回测沙箱 (优化) | P0 |
| `/config/strategies` | `StrategyConfig` (新建) | **策略配置页面** (新建独立页面) | P0 |
| `/strategies` | `StrategyWorkbench` (现有) | **策略工作台** (保留，用于策略模板管理) | P0 |
| `/config/system` | `SystemSettings` (新建) | 系统配置 (Level 1 全局配置) | P1 |
| `/config/profiles` | `ProfilesConfig` (迁移) | Profile 管理 (从 ConfigProfiles 迁移) | P0 |
| `/config/backup` | `BackupConfig` (迁移) | 备份恢复 (从 ConfigProfiles 迁移) | P0 |

### 2.2 路由冲突解决方案

**问题**: `/strategies` 已被 `StrategyWorkbench` 占用

**解决方案**: 
- 新策略配置页面使用 `/config/strategies` 前缀
- 保留 `/strategies` 给策略工作台 (策略模板管理/CRUD)
- 添加路由重定向 (可选): `/profiles/strategies` → `/config/strategies`

**边界说明**:
| 页面 | 用途 | 配置类型 |
|------|------|----------|
| `/config/strategies` | 配置策略参数 (触发器/过滤器/风控) | Level 2 - 策略级配置 |
| `/strategies` | 策略模板管理 (保存/加载/切换) | 策略模板操作 |

### 2.3 导航结构

**新导航结构**:
```
主导航 (Layout.tsx)
├── 📊 监控中心         → /dashboard
├── 🧪 回测沙箱         → /backtest
├── ⚙️ 策略配置         → /config/strategies    [新建]
└── 🔧 系统设置 (下拉)
    ├── Profile 管理    → /config/profiles      [迁移]
    └── 备份恢复        → /config/backup        [迁移]
```

---

## 三、组件架构

### 3.1 组件树拆分图

#### 3.1.1 策略配置页面 (`/config/strategies`)

```
StrategyConfigPage (新建)
├── PageHeader
│   ├── PageTitle ("策略配置")
│   └── GlobalActions
│       └── CreateStrategyButton
│
├── StrategyListSection
│   ├── SearchBar (搜索/筛选)
│   ├── StrategyCardList
│   │   └── StrategyCard (重复)
│   │       ├── StrategyName
│   │       ├── StrategyDescription
│   │       ├── EnableToggle (Switch)
│   │       ├── EditButton
│   │       └── DeleteButton
│   └── Pagination
│
└── StrategyEditorDrawer (抽屉式编辑)
    ├── DrawerHeader
    │   ├── StrategyTitle
    │   └── CloseButton
    │
    ├── StrategyBasicInfoForm
    │   ├── StrategyNameInput
    │   ├── StrategyDescriptionInput
    │   └── ScopeSelector (币种 + 周期)
    │
    ├── TriggerParamsSection (Level 2)
    │   ├── PinbarParamsForm
    │   ├── EngulfingParamsForm
    │   └── ...
    │
    ├── FilterChainSection (Level 2)
    │   ├── EmaFilterForm
    │   ├── MtfFilterForm
    │   ├── AtrFilterForm
    │   └── AddFilterButton
    │
    ├── RiskParamsSection (Level 2)
    │   ├── MaxLossPercentInput
    │   └── MaxLeverageInput
    │
    └── DrawerFooter
        ├── SaveButton (带 Loading 状态)
        └── CancelButton
```

#### 3.1.2 系统设置页面 (`/config/system`)

```
SystemSettingsPage (新建)
├── PageHeader
│   └── PageTitle ("系统配置")
│
├── WarningBanner (红色背景)
│   └── "修改以下配置需要重启服务才能生效"
│
├── Level1ConfigSection (默认折叠)
│   ├── CollapseHeader ("全局系统配置 (高级)")
│   └── CollapseContent
│       ├── QueueBatchSizeInput
│       ├── QueueFlushIntervalInput
│       ├── QueueMaxSizeInput
│       ├── WarmupHistoryBarsInput
│       └── SignalCooldownSecondsInput
│
└── SystemActions
    └── RestartServiceButton (可选)
```

#### 3.1.3 回测沙箱页面 (`/backtest` - 优化现有)

```
BacktestPage (现有，优化)
├── PageHeader
│   └── PageTitle ("回测沙箱")
│
├── QuickConfigSection (Level 3 - 显眼区域)
│   ├── SymbolSelector (7 个选项)
│   ├── TimeframeSelector (7 个选项)
│   └── DateRangePicker (快速选择)
│
├── AdvancedConfigSection (折叠)
│   ├── CollapseHeader ("高级配置")
│   └── CollapseContent
│       ├── StrategyCombinationSelector
│       ├── RiskOverrideForm
│       ├── SlippageRateInput
│       ├── FeeRateInput
│       └── InitialBalanceInput
│
├── SavePresetButton (可选)
│
└── BacktestResultSection
    ├── RunBacktestButton
    └── ReportDisplay
        └── UsedConfigSnapshot (参数快照)
```

### 3.2 组件复用计划

| 现有组件 | 目标位置 | 复用方式 |
|----------|----------|----------|
| `StrategyParamPanel.tsx` | `/config/strategies` → `StrategyEditorDrawer` | 拆分复用 (移除模板管理逻辑) |
| `SystemTab.tsx` | `/config/system` → `Level1ConfigSection` | 直接迁移 |
| `QuickDateRangePicker.tsx` | `/backtest` → `QuickConfigSection` | 直接复用 |
| `StrategiesTab.tsx` | `/config/strategies` → `StrategyListSection` | 参考设计 |

---

## 四、状态管理设计

### 4.1 状态分类策略

| 状态类型 | 推荐方案 | 使用场景 | 理由 |
|----------|----------|----------|------|
| **服务端状态** | React Query (`useQuery`, `useMutation`) | 策略列表、策略详情、系统配置 | 需要缓存、后台刷新、乐观更新 |
| **表单状态** | React Hook Form (`useForm`) | 策略编辑表单、系统配置表单 | 频繁变更，无需立即同步 |
| **全局 UI 状态** | Zustand / Context | 当前 Profile、主题、抽屉打开状态 | 跨组件共享的 UI 状态 |

### 4.2 React Query 配置

```typescript
// web-front/src/lib/react-query-config.ts

// 策略列表查询
const strategiesQuery = {
  queryKey: ['strategies'],
  queryFn: fetchStrategies,
  staleTime: 5 * 60 * 1000, // 5 分钟
  refetchOnWindowFocus: true,
};

// 策略详情查询
const strategyDetailQuery = (id: string) => ({
  queryKey: ['strategies', id],
  queryFn: () => fetchStrategy(id),
  staleTime: 2 * 60 * 1000, // 2 分钟
});

// 策略更新 Mutation
const updateStrategyMutation = {
  mutationFn: updateStrategy,
  onSuccess: () => {
    // 失效策略列表缓存，触发重新获取
    queryClient.invalidateQueries(['strategies']);
  },
};
```

### 4.3 表单状态管理

```typescript
// web-front/src/components/strategy/StrategyEditor.tsx

import { useForm } from 'react-hook-form';

interface StrategyFormValues {
  name: string;
  description: string;
  symbol: string;
  timeframe: string;
  pinbar: {
    min_wick_ratio: number;
    max_body_ratio: number;
    body_position_tolerance: number;
  };
  ema: {
    period: number;
  };
  mtf: {
    enabled: boolean;
    ema_period: number;
  };
  atr: {
    enabled: boolean;
    period: number;
    min_atr_ratio: number;
  };
  max_loss_percent: number;
  max_leverage: number;
}

const {
  control,
  handleSubmit,
  formState: { isDirty, isSaving },
  watch,
} = useForm<StrategyFormValues>({
  defaultValues: {
    // 默认值从 API 获取
  },
});
```

### 4.4 实时保存机制

**防抖策略**:
```typescript
// 输入停止 1 秒后自动保存
const debouncedSave = useCallback(
  debounce((values: StrategyFormValues) => {
    updateMutation.mutate(values);
  }, 1000),
  [updateMutation]
);

// 监听表单变化
useEffect(() => {
  const subscription = watch((value) => {
    if (isDirty) {
      debouncedSave(value as StrategyFormValues);
    }
  });
  return () => subscription.unsubscribe();
}, [watch, isDirty, debouncedSave]);
```

---

## 五、交互设计

### 5.1 Level 1 配置折叠交互

**设计说明**:
- 默认状态：**折叠** (减少干扰)
- 折叠面板使用 Ant Design `Collapse` 组件
- 折叠状态持久化到 `localStorage`
- 提供红色警告 Banner："修改后需重启服务"

**交互流程**:
```
1. 用户进入系统配置页面
   ↓
2. 看到红色警告 Banner + 折叠面板 (默认关闭)
   ↓
3. 点击"全局系统配置 (高级)"展开
   ↓
4. 修改配置
   ↓
5. 保存后显示 Toast + 重启提示
```

### 5.2 策略编辑抽屉交互

**展开方式**: **抽屉式 (Drawer)** - 从右侧滑出

**理由**:
- 保持列表可见，支持快速切换策略
- 比模态框更轻量
- 比下方展开更节省空间

**交互流程**:
```
1. 用户点击策略卡片的"编辑"按钮
   ↓
2. 从右侧滑出抽屉，显示策略编辑器
   ↓
3. 修改表单字段 (实时保存)
   ↓
4. 点击关闭按钮或点击遮罩层关闭
   ↓
5. 返回列表视图
```

### 5.3 用户反馈状态设计

| 场景 | Loading 状态 | Error 状态 | Success 状态 |
|------|--------------|------------|--------------|
| **策略列表加载** | 骨架屏 (Skeleton) | 错误提示 + 重试按钮 | - |
| **策略保存** | 按钮 Loading 状态 + 禁用 | Toast 错误消息 | Toast 成功 + 未保存标记消失 |
| **策略切换** | - | Toast 错误 | Toast 成功 + 状态标签更新 |
| **系统配置保存** | 按钮 Loading 状态 + 禁用 | Toast 错误 + 详情 | Toast 成功 + 重启提示 Modal |
| **回测运行** | 进度条 + 运行中动画 | Toast 错误 + 错误代码 | 回测报告展示 |

---

## 六、API 集成策略

### 6.1 API 客户端封装

```typescript
// web-front/src/api/config.ts

import { request } from './request';

export interface Strategy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  symbol: string;
  timeframe: string;
  params: StrategyParams;
}

export interface StrategyParams {
  pinbar: {
    min_wick_ratio: number;
    max_body_ratio: number;
    body_position_tolerance: number;
  };
  ema: { period: number };
  mtf: { enabled: boolean; ema_period: number };
  atr: { enabled: boolean; period: number; min_atr_ratio: number };
  max_loss_percent: number;
  max_leverage: number;
}

// 策略管理 API
export const configApi = {
  // 获取策略列表
  getStrategies: () => request.get<Strategy[]>('/api/config/strategies'),
  
  // 创建策略
  createStrategy: (data: Partial<Strategy>) => 
    request.post<Strategy>('/api/config/strategies', data),
  
  // 更新策略
  updateStrategy: (id: string, data: Partial<Strategy>) => 
    request.put<Strategy>(`/api/config/strategies/${id}`, data),
  
  // 删除策略
  deleteStrategy: (id: string) => 
    request.delete(`/api/config/strategies/${id}`),
  
  // 获取策略参数
  getStrategyParams: () => request.get<StrategyParams>('/api/strategy/params'),
  
  // 更新策略参数 (热重载)
  updateStrategyParams: (params: Partial<StrategyParams>) => 
    request.put<StrategyParams>('/api/strategy/params', params),
  
  // 预览参数变更
  previewStrategyParams: (newConfig: Partial<StrategyParams>) => 
    request.post('/api/strategy/params/preview', { new_config: newConfig }),
  
  // 系统配置
  getSystemConfig: () => request.get('/api/config/system'),
  updateSystemConfig: (config: Record<string, any>) => 
    request.put('/api/config/system', config),
};
```

### 6.2 热重载集成

**配置变更通知流程**:
```
前端修改配置
    ↓
调用 PUT /api/strategy/params
    ↓
后端调用 ConfigManager.update_user_config()
    ↓
后端广播配置变更事件 (WebSocket)
    ↓
前端监听配置变更，更新本地缓存
```

---

## 七、技术实现细节

### 7.1 Tooltip 内容来源

**问题**: Tooltip 内容硬编码在前端，维护困难

**解决方案**: 后端在配置 Schema 中提供 tooltip 字段

```typescript
// 后端 Schema 响应
interface ConfigFieldSchema {
  key: string;
  type: 'number' | 'string' | 'boolean';
  default: any;
  min?: number;
  max?: number;
  tooltip: {
    description: string;
    default_value: string;
    range: string;
    adjustment_tips: string[];
  };
}

// 前端动态读取
const fetchConfigSchema = async () => {
  const response = await request.get('/api/config/schema');
  return response.data;
};
```

### 7.2 回测参数快照展示

**位置**: 回测报告展示区域底部

**展示内容**:
```
使用的配置参数:
├── 币种：BTC/USDT:USDT
├── 周期：15m
├── 时间范围：2026-01-01 ~ 2026-03-31
├── 策略：Pinbar + EMA + MTF
├── 滑点率：0.1%
├── 手续费率：0.04%
└── 初始资金：10000 USDT
```

### 7.3 路由迁移计划

**渐进式迁移**:
1. 新建 `/config/strategies` 页面
2. 保留旧路由 `/profiles/strategies` 重定向到新页面
3. 在旧页面添加迁移提示 Banner
4. 观察用户使用情况后移除旧路由

---

## 八、性能优化策略

### 8.1 列表渲染优化

**问题**: 策略数量 > 100 时列表渲染卡顿

**解决方案**:
- 使用虚拟滚动 (`react-window`)
- 或添加分页功能 (每页 20 条)

```typescript
// 使用 react-window 虚拟滚动
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={strategies.length}
  itemSize={100}
  width="100%"
>
  {({ index, style }) => (
    <StrategyCard key={strategies[index].id} strategy={strategies[index]} style={style} />
  )}
</FixedSizeList>
```

### 8.2 表单性能优化

- 使用 `React.memo` 缓存子组件
- 避免不必要的重渲染
- 大型表单拆分为多个小组件

---

## 九、验收标准

### 9.1 功能验收

| 验收项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| 导航结构优化 | 访问主导航菜单 | 策略配置为独立导航项 |
| 策略列表展示 | 访问 `/config/strategies` | 显示所有策略列表 |
| 启用/禁用切换 | 点击 Switch | 策略状态切换成功 |
| 策略编辑 | 点击编辑按钮 | 抽屉式编辑器展开 |
| 实时保存 | 修改表单字段 | 输入停止 1 秒后自动保存 |
| 参数范围校验 | 输入非法值 | 显示错误提示，禁用提交 |
| 系统配置折叠 | 访问系统设置 | Level 1 配置默认折叠 |
| 回测快速配置 | 访问回测页面 | 快速配置区域显眼易用 |

### 9.2 技术验收

| 验收项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| React Query 缓存 | 刷新页面 | 策略列表从缓存加载 |
| 表单防抖 | 快速输入 | 1 秒后触发保存请求 |
| Tooltip 动态加载 | 打开 Tooltip | 显示后端提供的说明内容 |
| 回测参数快照 | 运行回测 | 报告包含使用的配置参数 |

---

## 十、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 文档缺失导致返工 | 低 | 高 | 本架构文档作为 SSOT |
| 路由冲突导致混乱 | 中 | 中 | 明确新页面命名和路由 |
| API 接口不一致 | 中 | 高 | 统一 API 路径，编写接口契约 |
| 用户不适应新导航 | 低 | 中 | 添加迁移提示 Banner |
| 实时保存冲突 | 中 | 中 | 使用防抖 + 乐观更新 |

---

## 十一、附录

### 11.1 相关文件

| 文件 | 路径 |
|------|------|
| PRD | `docs/products/frontend-config-optimization-prd.md` |
| 前端审查报告 | `docs/reviews/fe-001-frontend-design-review.md` |
| 接口契约文档 | `docs/contracts/fe-001-config-api-contracts.md` |

### 11.2 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|----------|--------|
| v1.0 | 2026-04-06 | 初始版本 | Claude |

---

**架构师签名**: Claude (前端开发专家)  
**批准日期**: 2026-04-06
