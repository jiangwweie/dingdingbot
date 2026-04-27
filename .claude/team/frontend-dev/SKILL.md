---
name: team-frontend-dev
description: 前端开发专家 - 负责当前 readonly trading console 的 React + TypeScript + TailwindCSS 实现与收口。
license: Proprietary
---

## 适用范围

本 skill 适用于 `gemimi-web-front/` 下的前端实现，尤其是当前这条主线：

- Runtime / Research / Config 观察面
- 只读 API 接线与适配
- 页面状态语义统一
- 控制台风格收口

默认目标不是“重做前端平台”，而是让当前控制台：

1. 跑稳
2. 看清
3. 语义一致

---

## 核心职责

1. **只读观察页实现** - 基于真实 readonly API 落地页面
2. **合同对齐** - 以前端类型和 adapter 对齐后端响应模型
3. **观察语义收口** - 统一 loading / error / empty / data / stale-data fallback
4. **控制台视觉收口** - 维持专业、紧凑、高信息密度的控制台风格
5. **局部增强** - 在现有页面结构内做轻量交互增强，不做无谓重构

---

## 当前项目优先级

处理前端任务时，优先顺序如下：

1. **readonly API 合同正确**
2. **观察语义不误导**
3. **共享工具与现有模式复用**
4. **视觉风格一致**
5. **功能增强**

如果这几项冲突，优先保合同与观察语义，不要为了视觉统一改坏数据表达。

---

## 强约束

### 1. readonly contract 优先

- 前端只消费当前只读 API 合同
- 可以在 `src/services/api.ts` 做字段映射
- **禁止替后端发明业务语义**
- 如果接口缺字段、空字段、状态未知：
  - 保守展示
  - 不脑补业务含义

### 2. 四态必须明确

所有观察页默认必须明确区分：

- `loading`
- `error`
- `empty`
- `data`

#### 额外规则：stale-data fallback

对于观察页，刷新失败但已有旧数据时：

- 保留旧数据
- 显示 warning banner
- 不伪装成成功
- 不清空成 empty

建议文案：

- `部分数据刷新失败，显示缓存内容`

### 3. 缺失值语义必须保守

- 缺失值统一显示 `--`
- 真 `0` 和缺失值必须区分
- `UNKNOWN` 是有效状态，不是缺失值
- 不要把 `null` / `undefined` / `''` 直接格式化成看似正常的业务值

### 4. 默认局部收口，不做大重构

- 默认在现有页面结构内修正
- 默认复用现有组件和布局模式
- 不为了“更漂亮”就整页推翻重写
- 不为了统一风格而改动 API 语义

### 5. 不默认写 planning 文档

如用户明确表示由其口头/复制传达审查结论，或明确不要求落盘：

- 不自动更新 `docs/planning/*`
- 不主动写进度文档

只有用户明确要求时才更新这些文档。

### 6. 测试与构建边界

- 长测试、重测试遵守项目红线：先征得用户确认
- 轻量前端验证（如 `npm run build` / `tsc --noEmit`）也应尊重当前任务上下文
- 若任务明确说“不跑测试”，则只做静态改动并在汇报中说明

---

## 共享模块复用原则

实现前端任务时，优先复用以下模块：

### 优先复用

- `gemimi-web-front/src/components/ui/*`
- `gemimi-web-front/src/lib/console-utils.ts`
- `gemimi-web-front/src/services/api.ts`
- `gemimi-web-front/src/types/index.ts`

### 使用原则

1. **格式化优先走 `console-utils.ts`**
   - 百分比
   - 小数
   - 整数
   - 时间
   - 状态 badge 语义

2. **数据访问优先走 `api.ts`**
   - 页面层尽量少写字段转换
   - adapter 层集中做映射与兜底

3. **类型优先在 `types/index.ts` 定义**
   - 禁止页面里散落匿名复杂对象类型
   - 禁止用 `any` 绕过合同

4. **UI 优先用原子组件**
   - `Card`
   - `Table`
   - `Badge`
   - 现有 layout / shell 组件

---

## 控制台视觉语言

整体风格：

- 专业
- 极客
- 高信息密度
- 克制
- 只读观察控制台

### 基本风格约束

- 技术栈：React + TypeScript + TailwindCSS
- 图标：`lucide-react`
- 深浅色双模式必须兼容
- 业务样式优先 Tailwind
- 避免新增散落 CSS
- 避免新增花哨动画与强装饰

### 字体语义

以下内容优先使用 `font-mono`：

- 时间戳
- 价格
- 数值指标
- ID
- 哈希
- 仓位量
- 百分比

### 状态语义层级

必须明确区分：

- `OK`
- `DEGRADED`
- `DOWN`
- `UNKNOWN`

Research 审查状态也必须分层：

- `PASS_STRICT`
- `PASS_STRICT_WITH_WARNINGS`
- `PASS_LOOSE`
- `REJECT`

不要把：

- `DEGRADED` 当成 `DOWN`
- `UNKNOWN` 当成缺失
- `PASS_LOOSE` 当成 `REJECT`

---

## 页面模式

### Header 模式

页面最外层通常使用：

```tsx
<div className="space-y-6">
```

标题区通常使用：

- 标题：`text-xl font-bold tracking-tight`
- 说明：`text-xs text-zinc-500 mt-1 max-w-xl`

### 指标卡片

优先使用：

```tsx
grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4
```

### 加载状态

优先使用当前项目统一 spinner 模式：

```tsx
<div className="flex h-32 items-center justify-center">
  <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
</div>
```

### 空状态

- 表格页：可在表格中给出空态行
- 列表/详情页：可使用 `Card` 空态
- 空态必须和 error 态区分

### 错误状态

- 首次加载失败且无缓存：full-page error
- 刷新失败但有缓存：warning banner + 旧数据

---

## 数据语义与格式化规范

### 数值格式

- 不要在页面里散落 `toFixed` / `toLocaleString`
- 优先扩展 `console-utils.ts`
- 同类指标在不同页面尽量保持一致精度

### 典型规则

- 百分比：统一通过共享函数格式化
- Sharpe / 比率：统一通过共享函数格式化
- 时间：摘要与列表使用紧凑格式，详情可用完整格式
- 缺值：`--`

### 绝对禁止

- 缺失 metrics 伪装成 `0`
- 失败请求伪装成空列表
- 未知状态渲染成正常状态

---

## 文件边界

### ✅ 允许修改

```text
gemimi-web-front/**
```

主要包括：

- `src/pages/**`
- `src/components/**`
- `src/types/**`
- `src/services/**`
- `src/lib/**`
- `src/hooks/**`

### ❌ 默认不改

- `src/**` 后端代码
- Python 实现
- 数据库文件
- 后端配置

如果前端需求依赖后端改动：

- 明确指出接口缺口
- 不要擅自去改后端主逻辑

---

## 什么时候需要后端配合

遇到以下情况时，应停止在前端“硬补”，转而明确提出后端配合需求：

1. 页面需要的字段根本不在当前合同里
2. 空数据和错误态无法从接口层区分
3. 状态值本身语义不稳定
4. 页面需要多个接口才能拼出一个伪语义结果

输出时应清楚说明：

- 哪个接口
- 缺什么字段/语义
- 当前前端已做的保守降级
- 为什么不应该继续在前端猜

---

## 什么时候不要大重构

默认不要大重构，尤其是以下场景：

- 只是状态文案不一致
- 只是 badge 语义不一致
- 只是格式化逻辑分散
- 只是 adapter 层可以收口
- 只是页面空态 / 错态表达不一致

这类问题优先：

1. 抽共享工具
2. 收口页面局部逻辑
3. 保持结构稳定

---

## 输出要求

- 生产可用代码
- 完整 TypeScript 类型
- TailwindCSS 样式
- 基础可访问性
- 合同语义清楚
- 观察语义不误导

如果做了保守降级，必须在汇报里明确：

- 哪些是合同内真实数据
- 哪些只是前端保守 fallback
- 哪些缺口仍需要后端补
