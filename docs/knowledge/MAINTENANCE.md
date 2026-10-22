# 知识库维护、验证与完成审计

> **定位：解释性知识库** · [知识地图](README.md)。本页记录文档交付证据，不取代生产验收；当前生产事实仍由 [MAIN_CONTROL_ROADMAP.md](../current/MAIN_CONTROL_ROADMAP.md)负责。

## 维护规则

### 每次变更先回答的四个问题

1. **事实来源是谁**：代码行为、现行契约、生产事实还是历史背景；同一事实只保留一个权威 owner。
2. **影响到哪一层**：模型与不变量、用例调用、数据库事务、运行进程、Owner 表面或发布恢复。
3. **哪些图和索引会失真**：修改对应专题、图和代码定义链接，不批量生成全部文档。
4. **证据是否足够**：找到测试、运行测试和真实生产证明分别标记；缺失证据明确列项。

### 按改动更新材料

| 改动类型 | 应更新材料 | 最小验证 |
| --- | --- | --- |
| 函数移动、改名、接口字段变化 | 对应专题与 CODE_AND_TEST_INDEX | 定义行链接与引用检查、相关测试阅读 |
| Signal/准入/Command/生命周期行为 | TRADE_LIFECYCLE、RISK_AND_EXIT、相关代码索引 | 对应行为测试；生产代码改动仍需 red/green |
| 选币 Spec、时钟、Authority、Vacuum | DYNAMIC_SELECTION、DATA_MODEL | 数学/时序/恢复与数据库边界测试 |
| Owner API、鉴权、控制流程 | OWNER_CONTROLS、代码索引 | HTTP/用例/持久化的受影响验证 |
| 表结构、身份、事务或约束 | DATA_MODEL、相关流程图 | schema 与受影响事务验证 |
| 进程装配、发布、恢复顺序 | SYSTEM_OVERVIEW、DEPLOYMENT_AND_RECOVERY | 架构、部署状态机与重启测试 |
| 权威集合或入口规则变化 | SOURCE_AUTHORITY、README 及原权威测试 | 先 RED 再更新 authority set；不把本库加入 runtime authority |
| 仅生产当前状态变化 | 唯一 MAIN_CONTROL_ROADMAP | 新鲜直接事实；本库只保留指向该入口的链接 |

以上维护顺序来自[文档管理技能](../../.agents/skills/doc-manager/SKILL.md)、[工程约束](../../AGENTS.md)及[信息架构](../current/PROJECT_INFORMATION_ARCHITECTURE.md)。

## 证据标记与图表约定

**代码已验证、现行契约规定、待核实**三种状态贯穿知识库。图表注明它表达的是业务关系、简化流程、真实组件依赖还是 tracked 部署拓扑；不能用一种图替代另一种证据。

1. 使用 **Markdown + Mermaid**，图与解释和代码链接放在一起。
2. Python 链接定位到真实定义行；更新后用下列架构测试确认行号仍对应定义。
3. 图中的分支必须能关联实现或注明是缩略；不为画完整故事虚构实际状态。
4. 历史原因引用原设计或复盘，当前行为同时给代码依据。
5. 不内嵌生产 SHA、Ticket ID、币池、账户余额或临时认证阶段；研究报告不参与 runtime 决策。

### 架构决策记录

**知识库解释既有决策，不新增未授权业务决定。**跨模块新决策需要独立设计记录，说明问题、选项、选择理由、代价、影响的契约与验证；经相应决定后更新原责任文档和本库导航。现有依据是 [P0 设计](../current/P0_TRADING_KERNEL_REBUILD_DESIGN.md)及 [历史设计导航](SOURCE_AUTHORITY.md)，不复制出第二套规范。

## 本轮验证记录

**验证日期：2026-10-22，代码阅读基准见 [README](README.md)。**所有执行均在本地；PostgreSQL 测试连接已检查为 loopback，并使用仓库的受限一次性数据库夹具。没有读取 `.env`、真实 credential 内容或调用生产 API。

### 行为验证

| 组合 | 本轮实际执行的文件 | 结果与证明范围 |
| --- | --- | --- |
| **规则、控制、选币与恢复** | unit 下的 test_capacity_sizing、test_entry_dispatch_preflight、test_unknown_command_recovery、test_commands、test_reducer、test_post_fill_risk、test_exit_policy、test_owner_control、test_generic_normal_authority_contract、test_generic_recovery_grant_proof、test_generic_materialization、test_drain_strategy_entry_vacuum、test_dynamic_close_handover、test_hourly_recovery_clock、test_selection_runtime_hosting、test_deploy_tokyo_release、test_worker_process_shutdown | **445 PASS**；证明类型化规则和受控编排，不证明生产外部状态 |
| **持久化与交易闭合** | full_chain 下的 test_ticket_lifecycle、test_fault_matrix；integration 下的 test_observation_to_signal、test_signal_to_ticket、test_owner_control_plane、test_selection_entry_authority_repository、test_selection_materialization_repository、test_unknown_outcome_reconciliation | **165 PASS**；本地数据库、recording/fake venue；包括部分成交、重启未知结果、正常生命周期、权限原子性 |
| **接口与补充算法** | interfaces/test_owner_console_http；unit/owner_console/test_auth；unit 下的 test_generic_selection_core、test_generic_selection_source、test_orb_session_selection、test_reconciliation_worker_fairness、test_release_classification、test_generic_signal_path | **128 PASS**；认证接口、选币数学/来源、ORB、调度、发布分类及研究边界 |
| **事务与安全生命周期补充** | integration 下的 test_ticket_lifecycle_maintenance、test_command_dispatch、test_pg_unit_of_work、test_owner_projection、test_entry_vacuum_drain | **122 PASS**；实际 PostgreSQL 事务、租约恢复、保护、终态投影和 Vacuum |

以上 **38 个文件、860 项行为测试通过**，主要行为映射见 [CODE_AND_TEST_INDEX](CODE_AND_TEST_INDEX.md)，精确执行文件见上表。第一组通过 **17 个文件**，第二组通过 **8 个文件**，后两组分别为 **8、5 个文件**。这些数字是本轮文档验证记录，不是生产认证数量。

每组的复现方式是 `.venv/bin/python -m pytest -q <表中每个文件的完整仓库相对路径>`；所有文件以 `.py` 结尾，测试类型目录均为 `tests/trading_kernel/` 的子目录。本轮未运行完整 Release certification、长期 soak、V2 前端测试或生产验收；映射到这些范围的链接只表示已有覆盖可查。

### 可重复的文档检查

在仓库根目录执行：

```bash
.venv/bin/python -m pytest -q tests/trading_kernel/architecture
.venv/bin/python -m ruff check tests/trading_kernel/architecture/test_project_knowledge.py
.venv/bin/python scripts/audit_production_runtime_file_io.py
git diff --check
```

新增 [test_project_knowledge](../../tests/trading_kernel/architecture/test_project_knowledge.py) 先运行时确认知识库缺失导致 **RED**。它保护统一入口、页面回链、相对路径、Markdown 显式锚点与 Python 定义行；不把固定字数或图数量当作质量标准，也不能自动验证段落语义正确。

| 文档和静态检查 | 本轮结果 | 实际证明范围 |
| --- | --- | --- |
| 完整 architecture 目录 | **86 PASS，1 FAIL** | 唯一失败是已存在的测试互相导入问题，见下文；不能宣称全绿 |
| `test_project_knowledge.py` 与 `test_current_document_authority.py` | **28 PASS** | 新知识库入口/链接、当前权威白名单、引用与退役语义约束；属于上述架构集合，不重复计数 |
| Ruff 与 Mypy：新文档测试 | **PASS** | 新增检查实现的静态检查 |
| production runtime file-I/O audit | **PASS** | suspicious_runtime_file_authority=0、frequent_report_write=0 |
| `git diff --check` | **PASS** | 差异格式与空白检查 |
| Mermaid CLI 渲染 | **17/17 PASS** | 全部图可解析并生成 SVG；组件、正常时序、部署、ER、风险状态图另渲染 PNG 后目视检查 |
| 核心表名与定义核对 | **PASS** | 正文完整 `brc_` 表名可在当前 SQLAlchemy metadata 找到；不是生产 schema 检查 |

### 已存在的架构失败

**失败检查：`test_test_modules_do_not_import_other_test_modules`**，报告：

1. `integration/test_owner_income_statistics.py` 导入 `integration.test_owner_console_read_repository`。
2. `unit/owner_console/test_google_oidc.py` 导入 `unit.owner_console.test_auth`。

本轮用 `git show <阅读基准>:<path>` 取出原始检查及两处源文件，在独立本地快照中调用原检查，复现同样两条违规；同时确认当前三文件与基准逐字节相同。**这是已验证的基准问题，不是本轮新增文档回归**。本轮没有为了全绿而放宽检查或移动无关测试夹具，记录为仓库既有检查阻断。（来源：[原始检查](../../tests/trading_kernel/architecture/test_test_support_boundaries.py#L21)）

### 图表复现

渲染工具独立安装在被忽略的 `.local/project-knowledge/diagram-tools/`，使用本机 Chrome；未改变项目 package 文件或 lockfile。每份含图文档以如下方式渲染，目录和文件名替换为相应页面：

```bash
.local/project-knowledge/diagram-tools/node_modules/.bin/mmdc \
  -i docs/knowledge/SYSTEM_OVERVIEW.md \
  -o .local/project-knowledge/render/SYSTEM_OVERVIEW.md \
  -a .local/project-knowledge/render \
  -p .local/project-knowledge/render/puppeteer.json -j 1
```

`puppeteer.json` 只配置本机 Chrome executablePath；这是本轮临时验证配置，不是 runtime authority。生成图片与渲染副本未提交，维护源仍为各页 Mermaid。后续本机可用正式 Mermaid CLI 和对应浏览器路径重新渲染。

## 按需求逐项完成审计

| 原始交付要求 | 交付位置与证据 | 本轮完成判定 |
| --- | --- | --- |
| 知识地图与分阶段阅读路线 | [README](README.md) 的两遍阅读、按问题导航 | 完成；入口与回链检查通过 |
| 文档盘点、权威、有效性与差异 | [SOURCE_AUTHORITY](SOURCE_AUTHORITY.md) 的完整现行白名单、历史类别、D1–D6 | 完成；差异及其未裁定边界已记录 |
| 中英文术语及关系 | [GLOSSARY](GLOSSARY.md) | 已关联定义与易混淆边界 |
| 总体设计、模块职责、依赖和决策解释 | [SYSTEM_OVERVIEW](SYSTEM_OVERVIEW.md) | 已覆盖组件、策略族、Worker、数据流和设计分析 |
| 上下文、组件、部署、流程、时序及数据图 | 总体设计、主链路和各专题 | 完成；17 张 Mermaid 全部成功渲染 |
| 完整交易链和异常恢复 | [TRADE_LIFECYCLE](TRADE_LIFECYCLE.md) | 正常、无交易、unknown、partial、重启及终态；本地 165 PASS 支撑对应场景 |
| 动态选币专题 | [DYNAMIC_SELECTION](DYNAMIC_SELECTION.md) | Generic、Comparison、Vacuum、正常/恢复及 SOR-1H 分支 |
| Owner 控制专题 | [OWNER_CONTROLS](OWNER_CONTROLS.md) | V2/API/鉴权、幂等、异步平仓、暂停语义 |
| 风险与退出专题 | [RISK_AND_EXIT](RISK_AND_EXIT.md) | 定量公式、冻结 Profile、实际风险、保护和故障 |
| 数据库状态模型与事务 | [DATA_MODEL](DATA_MODEL.md) | 核心 ER、数据字典、状态族、约束和查询示例 |
| 部署、恢复及故障定位手册 | [DEPLOYMENT_AND_RECOVERY](DEPLOYMENT_AND_RECOVERY.md) | tracked 拓扑、R0–R4、迁移、阶段恢复、六类诊断路径 |
| 模块代码导读、接口和测试映射 | [CODE_AND_TEST_INDEX](CODE_AND_TEST_INDEX.md) | 主链路与专题代码表，五个问题贯通验收 |
| 维护机制与证据等级 | 本页及新架构检查 | 已建立更新触发、决策记录与验证规则 |

## 最终状态、阻断与安全证明

**知识库交付完成**：12 份中文材料、17 张可维护图、统一入口、定义链接、测试映射与维护规则均已建立并检查。独立分支为 `codex/project-knowledge-system`；原有文档未移动或删除，新增内容可通过 Git 差异单独审阅或撤销。

**阻断与解释边界**：知识库交付本身没有待写章节或待解析图表。全仓架构检查仍有上述 D6 基准失败；D5 的契约与实现差异仍需正式语义裁定。本轮已提供双方原始依据和实际覆盖，不把它们悄然消除，也不以文档交付宣称生产验收完成。

**安全证明**：本轮 Git 变更范围仅为根 README、docs/README、本知识库和新增文档架构测试；生产源码、迁移、策略配置、服务单元、资金与权限文件均无改动。验证只创建或删除本地测试库，没有生产数据库 schema 操作、部署、服务重启、生产控制写入或交易所请求。知识库仅供人阅读，不加入 `docs/current` 白名单或任何 runtime loader。
