# MA-OPS-CLOSURE-01 本地实施证据

## 范围

Owner已明确要求修复五项缺陷。本轮在`codex/manual-operational-closure-v1`实施，继承已合入的数字语义修复与TP1／MA50能力。部署和生产历史补账仍等待Owner明确确认；没有服务器、生产PG、真实订单或真实通知写入。

## 实现与边界

| 工作包 | 实现 | 不改变的权限 |
|---|---|---|
| F1 | 显式ExternalExitOrderReference、成交来源互斥、实际订单核验、系统／外部成交去重、终态补证据队列与Review revision | 不伪造Command，不放宽数量守恒，MANUAL零订单写入 |
| F2 | 单一5分钟closure窗口、首次等待／最后核验／升级／解决时间、同episode不降级、完成与盈亏完整分别通知 | worker故障阈值独立，未核实状态不宣称全恢复 |
| F3 | 精确health／sizing拒绝码、同事务持久化bounded failure basis、Owner详情读取 | 只改真实原因记录，不放松风险／资金／占用门禁 |
| F4 | 止损存在性、数量不匹配和已核实覆盖分开；API／前端／通知一致 | 仍保守计量风险，超量止损不假设可执行 |
| F5 | 按attempt保存失败stage／code／安全异常类型与有界事实；认证和刷新因果引用；Session等待分类 | 不把成功覆盖失败，不复制凭据，不恢复退休SOR或暂停策略 |

终态补证据通过现有Reconciliation每轮一个有界对象读取，网络在事务外。先生成可复核预览；真实Owner通过现有TOTP创建准确request／digest授权后进入approved队列，由Kernel追加Review。Owner API只写授权／请求，不成为第二个核算writer。重复提交、重复应用、前版变更均有明确验证；原记录、terminal与预算释放保持。

失败诊断保留在PG的append-only历史中，单条basis限制12KB、数据库约束16KB，读取每页最多100条并有subject／stage时间索引。健康常态不追加诊断；失败历史按attempt增长，不以去重通知代替丢弃诊断。当前不自动删除故障历史，保留策略为完整审计留存；后续保留期限调整不得由runtime读取Markdown或删改既有证据冒充恢复。

## 已执行的反例与回归

- closure在3分钟／5分钟入口交错的RED已经观察；统一5分钟且告警时间不回填为首次等待，重启／stale调用不降级，PG同episode仅一次升级通知。
- 超量止损RED已经观察；存在的止损保留真实数量和价格，覆盖unknown，不变成确定“没有保护”。
- 原始DOGE订单／成交经过当前CCXT解析，再进实际适配器和严格经济计算；32811=16405+16406，多源重复去重。错订单／side／时间、缺手续费和截断响应明确失败。
- Review revision预览不改核算；缺授权拒绝；真实Owner角色／TOTP、重复请求、补齐后仍MANUAL、只追加一次、预算／命令完全不变均验证。
- 0020→0021逐表源列保全与暂停／残余lane／风险占用拒绝反例通过；原0019→0020独立迁移反例继续保留，不以新的head冒充其目标。
- 四进程资源旧断言已改为当前合同：到期Dynamic交接时旧Static不得消费close。四持久角色、1CPU／1GiB、600秒预算与零Signal／Ticket／Command／开放Incident断言保留，four_processes与idle_static_four串行2项通过（76.25秒）；不声明24小时服务器soak。
- 前端核算差异／TOTP未知请求、保护与原因映射145项通过；TypeScript与production build通过。早期后端完整链76项通过，最终精确候选仍须正式认证。

## 现场与历史限制

本地DOGE数值／协议形态回放不冒充已经补齐真实生产盈亏。历史只读快照具备订单量／均价，但不包含完整原始trade IDs与所有费用证明；可生成部分差异预览，不能凭此批准完整净盈亏。未来正式现场需准确GET-only补证据并提供逐票差异，Owner复核后才应用生产Review revision。

旧1024次认证和19:00 BNB拒绝缺失的历史原因无法倒推；保留unknown。自然AUTO／App接管、手机通知回执及当前首尔运行状态不由本地回归代替。

## 最终认证

新schema为`0021_manual_operational_closure`，冻结后执行新SHA完整R4、Owner API及static认证。最终状态以原生manifest及本地验收报告为准，早期局部通过不作为完整证书。
