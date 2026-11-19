# 手机协作缺陷修复：本地集成验证

## 授权与边界

Owner于2026-11-19批准开始集成测试，要求**部署前等待确认**。该授权替代前一阶段“集成测试前停止”的阶段限制。

本轮在`codex/manual-management-recovery-v2`的暂存差异上验证，工作区原实现与前轮P2修复保留。只连接独立本地`brc-manual-pg`／`127.0.0.1:55434`，测试数据库按用例隔离并清理。外部交易所由记录型协议桩替代；未接触生产、未部署、未操作Owner开关或真实订单。

这是本地集成证据，不是冻结提交的正式发布认证；当前生产身份仍只由[主路线图](../../current/MAIN_CONTROL_ROADMAP.md)记录。原修复范围及停止点历史见[审查记录](2026-11-19-owner-cooperation-defect-repair-review.md)。

## 新增集成覆盖

| 场景 | 实际覆盖的链路 | 边界 |
| --- | --- | --- |
| Runner手机减仓 | 真实PG生命周期进入Runner并退休TP→真实手机HTTP请求→持久预览→原始协议采集→P-256签名受理→持久命令派发→closePosition保护转换→成交证明→余仓自动续管 | 有且只有一次OWNER_REDUCE，重复推进不重发；独立连接确认命令claim先提交；旧TP历史成交保留，operation完成后释放 |
| 缺少保护 | 上述同一PG／HTTP链路中，较新当前订单快照缺少Stop | 明确拒绝预览，不创建减仓命令，不发送测试桩写入 |
| 核算窗口 | 正常闭仓及提前PositionFlatConfirmed→正式VerifiedExitClosed→结算／原Review→补证据预览 | 使用真实退出成交时间6000，而非较早空仓观察5000；不改旧Review、预算、敞口或命令；仍需原有Owner批准才追加修订 |
| Feed时序 | 实际PG心跳在请求取时后提交；同一严格回放拒绝、实时时钟通过 | 过期租约和错误commit仍拒绝；历史gap恢复后不重新计入故障时长 |
| Overview快照 | 真实RR事务、实际账户／策略／能力关联、Feed当前行及注入时钟 | 请求旧取时触发拒绝，快照后取时就绪；输出observed_at_ms与快照判定一致 |

新增文件为`test_owner_runner_raw_recovery.py`、`test_review_verified_window.py`及记录型协议桩`support/owner_raw_protocol.py`；Feed用例并入`test_readonly_feed_clock.py`。

另追加原始协议专项：普通TP与条件Stop使用同一数字订单号时，仍分别匹配命名空间和成交状态，避免把先读到的Stop误当作TP。

## 测试中处理的差异

1. 旧Overview测试断言11次查询；当前实现复用Feed同一行，实际10次。已更新精确次数和后续索引，原事务、限定范围、当前Review关联、limit和禁止窗口全扫等断言保留。
2. HTTP测试替身未接受新增`clock_ms`参数，已跟随真实repository接口取时；没有修改生产接口或放宽业务行为。
3. 新增记录型协议桩补齐真实协议要求：独立InstrumentRules、有效TP成交均价、closePosition订单数量0、真实手机会话签名，以及`runner_continuing`为已完成operation的产品语义。该部分属于新增测试自身建设，不列作生产缺陷修复。

## 验证记录

工作证据保存在`.local/owner-repair-integration-20261119/`，不纳入版本控制，也不作为生产运行权威。

| 检查 | 命令或入口 | 状态 |
| --- | --- | --- |
| 单元／架构 | `scripts/local/manual_pytest.sh tests/trading_kernel/unit tests/trading_kernel/architecture -q` | 2490通过，49.00秒 |
| 手机原始协议链路 | `test_owner_runner_raw_recovery.py` | 2通过 |
| 核算证明到持久预览 | `test_review_verified_window.py` | 2通过 |
| Feed与Overview数据库时序 | `test_readonly_feed_clock.py` | 5通过 |
| HTTP接口 | `tests/trading_kernel/interfaces/test_owner_console_http.py` | 54通过 |
| 前端组件／交互 | 现有Vitest对V2的30个测试文件，使用本地测试配置；不启动任何生产代理 | 148通过 |
| 完整Integration | 4个pytest工作进程、按文件分配，沿官方组合排除4个周期资源用例 | 2101通过，3568.43秒 |
| 完整Full-chain | 2个pytest工作进程、按文件分配 | 77通过，239.61秒 |
| 静态分析／构建 | Ruff、Mypy、TypeScript／Vite、手机六文件打包、JS语法 | 通过 |

新增路径最终复核`test_owner_runner_raw_recovery.py`／`test_review_verified_window.py`／`test_readonly_feed_clock.py`合计**9通过**，包含在主体集合启动后补入的Overview数据库时序用例；该追加用例已实际运行通过。当前清单为2102项常规集成＋4项周期资源检查；主体2101与追加9有重叠，不相加冒充独立样本。

普通TP／条件Stop同数字订单号的原始协议专项20通过；新增该参数后再跑单元／架构集合，最终为2490通过。

前端Vitest配置与日志仅在上述本地证据目录。它使用现有安装依赖，不新增前端产品依赖。所有pytest并行工作进程均只使用本地独立数据库；并行用例不能替代现场资源和自然成交验收。

## 尚未声称通过的验收

- 冻结精确提交的联合发布认证。
- iPhone真机长期会话、后台回收及通知实际送达。
- 自然交易所Stop／减仓交错。
- 本批部署后生产功能与历史核算预览／批准应用。
- 周期资源压力专项。

## 当前状态

**本地集成、全链路、接口、前端和静态检查均通过，已停在部署前等待Owner确认。** 本轮没有新增生产逻辑修复；只新增协议／数据库回归并更新两处旧测试预期。

改动已暂存，仍未形成新提交、冻结候选或生成精确提交的联合发布认证。未部署、未重启生产服务、未执行真实交易或自动重放用户此前失败的减仓。
