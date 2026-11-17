# 追加审查：升级、提前恢复与条件价故障隔离

日期：**2026-11-17，Asia/Shanghai**。状态：**本批本地修复，仍在整包认证与部署之前**。

> **单Owner范围与本轮更新：** [四项可靠性修复及复审](2026-11-17-four-boundary-fixes.md)记录断线覆盖、续装、跨页面请求与重绑核实；不把DB权限持有者恶意造设备作为首版门禁。整包认证与部署前等待要求保持。

## 1. 范围与审查基线

Owner批准修复追加报告中当前仍存在的三类缺陷。基线为`b83909c1`，复审差异使用`git diff b83909c1..HEAD`。前轮Feed、Stop、Runner、授权证据、限流与手机入口修复保持；不将旧版本问题重复计为当前未修。

本批没有生产上传、服务重启、数据库迁移、策略变更或交易所写入。手机Web与后台完整产品最终联合上线、整包认证及部署前等待Owner审查的要求保持。**不是可上线候选。**

## 2. 根因与修复

| 问题 | 已确认根因 | 本地修复 |
|---|---|---|
| **升级身份切换失败** | 用二元组查找，却把0022/0023/0024写成一个三元组；Alembic通过不代表身份可切换 | 明确注册0022→0023、0023→0024两条边；不放宽原来源身份、暂停、flat或保全检查 |
| **手机提前Resume被旧TOTP约束卡住** | 原0024只扩展最终Resume函数，排空、延后清理、首次恢复函数/触发器仍要求TOTP；vacuum恢复函数另有auth与resume_auth两组分支 | 在未部署0024中逐项扩展8个既有函数的9组别名；仅策略Resume接受真实可信设备证据；保留原TOTP历史、选币/风险配置与retired SOR边界 |
| **附加条件价故障阻断原退出** | 条件价与基础事实一起gather且异常向外传播；无条件价则worker完全跳过maintenance | 条件价独立限时采集并返回结构化blocker；不可用时不提供价格/时效数据，只停止价格转换，保留完整基础事实驱动原失效/时间退出 |

## 3. 升级路径验证

- 在一次性本地PG中从0022或0023建立真实来源结构和Runtime seed，保持新开仓暂停；执行真实Alembic前向迁移，再调用正式`deploy_compatible_upgrade_identity`。
- 核对Alembic版本、Schema metadata与两项Runtime capability的目标schema/commit一致；Owner政策与策略控制的current/events全部原值保留；相同目标再次调用幂等。
- 来源seed错误或账户不符时拒绝，metadata/capability不发生部分切换。
- 未增加活仓迁移、旧schema运行适配或跨产品部署能力。源0023多票终态恢复与历史错误namespace Command的正式编排仍单独待完成。

入口：[升级路由](../../../src/trading_kernel/infrastructure/runtime_authority_seed.py)、[迁移与身份连接测试](../../../tests/trading_kernel/integration/test_owner_cooperation_migration.py)。

## 4. 可信设备策略恢复链

补齐的既有函数包括：

1. `brc_static_owner_resume_authorization`。
2. `brc_orb_owner_resume_matches`。
3. `brc_generic_vacuum_owner_resume_matches`的`auth`及`resume_auth`两组条件。
4. `brc_generic_first_pause_recovery_matches`。
5. `brc_generic_deferred_owner_pause_matches`。
6. `brc_generic_deferred_cleanup_event_guard`。
7. `brc_generic_early_resume_drain_matches`。
8. `brc_generic_early_resume_drain_event_guard`。

迁移按明确函数签名与完整别名匹配；缺少预期原谓词则拒绝安装。匹配不允许`auth`误改`resume_auth`后缀。没有修改已部署0008/0011/0015/0023迁移。

验证使用真实FastAPI手机接口：独立绑定→nonce→P256签名→策略Pause/Resume→Kernel排空/物化→数据库匹配函数及INSERT触发器。覆盖四个Generic策略、Static/Dynamic、提前恢复与延后清理，保留原TOTP及损坏证据回归。

**反例**：仅写`trusted_device_session`强度、没有已关联的签名来源，不能完成排空。数据库函数扫描确认没有遗漏的裸策略Resume/TOTP谓词。SQL检查不是P256验签替代，真实接口仍完成密码学校验与证据绑定。

入口：[0024授权扩展](../../../migrations/trading_kernel/versions/0024_owner_cooperation.py)、[手机静态恢复测试](../../../tests/trading_kernel/integration/test_static_owner_pause_recovery.py)、[实际物化链测试](../../../tests/trading_kernel/integration/test_generic_selection_snapshot_repository.py)。

## 5. 条件价可用性边界

- 新增`TicketLifecycleFacts.contract_price_blocker`：timeout、transport_unavailable、invalid_protocol、identity_or_time_invalid。不能同时携带可用条件价。
- 附加请求默认最多1秒；worker进一步限制为原事实采集超时的四分之一与1秒的较小值。该附加请求不占满原外层超时窗口。
- 超时、连接错误、过期、错symbol、缺字段、NaN或浮点金额均不触发价格转换，也不使用旧价、标记价或历史高低点顶替。
- 仓位、成交等基础事实缺失仍报错，不因附加请求可降级而放宽。取消任务仍传播，不包装为正常不可用。
- 价格转换失败可通过worker detail返回具体blocker；原持仓保护不会被撤销。完整事实下，原失效/时段/持仓时限退出仍先于价格转换判断。
- 对已经关闭的`OWNER_REDUCE`派发门和手机持仓capability未做启用变更。

测试直接使用原始REST形状与真实适配器输出进入PG maintenance，分别证明：条件价超时/过期/非法时仍生成原失效退出；超时并到达时段上限时生成`session_expired`；缺必要仓位事实仍拒绝。

入口：[行情适配器](../../../src/trading_kernel/infrastructure/venue_adapter.py)、[事实合同](../../../src/trading_kernel/application/runtime_facts.py)、[实际减仓后生命周期测试](../../../tests/trading_kernel/integration/test_owner_reduction_recording.py)。

## 6. 本地验证记录

| 集合 | 结果 | 证据 |
|---|---|---|
| 单元与架构 | **2343通过** | `.local/review-followup-20261117/unit-architecture.log` |
| 迁移/身份、Static恢复、减仓续管及既有Lifecycle/worker | **77通过** | `pg-regression.log`；针对性文件，不是完整Integration portfolio |
| 物化暂停/恢复专项 | **48通过** | `materialization-regression.log`；含真实手机及原TOTP/损坏证据场景 |
| 既有兼容身份切换反例 | **3通过** | `identity-existing.log` |
| Ruff / Mypy / diff | **通过，Mypy 276源文件** | 本地命令输出 |
| 整包Integration / Full-chain / Kernel R4 / API / Static发布认证 | **未执行** | Owner审查门保持 |
| 生产／交易所变更 | **零** | 无上传、部署、重启、迁移或真实订单 |

不同集合有重叠，不加总作为产品认证。客户端真机、Hedge交错持续保护、完整operation runner、全部手机操作和源账户正式恢复仍需后续工程及证据，不能由本批通过推定完成。

## 7. 当前复审位置

本批修复完成后停下等待Owner复审。业务参数、MA50、选币模式、策略收益结构和风险上限保持；没有需要Owner重新选择的业务规则。完整发布仍需完成剩余工程、获准整包认证并单独等待部署确认。

相关：[前轮缺陷修复](2026-11-17-gemini-review-fixes.md)、[首轮交接](2026-11-17-owner-mobile-review-handoff.md)、[统一实施计划](2026-11-16-seoul-recovery-and-cooperation-implementation-plan.md)。
