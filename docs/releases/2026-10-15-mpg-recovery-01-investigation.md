# BRC-MPG-RECOVERY-01：恢复 Authority 后直接换币失败

## 结论与授权边界

**根因已由生产精确源码、PostgreSQL lineage 和真实PG RED/GREEN确认。**
生产 `b8e82fb6b6dc24fdce36c845ac491b801fe561e5` / 0011 的新成员 Generation
在前任为 GenericRecoveryAuthority、Vacuum 与 Generation fence 相等时选择普通当前收盘激活。
Repository 第1120行仍无条件要求先安装一次 NO_CHANGE successor，拒绝了已完成恢复 rebase
且拥有合法 CurrentFinalCloseGrantProof 的直接换币。2026-09-27的该拦截与2026-10-07新增的
逐重叠成员恢复身份/ARMED证明没有衔接；SQL Authority trigger 已独立验证这种直接激活的
重叠成员 rebase 与当前收盘证明。仅查服务 running 无法发现这条业务失败。

本报告是有时间戳的事故证据，不是生产状态权威。最新运行身份、控制与发布事实仍归
`docs/current/MAIN_CONTROL_ROADMAP.md`，实际行动必须重新只读核验。
Owner本轮只授权只读生产调查和独立本地修复；没有部署、订单、控制、授权或数据库修补。
A+B认证的工作区保持冻结，本修复隔离在 `codex/mpg-recovery-01`，基于生产精确提交，
不包含A/B或0012。没有合入dev或修改生产。

## 已知客观事实：2026-10-15，Asia/Shanghai

数据来源：Tokyo PG repeatable-read / READ ONLY事务、Observation journal、生产源码SHA256
及官方只读 `probe_production_runtime.py`。原始输出保留在主工作区
`.local/mpg-recovery-01/`；数据库URL、交易所凭据不输出。

| 时间 | 事件与精确身份 |
| --- | --- |
| 17:00:00.167 | Generation `44c158021ae4c1df6174a1584c8b5da200a6eef61356c7f327001307dad916e6`创建，Snapshot `01d9c53eaa3a25a39c7f72db194c8d0ff064e7d07b8051d4963265c6f42b7dc4`，epoch `cbec14e95765f21756f5fa65ea25abd159773020e13a1577940585282814d330`，Selection control8 / Owner control1 |
| 17:00:04.419 | 同Generation打开Vacuum，generation/vacuum fenced_at均为1792054804419 |
| 17:00:06.690 | ENTRY排空，Vacuum进入RECONFIGURING |
| 17:10:09.241 | Generation STAGED；旧Universe `universe:c1cc3c53b5eae3425857293f:v41`，旧恢复Authority `authority:recovery:90152fee72be3e56d5e744c50f765f9e63ab6617132c32b5ed2f160c06456097` |
| 17:10–17:30 | journal定位UniverseInstallConflict到 `_activate_generic:1120`；有界窗口匹配513条记录，该数仅代表查询窗口，不能当全部历史次数 |
| 17:30:05.963 | MATERIALIZATION_TIMEOUT → FAILED_CLOSED；失败事件说明本期到期前没有可用未来收盘，Vacuum保留隔离 |
| 18:10:19.586–.748 | 新Generation `0bc35e042500bf55901b83b1f65406e6db1005d2fc75171c154c0e797eb745d4`接管旧Vacuum；保留17:00的原fence/drain，新Generation使用18:10的fence |
| 18:12:57.795 | 新Generation STAGED |
| 18:13:00.258 | 既有 recovered-activation 合法接管：Universe v43、Recovery Authority `authority:recovery:fb4c84829da726fd0280966ec9077b77747660af93dea5fc902949288b27e451`，原Vacuum RESOLVED_ACTIVE |
| 18:22、18:37 | 12个MPG scope仍为 `selection_recovery_not_effective`；新首个合法close为19:00，Authority到20:00；此时不能称新ENTRY已恢复 |
| 18:37 | 官方交易所只读检查32个当前标的：持仓域0、挂单域0，独立多空/Cross；PG活动Ticket、未决Command、非零持仓、开放Incident均0 |
| 18:37 | 非静默Vacuum0、warming/staged0；MI与BRF2仍各有未fence的DESIRED Generation，故不能宣称0012全部静默门槛通过 |

源Authority创建于15:17:04.368，合法close16:00，到期17:00，携带真实recovery proof。
17:00 Snapshot为13成员，旧13成员中保留12，新增DOGE、移除DOT，比较Universe与revision1未变。
生成链已经通过DESIRED阶段的重叠成员rebase保护；17:10的失败是后续Repository无条件
拦截，不能由网络超时、Owner控制改变或成员事实漂移解释。

## 基于事实的分析

1. Coordinator 的fence分支表达的是**当前Generation是否接管旧中断Vacuum**，不能简单把
   “前任是Recovery Authority”解释成同一种recovered-activation。新普通Generation的
   fence相同，没有SUPERSEDED中断链，既有future-close恢复Proof的Python和SQL均要求
   old_fence < new_fence及精确前任事件；直接改分支会生成不合法恢复Proof。
2. 正确的直接接续需要保留源恢复身份和checkpoint保护，同时验证新Snapshot已预提交、
   当前close未消费、旧Recovery首个合法close已到、重叠成员均ARMED、Owner/epoch/
   Selection control/Universe/比较绑定/排空/暖机/lease仍一致。现有SQL trigger再次检查。
3. 超时后MPG/MI一小时周期本期没有下一合法收盘，所以不会凭旧成员立即fallback；保持
   FAILED_CLOSED并等新Snapshot接管是安全行为。18:13的自然恢复证明没有永久死锁，
   但如果下一次成员再变化且前任仍是Recovery，旧代码仍可能重复同一故障。
4. CPM/BRF2也共用Repository，故检查公共边界；SOR-1H走独立ORB激活入口，本次不改。
   生产同时可见其他策略的Authority，不代表其每一时刻都可ENTRY；全局暖机槽仍共享。

## 最小修复

只修改 `src/trading_kernel/infrastructure/pg_universe_repository.py` 的直接继任门槛：
保留 `GENERIC_RECOVERY_SUCCESSOR_NOT_INSTALLED`，仅在已经验证的新当前收盘证明不早于
源Recovery首个合法close、且原身份/逐重叠成员ARMED校验全部通过时允许直接普通接续。
后面的过期/Owner/Universe/比较绑定/lease/CAS/SQL检查保持原样。
恢复身份缺失、checkpoint漂移、未ARMED或无效当前收盘仍拒绝；不会制造NO_CHANGE
Snapshot，不重写Authority，不放松未来close规则，不改材料化超时。
没有迁移、策略/资金/交易经济字段、调度服务、ENTRY或Owner授权变更。

## 验证与证据边界

复用真实PG的完整失败→下一周期recovered target链；新增MPG/MI两个直接成员替换场景，
先在生产基线复现同一第1120行异常，再修复。恢复重叠成员必须通过正常Observation
在合法close看到flat后ARMED；新target必须真实通过暖机与比较投影。
负向在Coordinator已检查后、Repository激活前漂移保留成员checkpoint revision，原错误
必须仍抛出，整个激活回滚。然后重建连接、双并发和重复调用只允许同一Authority。
现有未ARMED守卫、超时、未来Proof伪造、同close、下一周期、安装锁及跨策略用例保留。

| 本地验证 | 实测结果 | 原始日志 |
| --- | --- | --- |
| 同一直接换币场景，生产基线 | MPG/MI各在1120行报错，2 failed（预期RED） | brc-mpg-direct-successor-red.log |
| 最终定向集成：恢复/并发/下一周期/同close/超时/四策略/ORB队列 | 52 passed / 214.20s | brc-mpg-final-integration.log |
| 其中直接成员替换、负向checkpoint、双并发及重启重复调用 | 2 passed / 14.63s | brc-mpg-production-shape-final3.log |
| 全部Unit/Architecture | 1681 passed / 28.28s | brc-mpg-fast.log |
| 全部Full-chain | 58 passed / 111.50s | brc-mpg-fullchain.log |
| 正式Mypy范围 / Ruff / diff | 196源文件PASS / PASS / PASS | brc-mpg-mypy.log、brc-mpg-ruff.log |

上述验证包含分轮重复节点，不累计为完整Integration。生产对照与最终测试原始证据保留在
主工作区 `.local/mpg-recovery-01/`；候选不携带生成报告作为运行权威。
开发验证不等于该修复已通过正式R3；
A+B的旧SHA R4也不覆盖此独立生产修复。

## 恢复与发布顺序

**不需要手工修补数据库，也不需要强平或撤单。** 18:13官方恢复已解除MPG旧Vacuum，
19:00及之后是否正常完成rebase/产生Signal应继续按当前PG与真实close核验，不能提前认定。
建议先审查独立0011修复，冻结其精确SHA并完成正式R3，再另行申请同Schema生产发布。
部署本身仍须当前flat/Writer/Owner控制门槛，不能因P0标签绕过。

A+B的0012发布需本故障状态明确并满足所有新的静止检查；MPG已解除旧Vacuum不代表整个
迁移门槛通过。后续若把此修复纳入A+B，需要重新认证包含修复的最终精确SHA，不能沿用
旧A+B manifest。生产部署及研究采集额度继续分别等待Owner明确授权。
