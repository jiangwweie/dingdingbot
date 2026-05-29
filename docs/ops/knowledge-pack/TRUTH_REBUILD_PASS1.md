# Current Truth Rebuild Pass 1

Date: 2026-05-29
Method: read-only, no code changes, no PG mutation, no exchange calls

---

## 1. 当前仓库状态

- **Branch**: `codex/brc-owner-console-v0`
- **Git status 摘要**:
  - 4 个已跟踪文件被修改（未暂存）:
    - `docs/ops/live-safe-v1-progress.md` (+23 行)
    - `docs/ops/live-safe-v1-task-board.md` (+1 行)
    - `docs/ops/project-roadmap-v2.md` (+31 行)
    - `src/infrastructure/pg_models.py` (+500 行)
  - 大量 untracked 文件：6 个 migration (022-027)、8 个 domain 文件、4 个 PG repository、5 个 application service、8 个 script、14 个 test 文件、knowledge-pack 目录
- **最近 10 个 commit 摘要**:
  - `559c95e` docs(brc): record R5 admission and read-only state
  - `860772e` fix(brc): gate signal execution by permission
  - `3e22b6a` feat(brc): add live read-only detection runner
  - `668acba` feat(brc): add admission-backed runtime evidence chain
  - `50cb1ba` docs(brc): record tf001 full-chain validation stage
  - `31075d1` test(brc): add tf001 carrier full-chain smoke
  - `6d10165` feat(brc): add tf001 carrier playbook
  - `785ef23` test(brc): add tf001 carrier decision review smoke
  - `3eeef88` feat(brc): add owner console evidence hardening
  - `769d902` feat(brc): harden owner console operation workbench

---

## 2. knowledge-pack 可信度判断

| 文档 | 是否可能过期 | 主要风险 | 是否可作为当前事实 |
|---|---|---|---|
| PROJECT_OVERVIEW.md | 低风险 | 架构描述准确，但高估了 Historical Research 链路的集成状态 | 可作为概览，但 UF-001/003/005/006 条目需要重写 |
| FACT_REGISTRY.md | **中风险** | F-011 说 "27 个 migration"，但只有 001-021 被 git 跟踪；UF-001 说 Strategy Family Registry PG 链路待确认，实际上 ORM 模型在 pg_models.py 但 migration 未跟踪 | 需要更新 F-011 和 UF 条目 |
| MODULE_MAP.md | **中风险** | 第 4/5 节（Strategy Research / Backtest Layer）高估了新模块的集成状态；所有 untracked 文件的实际集成度为零 | Section 2-3 基本准确；Section 4-5 需要降级 |
| STRATEGY_RESEARCH_HISTORY.md | 低风险 | 策略研究历史主要基于 docs/ops 报告，与代码状态无关 | 可作为研究档案 |
| CURRENT_STATE_AND_NEXT_ACTIONS.md | 低风险 | 当前状态描述准确 | 可作为行动指南 |
| PROMPT_LIBRARY.md | 低风险 | 模板内容不依赖代码状态 | 可直接使用 |

---

## 3. 仍然成立的事实

| ID | 事实 | 当前证据 | 置信度 |
|---|---|---|---|
| F-001 | 项目当前阶段为 BRC Reset / Opportunity Structure Discovery v0 | `docs/ops/project-roadmap-v2.md` 已跟踪文件确认 | HIGH |
| F-002 | 实盘交易被绝对禁止 | `docs/adr/0009-*.md` 已跟踪文件确认 | HIGH |
| F-003 | testnet-first / production-blocked 运营姿态 | `docs/ops/brc-testnet-first-production-blocked-principle.md` 已跟踪 | HIGH |
| F-004 | BRC Campaign 在 Binance testnet 上完成受控验证 | 最近 commit 历史 + task board 确认 | HIGH |
| F-005 | CPM-1 OOS_NEGATIVE，已暂停 | `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md` 已跟踪 | HIGH |
| F-007 | 无任何策略通过 SRR-002 标准 | task board + roadmap 确认 | HIGH |
| F-009 | BRC 控制台 v0 已实现 5 个 P0 页面 | 最近 commit 历史确认 | HIGH |
| F-010 | GKS fail-closed 设计 | commit `bc7e2ad` + code 确认 | HIGH |
| F-012 | Campaign 状态机 table-driven + PG 持久化 | migration 010/011 已跟踪，pg_models.py 包含对应 ORM | HIGH |
| F-015 | TF-001 是第一个 BRC carrier-validation playbook | commit `6d10165` + task board 确认 | HIGH |
| F-019 | Withdrawal 是 Owner 外部行为 | task board + progress 记录确认 | HIGH |
| F-020 | 操作员认证使用 TOTP + password | `src/interfaces/operator_auth.py` 存在 | HIGH |

---

## 4. 已过期或不应直接相信的事实

| ID | 原文说法 | 当前发现 | 风险 |
|---|---|---|---|
| F-011 | "项目有 27 个 Alembic migration（001-027）" | **只有 001-021 被 git 跟踪**。022-027 是 untracked 文件。`pg_models.py` 中的 ORM 模型（+500 行）也是 modified/unstaged 状态。实际可部署的 migration 链是 001-021。 | **高**：如果只看文件系统会误认为 022-027 已集成；实际上它们在 git 层面不存在 |
| UF-001 | "Strategy Family Registry PG 链路是否端到端完整" — 标记为待确认 | 实际上：ORM 模型 `PGBrcStrategyFamilyRegistryORM` 已在 `pg_models.py`（unstaged 修改），migration 022 存在但 untracked，repository 存在但 untracked，**无任何已跟踪文件导入该 repository**。链路存在但集成度为零。 | **高**：不应视为"待确认"，应视为"未集成" |
| UF-003 | "历史 OHLCV 数据导入工具是否已运行" | `scripts/import_sqlite_klines_to_pg.py` 是 untracked 文件。无证据表明已运行。 | **中** |
| UF-005/006 | "historical signal evaluation / research sampling 是否端到端验证" | 两个 service 文件都是 untracked，且无任何已跟踪文件导入它们。 | **中**：应从"待确认"改为"未集成" |
| MODULE_MAP Section 4 | "Strategy Research Layer — 端到端验证状态：部分" | 实际上新的 research 层文件全部 untracked，无任何已跟踪代码导入。只有 `backtester.py`（已跟踪）有独立的回测能力。 | **中**：新 research 层应标注为 "untracked, not integrated" |
| Knowledge-pack 整体 | 将 untracked 文件与已跟踪文件混为一谈 | knowledge-pack 没有区分 git tracked vs untracked 状态，导致对新模块的集成状态判断过于乐观 | **中**：所有涉及 022-027 和相关 domain/infra/app 文件的结论需要降级 |

---

## 5. 需要继续核验的高风险事项

| 优先级 | 事项 | 需要检查哪里 | 为什么重要 |
|---|---|---|---|
| **P0** | pg_models.py 的 unstaged +500 行修改是否应提交 | `git diff src/infrastructure/pg_models.py` 详细审查 | 这些 ORM 模型是 022-027 migration 的前提；不提交则 migration 无法运行 |
| **P0** | migration 022-027 是否应该被 git 跟踪 | Owner/Codex 决策 | 决定 historical research / strategy family registry 功能是否进入主线 |
| **P1** | account facts 双路径的实际实现位置 | `api_brc_console.py:1910` (`_account_facts` 函数) vs `account_service.py` | `_account_facts` 确实有 local PG + exchange 双路径（positions/orders），但 `AccountService` 只有 exchange 路径（balance）。需要区分这两个概念 |
| **P1** | `brc_live_read_only_detection_runner.py` 的实际作用 | `src/application/brc_live_read_only_detection_runner.py` | commit `3e22b6a` 添加了这个文件，未在 knowledge-pack 中充分描述 |
| **P1** | `execution_permission.py` 中 `account_facts_permission` 的实际调用链 | `src/application/execution_permission.py` | 决定 account facts 如何影响执行权限 |
| **P2** | 8 个 untracked scripts 的实际功能 | `scripts/` 目录 | 这些脚本是研究工具，但未确认是否可独立运行 |
| **P2** | 14 个 untracked test 文件的测试覆盖范围 | `tests/unit/` 目录 | 决定新模块的测试完整性 |

---

## 6. 下一轮建议

### 立即可做（read-only）

1. **读取 `pg_models.py` diff 的具体内容**，确认 500 行新增 ORM 模型是否与 022-027 migration 文件对应。
2. **读取 `brc_live_read_only_detection_runner.py`**，确认其功能和集成状态。
3. **读取 `execution_permission.py`** 中 `account_facts_permission` 逻辑，确认 account facts 如何影响执行权限决策。
4. **读取一个 untracked migration（如 022）**，确认其 revision id 和依赖链是否正确指向 021。

### 需要 Owner/Codex 决策

5. 决定 022-027 和相关 untracked 文件是否应提交到 git。
6. 决定 knowledge-pack 是否需要基于 tracked-only 重写，还是接受 mixed tracked/untracked 状态。

### 不建议

- 不建议在未确认 migration 链完整性前执行 `alembic upgrade head`
- 不建议在未确认 git 状态前将 knowledge-pack 视为权威文档
