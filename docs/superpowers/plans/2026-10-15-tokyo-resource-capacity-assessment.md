# BRC Tokyo 只读资源与容量评估

**文档性质：2026-10-15 的一次性调查与容量分析记录，不是当前生产状态权威，不构成优化、部署或参数变更授权。** 后续运行身份与状态以 [`MAIN_CONTROL_ROADMAP.md`](../../current/MAIN_CONTROL_ROADMAP.md) 及直接生产事实为准；ALPHA-02 范围见[研究规划](2026-10-14-brc-alpha-research-status-and-plan.md)。

采集日期：2026-10-15，北京时间。主采集窗口10:19–10:28；主机30秒连续采样10:21:24–10:21:54。调查范围：现有Tokyo机器、四个Kernel Worker、Owner API、BRC PostgreSQL、有界日志和当前生产路径。只调查，不优化、不发布、不改配置或仓库。报告中事实与情景假设分开。

## 结论

**当前硬件足以继续ALPHA-02开发，并支持以Signal为单位去重、按封闭K线推进、带额度的初期运行；没有证据支持现在升级服务器。应先处理轻量调度/日志问题，再扩大研究量。不能据此宣称24小时高峰或长期容量验收已通过。**

理由：整机2核/3.32GiB，短时CPU忙碌23.4%–32.3%，可用内存约1.2GiB，根盘约25GiB可用。BRC数据库仅57.27MiB，Shadow无到期积压。较明确风险是Worker共用1核/1GiB额度、Observation串行服务观察和Shadow、持续重复物化轮询及日志，以及主机上的其他不受限容器。

## 已知事实：服务器资源

|资源|实测|余量/含义|来源与时间|
|---|---|---|---|
|CPU|2 vCPU；load1/5/15=1.07/1.05/0.84|load不是CPU利用率|nproc、uptime，10:19|
|CPU短时|6个约5秒区间忙碌23.36%–32.30%，均值约28.2%|当前约68%–77%空闲，不代表全天|/proc/stat差分，10:21:24–54|
|内存|3399MiB总量；MemAvailable约1245–1259MiB|约36%可用，不用106MiB free误判|free、/proc/meminfo|
|Swap|0|没有Swap缓冲，不代表当前内存不足|swapon、/proc/meminfo|
|磁盘|59GiB，已用33GiB，剩余约25GiB，58%|未接近容量上限|df -hT，10:19|
|磁盘I/O|vda读0.027–1.967MB/s，写0.130–2.466MB/s；区间util5.6%–17.1%；平均每请求耗时约0.7–3.8ms|不是IOPS容量测试，无设备性能基线|/proc/diskstats差分，30秒|
|I/O等待|CPU iowait0.6%–2.9%|未见持续I/O饱和|/proc/stat差分|
|压力|末次PSI CPU some avg60=8.78%；memory some0.33%/full0.11%；I/O some3.75%/full2.82%|有短时争用，非零不等于饱和；PSI不是CPU使用率|/proc/pressure/*，10:21:54|
|Worker资源组|CPUQuota=100%即1核；MemoryMax=1GiB；使用约659MiB；Tasks30/128|内存额度余约365MiB；15秒约用0.242核且无新增CPU throttling|systemctl show、cgroup cpu.stat/memory.events|
|OOM|资源组oom/oom_kill均0；可检索7天内核日志未命中OOM/磁盘错误|仅限保留日志；不能证明完整7天无事件|memory.events、journalctl -k|

没有发现已启用的sar/iostat/atop历史采集，也没有在本次可访问范围取得云监控历史。**24小时与7天CPU、内存、I/O峰值不可得**；journal中的应用次数不能替代资源曲线。没有安装监控或新增常驻进程。

## 当前消耗者

CPU列的Worker值按30秒CPU时间差分，100%=1核；内存为服务cgroup MemoryCurrent。Docker值是独立瞬时样本，不与Worker时间窗强行相加。

|服务|CPU|内存|解释|
|---|---|---|---|
|Observation|20.40%单核|约202MiB|四Worker内主要CPU消耗者|
|Entry|0.35%|150MiB|新ENTRY工作较少|
|Lifecycle|1.67%|145MiB|独立进程；采集时有2个活跃Ticket|
|Reconciliation|1.85%|161MiB|认证、对账、恢复及收尾|
|Owner API|本次未单独差分CPU；ps累计均值约0.1%|153MiB|不在四Worker的1GiB资源组内|
|BRC PostgreSQL|docker瞬时12.85%单核|162MiB|不在四Worker资源组内|
|owner_ai_cpa|docker瞬时20.50%单核|55MiB|同机其他业务，可能竞争CPU|
|owner_ai_new_api|docker瞬时0.02%|99MiB|其他业务|
|其他2个PG容器及Redis|docker瞬时各约0%–0.55%|约108/156/7MiB|其他业务|

Worker当前NRestarts全0；并不代表过去24小时无重启。昨晚有发布停止/启动，也有Reconciliation退出码1失败；当前进程身份都为b8e82fb6b6dc24fdce36c845ac491b801fe561e5、schema0011_orb_session_1h_v1。发布包无.git，因此身份来自运行进程cwd/env白名单及PostgreSQL认证身份；5个被用于分析的部署源文件SHA256与本地一致。未读取或输出凭据。

BRC PG与其他Docker容器inspect显示Memory=0/NanoCpus=0，即未配置独立容器CPU/内存硬上限；不能保证同机其他业务高峰时BRC仍有本次余量。

## PostgreSQL

数据库57.27MiB；业务表连TOAST及索引总计45.23MiB，其中heap23.27MiB、索引15.57MiB（总计还含TOAST/辅助页）。WAL当前32MiB。连接11，其中10 idle，唯一active为本次查询；没有其他活跃长查询、阻塞链或idle-in-transaction。max_connections100，shared_buffers128MiB，work_mem4MiB，autovacuum开启；temp_bytes0；无无效索引。pg_stat_statements未安装，慢SQL日志关闭，track_io_timing关闭，因此无法给出慢查询排名。

|表|统计估计行数|含索引/TOAST物理大小|
|---|---:|---:|
|instrument_selection_member_decisions|3768|5.32MiB|
|facts_current|6349|4.69MiB|
|trade_events|4499|4.07MiB|
|admission_decisions|1493|3.75MiB|
|signal_fact_snapshots|8628|3.13MiB|
|exchange_commands|约1948–1952|2.35MiB|
|signal_events|2043|2.13MiB|
|shadow_outcomes_current|1327|1.20MiB|
|trade_tickets|253|0.74MiB|
|selection_snapshots|157|0.54MiB|
|selection_session_authorities|133|0.55MiB|

行数为pg_stat_user_tables估计，不是全表精确COUNT。Shadow有due(status,horizon_end_ms,lease_until_ms)和Signal唯一索引；生命周期/对账均有status+due索引。不因累计seq_scan次数大就直接判缺索引；部分计数跨旧版本和数月，当前exchange_commands的seq_scan在约186秒内未增加。

10:20:33–10:23:39差分：约21.2提交/秒，WAL生成约8.57KB/s，数据库字节数不变。WAL约0.74GB/日只是短时生成速率外推，会循环复用，**不是每日磁盘净增长**。数据库长期净增长无法从3分钟窗口估算；不拿昨天SQL文本导出大小和今天数据库物理大小作对比。

过去24小时可见PG日志有36次deadlock，最后一次2026-10-14 21:30:37北京；当前统计总deadlocks40，在本次两次采集间未增加。当前运行版本开始后未发现新的deadlock日志；这是锁顺序/并发修复证据范畴，不是硬件升级依据。当前无阻塞；历史问题不能凭短时无复发宣称长期根除。

## 应用调度与积压

### Observation与Shadow

- 106个observation_enabled scopes，其中当前五个实盘策略共76个，旧SOR和TradFi各14/16个仍处于观察；不代表允许其ENTRY。
- Observation主循环每次领取1个scope，完成后等待5秒；有到期scope时不领取Shadow。
- Shadow每次最多1个，只有horizon到期才投影；1h读取24根封闭K线，15m上限96根；底层请求limit+1后筛封闭根。终态不保存所有K线原文，而保存有界指标。
- 1327个Shadow：1315已完成，12 pending，均未到horizon；当前到期积压0。
- 最近24小时30个完成样本：horizon到完成p50约11.8分钟，p95约100分钟。最大延迟样本发生昨晚部署/停机段，不能将其归因为当前硬件不足。
- 当前版本09:30后观察日志按scope关联：活跃五策略完成延迟p50约148–366秒，p95约351–537秒；SOR-1H p50约325秒、p95约459秒。值为K线收盘到任务完成，含排队、网络、计算、恢复；不是每次策略计算耗时。当前scope到期积压0，说明最终消化，不代表整点实时性理想。
- 106条同时到期任务，仅每次5秒等待就需约9分钟量级，尚未加入网络及计算；历史scope公平调度还可能影响先后顺序。增加CPU不能直接消除人为轮询等待。

### Dynamic Selection

四通用策略每24个候选：MI/MPG每小时，CPM/BRF2每4小时。正常每天60个批次、1440个候选窗口；每窗分别13/14/25/73根1h线，合计约29664根候选输入/日，不含资格查询、重试和materialization。SOR-1H每天一轮24候选×96根15m线，另约2304根输入。每个选择批次并发默认6；各逻辑循环共享一个Observation进程及公共行情client，并发/限速会互相影响。新增Signal路径不应重复执行Selection。

本次5分钟日志833条/372840字节，约821条来自物化重复状态：旧SOR OWNER_PAUSED、SOR-1H TERMINAL_AUTHORITY_ALREADY_COMMITTED、CPM/BRF2相同ACTIVE_NEW身份，以及MI/MPG当前close已消费的重复待处理/阻塞。某些终态被映射为advanced而未进入idle日志节流。按这5分钟的消息体速率外推约108MB/日，**只是消息体估算，不含journal元数据、压缩和其他服务**。实际journal2.2GiB，Docker容器日志目录737MiB；释放历史日志不在本任务范围。

### Lifecycle/Reconciliation

独立常驻进程，每轮最多一个有界动作，poll分别2/5秒；关键/例行对账、认证等在一个Reconciliation进程调度。当前2个SOR-1H Ticket在调查中自然进入Runner保护，未解决Incident0。最后瞬时采样生命周期due偏差约-0.75/+1.64秒，对账约落后4.7/12.5秒；有处理进展，无法仅凭due偏差推断异常或给出完整延迟分布。调查未为验证而调用交易所接口。

## ALPHA-02影响：假设而非已上线能力

已有五策略Signal，最近24小时共14个：BRF2=5、CPM=3、SOR-1H=6、MI/MPG=0；昨日报表四原策略合计24个/自然日。刚发布、停机、市场和Universe变化使这些数据不是稳态吞吐基线。不能把Signal数低当成服务器处理上限。

以“每个唯一Signal一个24h研究样本、复用现有Signal且与现有Shadow去重”为前提：

|情景|样本/日|24根1h路径输入/日|若到期补读的一任务一次K线请求|若每样本最终记录含索引2–5KB的新增存储|
|---|---:|---:|---:|---:|
|初期额度假设|50|1200|至多约50次成功请求/日，另计重试/冷启动|0.10–0.25MB/日|
|放大情景|200|4800|约200次/日|0.40–1.00MB/日|
|压力情景|1000|24000|约1000次/日|2–5MB/日|

2–5KB是为增加阈值/路径字段预留的工程假设，当前Shadow平均逻辑行约432B、物理含索引约945B/条。1000样本/日也只是约0.73–1.83GB/年最终记录；不能把总盘剩余25GiB都视为研究可用，日志、发布、其他业务仍增长。

当前成功一次Shadow从创建到完成约：1 INSERT（Signal去重）、1 SELECT FOR UPDATE领取、1 UPDATE设置Claim、1 UPDATE终态，另加事务/身份读取，约3个事务；ALPHA-02复杂性未知，可先按4–8业务SQL/任务预算，50/200/1000任务分别200–400/800–1600/4000–8000语句/日，不含空轮询和重试。远小于当前约21TPS的轮询事务量。

若复用自然收到的封闭K线，可减少新增API调用，但现有public source只有Product短缓存，没有通用共享K线缓存；“研究零新增API”需要设计实现，不能宣称现成。若要求逐根推进，24h1h样本有24次投影，200/1000样本就是4800/24000次更新/日。若仍然每样本逐根单独拉行情，也可能达到4800/24000请求；应按instrument/timeframe/close去重复用。同一行更新产生WAL/死元组，不等于存24份；若每根追加2–5KB快照，1000样本则48–120MB/日、17.5–43.8GB/年，会明显改变磁盘判断。

CPU：纯路径计算为O(样本×K线)，24根/样本与现有选择运算相比不大，但无profile不能承诺精确CPU百分比。内存：单个/小批量投影应有界，不能将一天全部路径常驻；当前Worker内存余约365MiB，不能默认再起一个150–200MiB Python服务没有代价。API与排队比最终存储更值得关注。现有单任务5秒循环若1000样本同时到期，仅轮询等待即约83分钟；这是队列结构压力，不是日平均CPU不足。

## 最多三项优先措施（本轮均未实施）

1. **必要：把无变化物化终态归入空闲/变更才记录，并避免无效重复协调。** 当前已有直接重复身份和日志证据。不是关掉真实故障日志，也不跳过授权刷新；先删掉可证明无效的工作。
2. **ALPHA-02上线前必要：给研究工作单独的有界逻辑队列、处理额度和超时预算，沿用现有进程与官方内核边界。** 交易观察/保护/对账优先；按唯一Signal去重，按instrument/timeframe/close复用自然行情；每轮小批量但明确yield。处理延迟和重试数可见，不能永久只靠“碰巧空闲”。目前无需新增Worker或放宽共享资源额度。
3. **作为初期运行约束必要，大规模清理暂不必要：冻结样本/日、最长horizon、每任务投影/重试上限与研究保留期限。** 初期示例200样本/日、24h路径、最终摘要长期保留而原始重复路径不保存；数值属于待设计预算，不是已批准配置。只保留必要检查点，避免逐根重复追加完整状态。无需现在清库、重建索引或升级磁盘。

## 历史与证据边界

- 没有24小时/7天CPU内存IO时间序列，本次不能签署高峰容量保证。
- 所有pg_stat累计计数跨旧发布/很长时间；只有两次差分可作为本采样速率。
- 最近24小时有发布暂停和旧版本错误，不能直接外推稳态生产。
- 只能给有额度运行判断，不能给ALPHA-02尚未冻结设计的精确CPU/时延容量。
- 无数据库净增长历史基线，不给“还可以安全运行几年”的伪精确结论。

## 关键命令与SQL摘要

- `nproc; uptime; free -m; swapon --show; df -hT /`。
- 7次/proc/stat、/proc/diskstats、/proc/meminfo、/proc/pressure/*差分，共约30秒；systemctl show和cgroup短窗差分。
- `docker stats --no-stream`；Docker inspect仅白名单资源/状态字段。
- `journalctl --since ... -u ... -o json`有界读取后仅汇总；PG日志仅统计错误及时间，不输出原始SQL。
- PG全部在readonly transaction，`SET LOCAL statement_timeout='4s'`、`lock_timeout='200ms'`。查询`pg_database_size`、`pg_stat_user_tables`、`pg_stat_database`、`pg_stat_activity`、`pg_stat_wal`、`pg_stat_bgwriter`、`pg_indexes`、`pg_settings`，并对小型运行表做7天/24h有界聚合与最多100条样本。
- `SELECT status,evaluation_kind,count(*) ... FROM brc_shadow_outcomes_current GROUP BY ...`及到期条件；Signal按occurred_at_ms限制24h/7天。

## 本地证据文件

`host.json`、`runtime_host.json`、`pg_metadata.json`、`pg_runtime.json`、`pg_rates.json`、`pg_final.json`、`logs.json`（旧日志窗口有上限，仅代表所列覆盖时间）、`recent_logs.json`、`log_detail.json`、`observation_lags.json`。原始证据与采集脚本保留在本地目录 `/Users/jiangwei/Documents/brc_capacity_assessment_2026-10-15/`，不随本次文档提交发布。表格中的来源与关键命令用于解释调查方法；文档本身不能替代原始采样或后续生产核验。

**最终状态：建议继续开发，按额度上线；先做轻量调度优化，不升级硬件。没有实施任何优化、安装、常驻监控、重启、配置调整、部署、数据库写入、迁移、清理、交易所调用或生产代码修改；本次后续仅发布调查文档与索引。**
