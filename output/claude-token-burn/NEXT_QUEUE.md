# Claude Token-Burn 下一步任务队列

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-INDEX-011
Mode: read-only queue — no file modifications except this report

---

## 队列总览

| 分组 | 数量 | 说明 |
|------|------|------|
| Safe Now / docs-only | 2 | 纯文档，零代码变更，可立即执行 |
| Safe Now / output-only planning | 1 | 仅写 output/，不影响 mainline |
| Safe After Mainline Acceptance | 8 | mainline 完成后可安全分发 |
| Decision Required Before Implementation | 5 | 需 Codex 先做决策 |
| Do Not Touch During Mainline Acceptance | 4 | mainline 期间禁止触碰 |

---

## A. Safe Now / docs-only

### Q-001: Commit Agent Authority Cleanup Diff

| Field | Value |
|---|---|
| **Queue ID** | Q-001 |
| **Source report(s)** | TASKPACK-003 CARD-001A, REVIEW-002 |
| **Goal** | 提交 27 文件 agent 指令权威路径重写 |
| **Allowed files** | `.agents/skills/*/SKILL.md`, `.claude/commands/*.md`, `.claude/team/**`（已修改） |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `git diff HEAD --stat -- src/ tests/ scripts/ deploy/` 返回空；`grep -rn "docs/ops/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" \| grep -v "Do not recreate"` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | solo |

### Q-002: owner-runtime-console Anti-Regression Scanner

| Field | Value |
|---|---|
| **Queue ID** | Q-002 |
| **Source report(s)** | UICARDS-005 UIG-001, AUDIT-001 |
| **Goal** | 在 owner-runtime-console 的 visual:qa 门禁中加入禁止术语自动扫描 |
| **Allowed files** | `owner-runtime-console/scripts/visual-qa.ts`, `owner-runtime-console/package.json` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`(backend), `deploy/`, `trading-console/`, `live-config.env`, `.env*` |
| **Tests/verification** | 当前代码库零违规；注入测试术语能被捕获 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize（与 Q-001 独立） |

---

## B. Safe Now / output-only planning

### Q-003: INDEX.md + NEXT_QUEUE.md（本任务）

| Field | Value |
|---|---|
| **Queue ID** | Q-003 |
| **Source report(s)** | 全部 17 个报告 |
| **Goal** | 创建 token-burn 报告索引和下一步任务队列 |
| **Allowed files** | `output/claude-token-burn/INDEX.md`, `output/claude-token-burn/NEXT_QUEUE.md` |
| **Forbidden files** | 所有其他文件 |
| **Tests/verification** | `ls output/claude-token-burn/INDEX.md output/claude-token-burn/NEXT_QUEUE.md`；`git status --short` 确认只改了这两个文件 |
| **Risk level** | NONE |
| **Parallelism safety** | solo |

---

## C. Safe After Mainline Acceptance

### Q-004: Quarantine Header Cleanup (7 files)

| Field | Value |
|---|---|
| **Queue ID** | Q-004 |
| **Source report(s)** | TASKPACK-003 CARD-002A, CLEANUP-PLAN-001 Group D |
| **Goal** | 删除或重写 7 个 quarantined/superseded 文件的 CAUTION header，指向当前权威链 |
| **Allowed files** | `.claude/AGENTIC-WORKFLOW-GUIDE.md`, `.claude/MCP-ORCHESTRATION.md`, `.claude/TEAM-SETUP-SUMMARY.md`, `.claude/team/QUICKSTART.md`, `.claude/team/QUICK-REFERENCE.md`, `.agents/skills/agentic-workflow/README.md`, `.claude/skills/agentic-workflow/README.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*`, 任何活跃运行时源码 |
| **Tests/verification** | `grep -rn "docs/canon/" <target files>` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize |

### Q-005: Duplicate Skill Copy Alignment

| Field | Value |
|---|---|
| **Queue ID** | Q-005 |
| **Source report(s)** | TASKPACK-003 CARD-002B, REVIEW-002 Class 2 |
| **Goal** | 对齐 `.claude/skills/pua-skill/SKILL.md` 与已更新的 `.agents/skills/pua-skill/SKILL.md` |
| **Allowed files** | `.claude/skills/pua-skill/SKILL.md` |
| **Forbidden files** | `.agents/skills/pua-skill/SKILL.md`（已正确，不修改） |
| **Tests/verification** | `grep -n "docs/ops/" .claude/skills/pua-skill/SKILL.md` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize |

### Q-006: Memory Authority Header Fix

| Field | Value |
|---|---|
| **Queue ID** | Q-006 |
| **Source report(s)** | TASKPACK-003 CARD-002C, REVIEW-002 Class 3 |
| **Goal** | 更新 `.claude/memory/project-core-memory.md` 读取规则从 `docs/canon/` 到 `docs/current/*`；更新 MEMORY.md 标题 |
| **Allowed files** | `.claude/memory/project-core-memory.md`, `.claude/memory/MEMORY.md` |
| **Forbidden files** | `.claude/memory/` 以外的任何文件 |
| **Tests/verification** | `grep -n "docs/canon/" .claude/memory/project-core-memory.md` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize |

### Q-007: FinalGate Blocker Class Consolidated Test (TESTCARD-004)

| Field | Value |
|---|---|
| **Queue ID** | Q-007 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-004, TEST-MAP-001 Step 8 |
| **Goal** | 为所有 6 个 FinalGate blocker class 编写综合测试（9 个测试用例） |
| **Allowed files** | `tests/unit/test_final_gate_all_blocker_classes.py`（新建） |
| **Forbidden files** | `src/**`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `python -m pytest tests/unit/test_final_gate_all_blocker_classes.py -v` |
| **Risk level** | CRITICAL（FinalGate 是最后安全屏障），但 tests-only 无源码变更 |
| **Parallelism safety** | can-parallelize |

### Q-008: Post-Submit Partial Fill + Reconciliation Test (TESTCARD-006)

| Field | Value |
|---|---|
| **Queue ID** | Q-008 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-006, TEST-MAP-001 Step 10 |
| **Goal** | 为 partial fill 结算和 reconciliation mismatch 编写测试（8 个测试用例） |
| **Allowed files** | `tests/unit/test_post_submit_partial_fill_and_reconciliation.py`（新建） |
| **Forbidden files** | `src/**`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `python -m pytest tests/unit/test_post_submit_partial_fill_and_reconciliation.py -v` |
| **Risk level** | HIGH（结算错误导致预算漂移），但 tests-only |
| **Parallelism safety** | can-parallelize |

### Q-009: Notification / Review Outcome Test (TESTCARD-007)

| Field | Value |
|---|---|
| **Queue ID** | Q-009 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-007, TEST-MAP-001 Step 11 |
| **Goal** | 为通知交付和 review outcome 传播编写测试（8 个测试用例） |
| **Allowed files** | `tests/unit/test_notification_and_review_propagation.py`（新建） |
| **Forbidden files** | `src/**`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `python -m pytest tests/unit/test_notification_and_review_propagation.py -v` |
| **Risk level** | MEDIUM（通知失败 = Owner 盲操作），但 tests-only |
| **Parallelism safety** | can-parallelize |

### Q-010: Handoff Read-Only QA Cards (Phase 1)

| Field | Value |
|---|---|
| **Queue ID** | Q-010 |
| **Source report(s)** | HANDOFFCARDS-006 HQ-001A~HQ-006A, HANDOFFQA-007 |
| **Goal** | 执行 9 个 read-only QA 卡：handoff 完整性、mode 对齐、RequiredFacts 覆盖、conflict policy 可测性、research boundary、provenance、gap matrix、Owner 术语映射 |
| **Allowed files** | `docs/current/strategy-group-handoffs/`（只读） |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | 每个 QA 卡有独立验证命令（见 HANDOFFCARDS-006） |
| **Risk level** | LOW（只读审计） |
| **Parallelism safety** | can-parallelize（9 个 QA 卡相互独立） |

---

## D. Decision Required Before Implementation

### Q-011: SOR-001 Mode Alignment

| Field | Value |
|---|---|
| **Queue ID** | Q-011 |
| **Source report(s)** | DECISIONPACK-009 Topic 1, HANDOFFQA-007 F-001, CODETRACE-008 BF-001 |
| **Goal** | 解析 SOR-001 默认模式：推荐 Option B（collapse to `armed_observation`） |
| **Decision needed** | Codex 选择：A（实现 session-window gating）/ B（collapse to armed_observation）/ C（document as advisory） |
| **推荐方案** | Option B — 安全、即时、对齐文档与运行时行为 |
| **Allowed files**（实施后） | `docs/current/strategy-group-handoffs/main-control-handoff-index.md`, `docs/current/strategy-group-handoffs/main-control-admission-priority.md`, `scripts/build_strategy_group_handoff_intake_packet.py` |
| **Forbidden files** | `src/**`, `tests/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Risk level** | LOW（Option B 仅文档+1 行代码） |
| **Parallelism safety** | max-1（需要先做决策） |

### Q-012: Review Outcome Vocabulary Mapping

| Field | Value |
|---|---|
| **Queue ID** | Q-012 |
| **Source report(s)** | DECISIONPACK-009 Topic 3, HANDOFFQA-007 F-004/F-005, CODETRACE-008 BF-003 |
| **Goal** | 文档化后端英文 review outcome 与 board contract 中文 Owner 词汇的映射 |
| **Decision needed** | Codex 选择：A（前端翻译）/ B（后端 emit 双字段）/ C（文档映射表，推荐） |
| **推荐方案** | Option C — 映射表已在 DOCFIX-010 中应用到 board contract |
| **Allowed files**（实施后） | `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`（已应用），后续可选手 handoff.json |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize（与 Q-011 独立） |

### Q-013: Freshness Semantics Documentation

| Field | Value |
|---|---|
| **Queue ID** | Q-013 |
| **Source report(s)** | DECISIONPACK-009 Topic 2, HANDOFFQA-007 F-002, CODETRACE-008 BF-002 |
| **Goal** | 文档化 Candidate Packet Freshness 120s 是 watcher metadata，非运行时强制门禁 |
| **Decision needed** | Codex 选择：A（保持 upstream enum-only，推荐）/ B（强制 numeric 120s）/ C（per-fact windows） |
| **推荐方案** | Option A — 文档已在 DOCFIX-010 中应用 |
| **Allowed files** | 已应用到 `main-control-watcher-cadence.md` 和 `main-control-conflict-policy.md` |
| **Risk level** | NONE |
| **Parallelism safety** | can-parallelize |

### Q-014: trading-console Developer/Audit Classification

| Field | Value |
|---|---|
| **Queue ID** | Q-014 |
| **Source report(s)** | UICARDS-005 UIG-002, AUDIT-001, TASKPACK-003 CARD-003A |
| **Goal** | Codex 决定 trading-console 是 developer-only、需要 remediation、还是归档 |
| **Decision needed** | Codex 选择：a（标记 developer-only）/ b（Owner surface + remediation）/ c（归档） |
| **Blocked cards** | UIG-003, UIG-004, UIG-008 依赖此决策 |
| **Risk level** | MEDIUM（产品表面语义） |
| **Parallelism safety** | max-1 |

### Q-015: Admission + Post-Settlement Safety Tests (Codex-owned source changes)

| Field | Value |
|---|---|
| **Queue ID** | Q-015 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-001/002/003/005, AUDIT-002 |
| **Goal** | 4 个 Codex-owned 测试卡：stale facts confirmation blocking、idempotency degraded mode、no-safe-executor blocked status、admission stale facts + duplicate guard |
| **Decision needed** | Codex 必须先批准预期行为并落地源码修改，Claude 再写测试 |
| **Blocked by** | mainline acceptance + Codex source changes |
| **Risk level** | MEDIUM-HIGH（运行时安全边界） |
| **Parallelism safety** | max-1（需要 Codex 逐个审批） |

---

## E. Do Not Touch During Mainline Acceptance

### Q-016: Old SQLite Repository Removal (CARD-005A)

| Field | Value |
|---|---|
| **Queue ID** | Q-016 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005A |
| **Why blocked** | 需要更新所有 importer 到 pg_* 等价物；触及 Codex-owned 核心文件 |
| **Unblock condition** | mainline acceptance 完成 + Codex 确认零活跃 caller + 全测试通过 |

### Q-017: Config System Unification (CARD-005B)

| Field | Value |
|---|---|
| **Queue ID** | Q-017 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005B |
| **Why blocked** | config_manager.py 被广泛 import；跨切面重构 |
| **Unblock condition** | mainline acceptance 完成 + Codex 专用 task card |

### Q-018: Runtime Domain Chain Rationalization (CARD-005C)

| Field | Value |
|---|---|
| **Queue ID** | Q-018 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005C |
| **Why blocked** | 35 个 domain 文件的架构决策 |
| **Unblock condition** | mainline acceptance 完成 + Codex 架构决策 |

### Q-019: binding vs linkage Consolidation (CARD-005D)

| Field | Value |
|---|---|
| **Queue ID** | Q-019 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005D |
| **Why blocked** | domain model 重命名需要 Codex 决定规范术语 |
| **Unblock condition** | mainline acceptance 完成 + Codex 决定 |

---

## 并发推荐

### 约束

- 最多 3 个 Claude 任务并行
- 避免 owner-runtime-console/mainline 干扰
- tests-only 卡可并行（无源码冲突）
- docs-only 卡可并行（无代码冲突）
- Codex-owned 卡需串行（等待审批）

### 推荐分发波次

**Wave 0（立即）— 2 个并行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-001 | commit agent cleanup diff |
| 2 | Q-002 | owner-runtime-console anti-regression scanner |

**Wave 1（mainline 后立即）— 3 个并行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-004 + Q-005 + Q-006 | agent config cleanup 尾巴（quarantine headers + duplicate skill + memory） |
| 2 | Q-007 | FinalGate blocker class tests（CRITICAL） |
| 3 | Q-008 | post-submit partial fill tests（HIGH） |

**Wave 2（mainline 后 P1）— 3 个并行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-009 | notification/review tests |
| 2 | Q-010 | handoff read-only QA cards |
| 3 | Q-011 + Q-012 + Q-013 | decision pack 实施（需 Codex 先决策） |

**Wave 3（Codex 决策后）— 串行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-014 | trading-console 分类决策 |
| 2 | Q-015 | admission safety tests（需 Codex source changes） |

**Wave 4+（长期）**

| 槽位 | 任务 | 说明 |
|------|------|------|
| — | Q-016 ~ Q-019 | structural slimming（需 Codex clearance） |

---

## Resume Prompt（给下一个 Codex turn）

```text
Context: Claude token-burn reports are indexed at output/claude-token-burn/INDEX.md.
Next queue is at output/claude-token-burn/NEXT_QUEUE.md.

Current branch: codex/owner-runtime-console-v1
Mainline status: active acceptance in progress

Immediate safe actions (no mainline interference):
- Q-001: Commit the 27-file agent instruction cleanup diff
- Q-002: Add forbidden-term scanner to owner-runtime-console visual:qa

Pending Codex decisions:
- Q-011: SOR-001 mode (recommended: Option B — collapse to armed_observation)
- Q-012: Review vocabulary (recommended: Option C — mapping table in board contract, already applied)
- Q-013: Freshness semantics (recommended: Option A — keep upstream enum-only, docs already applied)
- Q-014: trading-console classification

After mainline acceptance:
- Q-004~Q-006: Agent config cleanup tail
- Q-007~Q-009: Safety test cards (FinalGate, partial-fill, notification)
- Q-010: Handoff QA cards

Do NOT touch during mainline: src/**, tests/**, scripts/**, deploy/**, live-config.env, owner-runtime-console/src/**.
```

---

*End of NEXT_QUEUE.*
