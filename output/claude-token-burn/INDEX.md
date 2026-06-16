# Claude Token-Burn 报告索引

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-INDEX-011
Mode: read-only index — no file modifications except this report and NEXT_QUEUE.md

---

## 1. 报告总览

| # | 文件名 | 类型 | 状态 | 最高严重度 | 一句话价值 | 下一步 |
|---|--------|------|------|-----------|-----------|--------|
| 1 | `CLAUDE-AUDIT-001-owner-language-leakage.md` | audit | read-only | HIGH | owner-runtime-console 合规；trading-console 有 62+ 处内部术语泄漏 | 等 Codex 决定 trading-console 定位 |
| 2 | `CLAUDE-AUDIT-002-runtime-safety-redteam.md` | audit | read-only | MEDIUM | 7 项安全发现，无 P0 绕过；stale-fact 和 idempotency 有部分缺口 | 等 mainline 后补充测试 |
| 3 | `CLAUDE-TEST-MAP-001-runtime-path-test-coverage.md` | audit | read-only | HIGH | 11 步运行时路径测试覆盖矩阵；admission 和 notification 最弱 | 等 mainline 后补测试 |
| 4 | `CLAUDE-DEBT-001-deletion-consolidation-map.md` | cleanup-plan | read-only | HIGH | 940MB 非源码质量；35 个 domain 文件链可压缩至 ~15 | 等 mainline 后分 wave 执行 |
| 5 | `CLAUDE-DOC-DEBT-001-doc-authority-conflict-map.md` | docs-fix | docs-applied | HIGH | 19 个 agent 配置文件引用已删除的 docs/canon/* 路径 | Wave 1 已应用（27 文件），Wave 2-5 待定 |
| 6 | `CLAUDE-SCHEMA-DEBT-001-personal-campaign-schema-usage.md` | audit | read-only | LOW | 11 个 schema 全有 Pydantic 模型对应；1 个可归档 | 等 Codex 确认 sandbox 状态 |
| 7 | `CLAUDE-CLEANUP-PLAN-001-agent-config-wave1-rewrite-plan.md` | cleanup-plan | docs-applied | MEDIUM | 35 个文件的 dead-path 重写计划 | Wave 1 已执行（27/35），剩余 8 个 quarantined 文件待处理 |
| 8 | `CODEX-CLEANUP-REVIEW-001-mainline-safe-cleanup-notes.md` | review | read-only | MEDIUM | Codex 对 Claude 报告的整合审查；确认当前清理不影响 mainline | 作为后续 wave 参考 |
| 9 | `CLAUDE-FINAL-REVIEW-002-agent-config-cleanup-safety-review.md` | review | docs-applied | LOW | 确认 27 文件 agent 指令重写安全，不影响 mainline | 可提交或保持 uncommitted |
| 10 | `CLAUDE-FINAL-TASKPACK-003-post-acceptance-task-cards.md` | task-cards | pending-action | HIGH | 5 组 14 个 task card：acceptance-safe → P1 → P2 → deferred → do-not-touch | 按组顺序分发 |
| 11 | `CLAUDE-FINAL-TESTCARDS-004-runtime-safety-test-cards.md` | task-cards | pending-action | CRITICAL | 7 个 P1 测试卡（44 个测试用例）；覆盖 FinalGate、admission、stale-facts、idempotency | 等 mainline 后分发 |
| 12 | `CLAUDE-FINAL-UICARDS-005-owner-console-surface-governance-cards.md` | task-cards | pending-action | HIGH | 8 个 UI 治理卡；owner-runtime-console 合规，trading-console 需决策 | 等 mainline 后分发 |
| 13 | `CLAUDE-FINAL-HANDOFFCARDS-006-strategygroup-handoff-quality-cards.md` | task-cards | pending-action | P1 | 16 个 handoff 质量治理卡（8 个维度） | 等 mainline 后分发 |
| 14 | `CLAUDE-FINAL-HANDOFFQA-007-strategygroup-handoff-readonly-audit.md` | audit | read-only | P1 | 9 个 QA 卡全部执行；发现 SOR-001 模式不一致和 freshness 语义缺口 | 等 Codex 决定 SOR-001 模式 |
| 15 | `CLAUDE-FINAL-CODETRACE-008-handoff-runtime-consumption-audit.md` | code-trace | read-only | P1 | 追踪 HANDOFFQA-007 的 P1 发现到后端代码；确认 conditional_armed_observation 是 phantom mode | 等 Codex 决定 |
| 16 | `CLAUDE-FINAL-DECISIONPACK-009-runtime-semantics-adr-options.md` | decision-pack | decision-needed | P1 | 3 个运行时语义决策选项（SOR-001 mode、freshness、review vocabulary） | 等 Codex 选择方案 |
| 17 | `CLAUDE-FINAL-DOCFIX-010-docs-semantic-cleanup-report.md` | docs-fix | docs-applied | LOW | 4 个 docs/current 文件的语义清理（review mapping、gate class、freshness note） | 已应用，可验证 |
| 18 | `CLAUDE-FINAL-COMMITAUDIT-012-worktree-commit-boundary-audit.md` | review | read-only | MEDIUM | 将脏工作树拆分为 agent cleanup、docs cleanup、token-burn artifacts 与排除项 | 已由 012A 复核当前状态 |
| 19 | `CODEX-COMMITAUDIT-012A-current-state-addendum.md` | review | read-only | LOW | Codex 复核当前 tracked diff，确认 scripts/tests 瞬时观察不再适用 | 已用于提交边界 |
| 20 | `CLAUDE-FINAL-PRECOMMIT-013-safe-local-commit-verification.md` | review | read-only | LOW | 提交前 PASS 校验，确认 27 个 agent 文件与 4 个 docs 文件可拆分提交 | 已应用为 2 个本地提交 |
| 21 | `CLAUDE-FINAL-ARTIFACTAUDIT-014-token-burn-artifact-publication-audit.md` | review | read-only | LOW | 检查 token-burn artifacts 无 secrets / workspace contamination / live data | 已应用为 output artifact 提交 |
| 22 | `CLAUDE-FINAL-LOCALARTIFACTS-015-untracked-artifact-hygiene-audit.md` | audit | read-only | MEDIUM | metadata-only 盘点 648MB / 717 个未跟踪本地产物，形成清理与 .gitignore 建议 | 等 Owner 明确授权后再清理 |
| 23 | `INDEX.md` | index | read-only | LOW | token-burn 报告总索引 | 持续补齐 |
| 24 | `NEXT_QUEUE.md` | index/queue | read-only | LOW | token-burn 后续任务队列和 resume prompt | 持续补齐 |

---

## 2. 跨报告发现矩阵

| 主题 | 相关报告 | 发现摘要 | 严重度 | 状态 |
|------|---------|---------|--------|------|
| **Owner-facing 语言泄漏** | AUDIT-001, UICARDS-005 | owner-runtime-console 合规（0 违规）；trading-console 62+ HIGH 违规 | HIGH | 等 Codex 决定 trading-console 定位 |
| **运行时安全 / stale facts / idempotency** | AUDIT-002, TESTCARDS-004, CODETRACE-008 | 7 项安全发现；stale freshness 不阻塞 Operation Layer 确认；idempotency repo 可为 None | MEDIUM | 等 mainline 后补充测试和 Codex 修复 |
| **StrategyGroup handoff 完整性** | HANDOFFQA-007, HANDOFFCARDS-006 | 5×4 字段矩阵完整；SOR-001 模式不一致（P1）；review vocabulary 缺失（P2） | P1 | 等 Codex 决定 SOR-001 模式 |
| **SOR-001 conditional mode** | HANDOFFQA-007, CODETRACE-008, DECISIONPACK-009 | handoff.json 说 `armed_observation`，index/priority 说 `conditional_armed_observation`；runtime 无 session-window gating | P1 | DECISIONPACK-009 推荐 Option B（collapse to armed_observation） |
| **review outcome vocabulary** | HANDOFFQA-007, CODETRACE-008, DECISIONPACK-009 | 后端 emit `promote/revise/park`；board contract 定义 `保留/调整/暂停/停用/待复盘`；无映射层 | P2 | DECISIONPACK-009 推荐 Option C（文档映射表） |
| **agent/Claude 指令权威清理** | DOC-DEBT-001, CLEANUP-PLAN-001, REVIEW-002 | 27 文件已重写（Wave 1）；8 个 quarantined 文件待处理 | MEDIUM | Wave 1 已应用；Wave 2 待 mainline 后 |
| **deletion/consolidation 候选** | DEBT-001 | 940MB 非源码质量；35 个 domain 文件链；9 个旧 SQLite repo；config_manager vs config/ | HIGH | 等 mainline 后分 6 wave 执行 |
| **本地产物 / 未跟踪输出治理** | LOCALARTIFACTS-015, ARTIFACTAUDIT-014 | 648MB / 717 个未跟踪本地产物；live-config.env 仅识别存在、不读取；output/claude-token-burn 已安全提交 | MEDIUM | 等 Owner 授权后分阶段清理或更新 .gitignore |

---

## 3. 权威文档变更 / 应用映射

### 3.1 当前权威文档已变更

| 文档 | 变更来源 | 变更内容 |
|------|---------|---------|
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | DOCFIX-010 | 新增 Review Outcome Vocabulary Mapping 小节（6 对映射） |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | DOCFIX-010 | 新增 `hard_safety_stop`→`需要介入`、`review_only_warning`→`运行中` 映射 |
| `docs/current/strategy-group-handoffs/main-control-watcher-cadence.md` | DOCFIX-010 | 新增 Candidate Packet Freshness 是 watcher-side metadata 说明 |
| `docs/current/strategy-group-handoffs/main-control-conflict-policy.md` | DOCFIX-010 | 新增 stale facts 是 upstream status/enum 说明 |
| `.agents/skills/*/SKILL.md` (8 files) | CLEANUP-PLAN-001, REVIEW-002 | dead path 重写为当前权威链 |
| `.claude/commands/*.md` (10 files) | CLEANUP-PLAN-001, REVIEW-002 | dead path 重写为当前权威链 |
| `.claude/team/**` (9 files) | CLEANUP-PLAN-001, REVIEW-002 | dead path 重写为当前权威链 |

### 3.2 task card 来源报告

| 报告 | 产出的 task card |
|------|-----------------|
| AUDIT-001 | UIG-001 ~ UIG-008（via UICARDS-005） |
| AUDIT-002 | TESTCARD-001 ~ TESTCARD-007（via TESTCARDS-004） |
| TEST-MAP-001 | TESTCARD-004 ~ TESTCARD-007（via TESTCARDS-004） |
| HANDOFFQA-007 | HQ-001A ~ HQ-008B（via HANDOFFCARDS-006） |
| CODETRACE-008 | DECISIONPACK-TC-001 ~ TC-010（via DECISIONPACK-009） |
| DOC-DEBT-001 | CARD-002A ~ CARD-002C（via TASKPACK-003） |
| REVIEW-002 | CARD-001A ~ CARD-005D（via TASKPACK-003） |
| DEBT-001 | CARD-005A ~ CARD-005D（via TASKPACK-003） |

### 3.3 只读证据报告

| 报告 | 证据性质 |
|------|---------|
| AUDIT-001 | UI 术语泄漏证据（87 处，12 文件） |
| AUDIT-002 | 运行时安全红队证据（7 项发现，20+ 文件路径） |
| TEST-MAP-001 | 11 步运行时路径测试覆盖证据（297 test files scanned） |
| HANDOFFQA-007 | 5 StrategyGroup handoff 完整性证据（9 QA 卡执行结果） |
| CODETRACE-008 | handoff→runtime 代码消费追踪证据 |
| SCHEMA-DEBT-001 | 11 个 personal_campaign schema 使用证据 |
| LOCALARTIFACTS-015 | 未跟踪本地产物 metadata-only 清单和未来清理门控 |

### 3.4 被后续报告取代的报告

| 早期报告 | 被取代者 | 取代范围 |
|---------|---------|---------|
| AUDIT-001 的 task card 建议 | UICARDS-005 | UICARDS-005 提供了更完整的 8 卡治理方案 |
| AUDIT-002 的 task card 建议 | TESTCARDS-004 | TESTCARDS-004 将发现转化为 7 个可执行测试卡 |
| TEST-MAP-001 的 task card 建议 | TESTCARDS-004 + TASKPACK-003 | 合并为统一的测试卡和 task pack |
| HANDOFFQA-007 的 F-001/F-002 | CODETRACE-008 + DECISIONPACK-009 | CODETRACE 追踪到代码，DECISIONPACK 提供决策选项 |
| CLEANUP-PLAN-001 的执行计划 | REVIEW-002 | REVIEW-002 确认 Wave 1 已应用并评估安全性 |
| CODEX-CLEANUP-REVIEW-001 的 wave 建议 | TASKPACK-003 | TASKPACK-003 将建议转化为 5 组 14 个可执行 task card |

---

## 4. mainline acceptance 期间不触碰清单

| 类别 | 路径 |
|------|------|
| 运行时源码 | `src/**` |
| 测试 | `tests/**` |
| 脚本 | `scripts/**` |
| 部署 | `deploy/**` |
| 实盘配置 | `live-config.env`, `.env*` |
| Watcher/Tokyo | 任何 watcher 或 Tokyo 运维代码 |
| 交易所/凭证 | Exchange gateway, credentials, live profiles |
| owner-runtime-console 源码 | `owner-runtime-console/src/**` |
| quarantined agent 文件 | `.claude/AGENTIC-WORKFLOW-GUIDE.md`, `.claude/MCP-ORCHESTRATION.md`, `.claude/TEAM-SETUP-SUMMARY.md`, `.claude/team/QUICKSTART.md`, `.claude/team/QUICK-REFERENCE.md` |

---

## 5. 验证命令

```bash
# 确认所有报告文件存在
ls -la output/claude-token-burn/*.md | wc -l
# 预期: 24 (22 reports + INDEX.md + NEXT_QUEUE.md)

# 确认 INDEX.md 和 NEXT_QUEUE.md 已创建
ls -la output/claude-token-burn/INDEX.md output/claude-token-burn/NEXT_QUEUE.md

# 确认未修改其他文件
git status --short

# 确认 docs/current 已应用的变更仍在
rg 'promote.*保留|revise.*调整|park.*暂停|kill.*停用|pending.*待复盘' docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
rg 'hard_safety_stop|review_only_warning' docs/current/AI_AGENT_CONSTRAINTS.md
```

---

*End of INDEX.*
