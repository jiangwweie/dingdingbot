# Claude Prompt - Console API First Batch Implementation

你在 `/Users/jiangwei/Documents/final` 仓库继续推进“后端只读 API 第一批实现”。可以改代码，但不要跑长测试，不要提交 git。

## 背景

当前第一批接口已经冻结为：

1. `GET /api/runtime/overview`
2. `GET /api/runtime/portfolio`
3. `GET /api/runtime/health`
4. `GET /api/research/candidates`

当前仓库已经新增了第一阶段骨架：

- `src/application/readmodels/runtime_overview.py`
- `src/application/readmodels/runtime_portfolio.py`
- `src/application/readmodels/runtime_health.py`
- `src/application/readmodels/candidate_service.py`
- `src/interfaces/api_console_runtime.py`
- `src/interfaces/api_console_research.py`

并且：

- `main.py -> api.py` 注入链已补 runtime config provider / execution recovery repo / startup reconciliation summary
- 新 router 已挂到 `src/interfaces/api.py`

## 你的任务

请基于现有骨架，做“实现补强 + 小范围测试补齐”，但不要扩大范围到第二批接口。

### 任务 A：代码补强

重点检查并补强这几件事：

1. `runtime/overview`
   - profile/version/hash/frozen 是否和 runtime provider 对齐
   - backend_summary 是否合理
   - freshness_status 推导是否稳妥

2. `runtime/portfolio`
   - total_equity / available_balance / unrealized_pnl / total_exposure 计算是否一致
   - position 投影字段是否和前端契约一致
   - daily_loss_limit / daily_loss_used 的 fallback 是否合理

3. `runtime/health`
   - breaker_summary / recovery_summary 必须保持分离
   - permission summary / startup markers 的状态不要误导
   - exchange stale / degraded / down 的逻辑是否过于粗糙

4. `research/candidates`
   - candidate 文件扫描是否健壮
   - review_status / strict_gate_result / warnings 的推导是否和 review rubric 对齐
   - 对损坏 JSON / 缺字段 / 空目录是否有防御

### 任务 B：小范围测试

请只补最小单测，不跑长测试。

建议新增：

1. `tests/unit/test_console_runtime_readmodels.py`
   - overview freshness 分类
   - portfolio exposure / leverage_usage / daily_loss fallback
   - health breaker/recovery summary 分离

2. `tests/unit/test_candidate_artifact_service.py`
   - list_candidates 正常读取
   - 空目录返回空列表
   - 坏 JSON 跳过
   - review_status 推导基本正确

如果你觉得测试文件名更适合现有 repo 风格，可以调整，但范围只限第一批接口。

## 约束

1. 只做第一批接口相关代码。
2. 不扩到 `runtime/events`。
3. 不扩到 candidate detail / replay / config snapshot。
4. 不重构 `api.py` 大结构。
5. 不运行长测试；如果跑测试，只跑你新增的最小单测。
6. 不提交 git。

## 最终汇报格式

- A. 修改了哪些文件
- B. 解决了哪些具体问题
- C. 跑了哪些最小测试（如果你跑了）
- D. 还剩哪些明显缺口
