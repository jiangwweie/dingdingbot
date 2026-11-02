# Generic Owner Recovery 修复与验收记录

## 范围与授权

Owner 授权修复 CPM/MPG；本轮完成本地实现、验证和候选认证，部署前等待确认。
不修改资金参数、策略、Selection、旧 Authority、Owner 授权或交易历史。
生产身份、当前运行状态只由 MAIN_CONTROL_ROADMAP 管理。

## 已证实问题

2026-11-02 的只读 RCA：CPM 独立 Owner 暂停没有正常 drain 调度；失败回退仍
要求源 Owner version 与当前完全相等，未消费真实 Resume 证明。MPG 的
AUTHORITY_GAP 及失败目标早于暂停，原 Resume matcher 不支持这组历史。
恢复错误又被原 MATERIALIZATION_TIMEOUT 遮蔽。
证据保存在忽略的 `.local/cpm-mpg-rca-20261102/`；历史诊断不代替当前运行事实。

## 改动

| 边界 | 修复 | 保留门槛 |
| --- | --- | --- |
| Runtime | 调度无 Generation 的 Owner 暂停 drain，支持提前 Resume | 不开启 ENTRY，不授予 Authority |
| Resume matcher | 支持 gap 已 drain 后的一组连续真实 pause/resume，包含先失败后暂停 | 精确源 Authority、Owner 版本、TOTP scope/time、epoch/control |
| Python 恢复 | 新目标与有效旧池回退使用同一 Resume 证明 | Universe/member/Comparison/freshness 不放宽 |
| SQL 原子提交 | 区分有完整恢复证明的 ACTIVE_NEW/FALLBACK 与普通激活 | INSERT 前态验证、deferred 后态和未来 checkpoint rebase |
| 可观测性 | 返回当前恢复失败原因 | 原失败原因留在 Vacuum/Generation 历史 |
| 0014→0015 | 仅修改函数，完整保全所有源表字段和行 | stopped/flat/quiescent，保留 Owner 已选风险值 |

仅允许源 Authority Owner 版本之后的一组连续暂停/恢复；多轮未消费的控制
变化继续拒绝，不能通过宽松版本比较或手工更新源记录解决。

## 验证设计

1. 真实首次 Dynamic 激活 → gap → Owner pause/resume → 新鲜目标恢复。
2. 真实 gap → 目标失败 → Owner pause/resume → 更新周期目标恢复，覆盖 MPG 时序；
   同时覆盖没有 Owner 控制变化的相同失败重试，完整恢复证明不被误判为普通激活。
3. CPM 独立 pause → 先 Resume → 常驻 worker drain，不改变旧 Authority。
4. 有效旧池完整 fallback 成功；过期旧池明确拒绝，不以新认证延长成员有效期。
5. 错 scope、弱认证、缺 Resume、未来 Resume、错源均被 SQL matcher 拒绝；
   绕过 Python 预检的错误 proof、没有新 Authority 的直接围栏解封被 SQL 拒绝。
6. 0014 非空 seed 通过正式预算接口设为3%后，0015全部字段/行摘要一致；
   3%/9%/6%/50%与 Owner ENTRY 暂停保留。
7. 冻结一次候选，完成完整 R4、Owner API 与 static 精确提交认证；不使用旧SHA证书。

## 发布验收边界

候选认证是本地软件证据，不证明生产恢复。Owner 确认后按官方 R4流程刷新
内外空仓、无未决命令/Incident/预算债务、Selection静止与控制保全事实；
五个写入者互斥停写，正向迁移与官方 promote_entry 保留真实 Owner 意图。
存在自然持仓时保持现有生命周期，不能为本修复强平或切换。

上线后需分别验证新鲜 Snapshot、当前 Authority/epoch/control、Comparison、
合法恢复 close 与真实 checkpoint ARMED，以及精确 scope 的只读准入结果。
没有自然信号时不制造订单；自然接单与 Initial Stop 是另外的实盘证据。
独立 partial TP1缺陷不由本修复覆盖。
