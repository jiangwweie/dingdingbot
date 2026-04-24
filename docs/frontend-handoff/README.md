# Frontend Handoff for Google AI Studio

这份目录用于给 Google AI Studio 提供**最小可执行的前端交接包**。

目标：

1. 让 AI Studio 根据已有规划直接生成前端工程骨架
2. 使用 mock 数据驱动页面
3. 第一轮只生成只读控制台，不接真实后端

## 建议上传的文件

### 必传

1. `/Users/jiangwei/Documents/final/docs/planning/architecture/2026-04-24-frontend-runtime-monitor-and-research-console-plan.md`
2. `/Users/jiangwei/Documents/final/docs/planning/optuna-candidate-review-rubric.md`
3. `/Users/jiangwei/Documents/final/docs/frontend-handoff/ai-studio-frontend-task.md`
4. `/Users/jiangwei/Documents/final/docs/frontend-handoff/mock-api-contract.md`

### 建议一并上传

5. `/Users/jiangwei/Documents/final/docs/frontend-handoff/first-prompt.md`

## 推荐使用方式

### 第一步

先上传上面的 4-5 个文件。

### 第二步

把 `first-prompt.md` 里的提示词直接粘贴到 AI Studio 输入框。

### 第三步

第一轮只要求它生成：

1. React + TypeScript + TailwindCSS 工程骨架
2. 路由和布局
3. 页面文件
4. mock API 层
5. mock fixture 数据
6. 类型定义
7. README

### 第四步

不要在第一轮要求：

1. 接真实后端
2. 做配置编辑器
3. 做 runtime 热改
4. 做 WebSocket
5. 做 candidate review 写回
6. 做复杂图表平台

## 第一轮验收重点

拿到结果后，先检查：

1. 是否有 `Runtime` / `Research` 两个域
2. 是否包含：
   - `Runtime / Overview`
   - `Runtime / Signals`
   - `Runtime / Execution`
   - `Runtime / Health`
   - `Research / Candidates`
   - `Research / Candidate Detail`
   - `Research / Replay`
3. 是否使用 mock 数据，而不是偷偷接真实接口
4. 是否保持只读
5. 是否有 loading / empty / error 状态
6. 是否在 Runtime 页面提供手动刷新

## 说明

这套交接包的目标不是让 AI Studio 一次做完最终产品，而是：

- 先生成一个**可运行、可接手、便于后改**的前端初稿工程
- 再由人类或后续模型继续做第二轮修正
