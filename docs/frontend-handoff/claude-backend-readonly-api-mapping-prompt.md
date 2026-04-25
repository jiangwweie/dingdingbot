# Claude Prompt - Backend Readonly API Mapping

你在 `/Users/jiangwei/Documents/final` 仓库做一轮“后端只读 API v1 映射梳理”。不要改业务代码，不要提交 git。

## 目标

1. 盘点当前已有后端 API、仓储、artifact 数据源，哪些可以直接复用，哪些需要新增聚合层。
2. 把前端 `gemimi-gemimi-web-front` 的 mock 契约映射到现有后端能力。
3. 输出“可直接实现 / 需新增 read model / 当前缺口”三类结论。

## 先读这些文件

1. `docs/planning/architecture/2026-04-25-backend-readonly-api-and-api-module-roadmap.md`
2. `docs/planning/architecture/2026-04-25-console-readonly-api-v1-contract.md`
3. `gemimi-gemimi-web-front/src/types/index.ts`
4. `gemimi-gemimi-web-front/src/services/mockApi.ts`
5. `src/interfaces/api.py`

## 任务 A：现状盘点

请搜索并梳理以下内容：

- 现有 API 路由
- 现有可复用的 service / repository / provider
- 现有 candidate / backtest / replay artifact 数据来源
- 现有 runtime snapshot / account / position / order / signal / attempt 数据来源

建议搜索：

- `rg -n "@app.get|@router.get|def set_dependencies|def set_v3_dependencies" src/interfaces`
- `rg -n "SignalStatusTracker|ConfigSnapshotService|ExecutionIntent|recovery|breaker|Account|Position|Order|candidate|replay|backtest" src`

## 任务 B：按接口合同做映射表

针对以下接口逐个判断：

- `GET /api/runtime/overview`
- `GET /api/runtime/portfolio`
- `GET /api/runtime/positions`
- `GET /api/runtime/events`
- `GET /api/runtime/health`
- `GET /api/runtime/signals`
- `GET /api/runtime/attempts`
- `GET /api/runtime/execution/intents`
- `GET /api/runtime/execution/orders`
- `GET /api/research/candidates`
- `GET /api/research/candidates/{candidate_name}`
- `GET /api/research/candidates/{candidate_name}/review-summary`
- `GET /api/research/replay/{candidate_name}`
- `GET /api/config/snapshot`

每个接口都给出：

1. 是否已有现成 API 可复用
2. 是否已有后端数据源但缺聚合层
3. 是否当前完全缺口
4. 推荐的数据真源
5. 推荐落在哪个模块

## 任务 C：输出实现优先级建议

请给出一个务实的实现顺序：

1. 哪 3-5 个接口最适合先做
2. 哪些接口会卡在 `api.py` 或 read model 缺失
3. 哪些接口可以让前端最早从 mock 切到真实数据

## 最终输出格式

按这个格式汇报：

- A. 现状概览
- B. 接口映射表
- C. 当前最大缺口
- D. 推荐先做的接口顺序
- E. 风险与注意事项

## 约束

1. 只做分析，不改代码。
2. 不跑长测试。
3. 不擅自修改前端 mock 契约。
4. 如果发现 mock 字段与后端现实严重冲突，可以指出，但不要自行改文件。
