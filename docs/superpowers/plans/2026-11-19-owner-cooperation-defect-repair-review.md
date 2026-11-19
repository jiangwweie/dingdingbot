# 手机协作与核算缺陷修复：集成测试前审查

## 当前边界

**阶段更新：Owner于2026-11-19批准开始集成测试，当前停止点为部署前。** 集成结果与后续边界见[集成验证记录](2026-11-19-owner-cooperation-integration-results.md)。以下保留集成前审查时的阶段事实。

Owner要求：本轮发现的缺陷、价格精度修改和操作指南一起处理，**集成测试前停止，确认后再继续；部署另须Owner确认**。

本轮仅本地实现、单元／架构检查、静态分析、前端构建及无后端界面查看。不运行PostgreSQL专项、接口联调、全链路、正式联合认证或生产写入。不重试用户此前失败的减仓，不修写生产历史记录，不调整策略参数、风险、容量、选币或认证门禁。现有生产身份仍以[主路线图](../../current/MAIN_CONTROL_ROADMAP.md)为准。

## 实现范围与审查入口

| 对象 | 已实现行为 | 主要文件 |
| --- | --- | --- |
| Runner手机减仓误拒 | 没有活动TP订单时保留Aggregate已记录成交量，不再返回0；有活动TP却缺少精确来源时拒绝 | `owner_position_source.py` |
| 相邻事实缺陷 | 当前TP快照必须与此前精确查询一致；消失、变价、成交变化、重复、错误身份均不再冒充一致事实；两种采集入口共享检查。明确校验仓位数量符号、TP时效类型和订单命名空间 | `owner_tp_snapshot.py`、`owner_position_source.py`、`owner_reduction_source.py` |
| 其他持仓操作预览 | 收紧、改止盈、全平等冻结前检查TP身份和累计成交量，改变时由原生命周期先记账，再重新预览 | `owner_position_operation.py` |
| 历史核算窗口 | 有正式VerifiedExitClosed时优先使用证明的最后退出成交时间；先后关系按证明内真实入场／退出成交校验，本地入场确认时间不作成交下界；没有证明时仍使用原观察窗口；保留数量、身份及证明时间边界 | `review_window.py` |
| 独立前端发布 | 核对Kernel/API的commit和Schema标记，再与数据库元数据、Alembic和能力认证逐一绑定；去除仅适用于旧Schema的硬编码；空认证集合拒绝 | `deploy_manual_static.py` |
| 管理就绪误报 | Overview在取得RR快照后取时；真实Entry和发送门在读到Feed后重新取时，读取接收队列后再次核验租约；显式回放仍按传入时刻严格拒绝未来数据 | `pg_owner_read_repository.py`、`overview.py`、`pg_management_feed.py`、`management_health.py`、Entry/dispatch/Feed调用点 |
| 虚增故障时长 | 最新连接转换已恢复时，不把旧gap或epoch启动当成当前持续中断；真正租约过期仍以租约终点计时 | `pg_management_feed.py` |
| 桌面旧状态常驻FRESH | 总览、控制和持仓15秒有界刷新，回焦和重连重读；旧响应超过20秒降为滞后、60秒为不可用；不抬高后端已有不可用／矛盾状态 | `useOverviewData.ts`、`overviewSnapshot.ts` |
| 手机价格精度 | 价格以十进制字符串展开、去无意义尾零和分组，不先转换为浮点数，不统一保留两位；覆盖持仓、委托、预览和结果保护价 | `frontend/owner-mobile/app.js` |
| 操作指南 | 持仓页轻量“操作帮助”→六类意图→影响、折叠示例→当前持仓选择／原操作表单。表单内按需查看；帮助不发API交易请求；能力、预览、签名确认和后台原链不变 | 手机`app.js`／`styles.css` |
| 独立原型 | 原模拟页面一并保留；它的模拟表单和提交结果不会进入真实手机产品 | `docs/prototypes/mobile-operation-guide-v1/` |

手机协作行为仍遵循[既定执行合同](../specs/2026-11-16-owner-cooperative-execution-v1.md)：系统内日常操作后自动续管；不开放放宽止损；外部App真实干预仍按现有归属处理；没有新增真实下单通道。

## 已完成验证

- 已观察到失败再实现修复：退休TP历史成交丢失、活动TP来源缺失、仓位符号矛盾、当前TP快照矛盾、调整预览TP变化、核算窗口取早、发布Schema失配、读取时钟与旧缺口、手机帮助入口。
- 单元验证使用纯逻辑、内存协议Reader、真实JS的Node VM、TS纯函数和受控时钟，不连接生产数据库或交易所。
- 前轮基线执行`scripts/local/manual_pytest.sh tests/trading_kernel/unit tests/trading_kernel/architecture -q`：**2,482通过，43.88秒**。下面P2修复后采用相关专项回归，没有将该旧结果冒充新差异的全量结果。
- Ruff通过；Mypy检查294个源文件通过；前端TypeScript／Vite构建通过；JS语法和`git diff --check`通过。
- 手机六文件静态打包；本地展示副本仅使用虚拟持仓，禁用API请求；无后端地查看了帮助目录与详情。
- 当前无后端本地预览为`http://127.0.0.1:8768/`；截图保存在`.local/owner-repair-ui-preview/operation-guide.png`。展示数据为虚拟样例，不能当作生产状态；原型目录另行保留。

可复核本地日志：`.local/owner-repair-unit-architecture-final.log`、`.local/owner-repair-focused.log`。它们是工作证据，不是生产运行权威，不纳入版本控制。

### 复审P2：入场确认时间与成交时间混用

- 原校验错误地要求`proof.exit_time_ms >= entry.occurred_at_ms`。后者来自本地确认／补记，不能作真实成交下界。
- 修复前新增4个失败用例：EntryFilled／EntryPartiallyFilled，真实入场2000、退出3000、本地确认3500／4500。
- 修复后重新验证完整VerifiedExitClosureProof，由证明内真实成交记录验证先后和数量守恒；移除上述错误比较。保留Ticket身份、入场数量、唯一证明和退出不晚于闭仓记录的校验。
- 新增身份／数量不符及真实成交时间倒置的拒绝回归；不存在闭仓证明时的旧观察窗口行为保持原样。
- **129项单元／内存专项通过，1.80秒**，覆盖核算窗口、证明、核算经济、复核worker、减仓采集／预览、Feed、静态发布和手机故障回归。Ruff、相关Mypy、暂存差异检查通过。日志：`.local/owner-repair-p2-entry-confirmation.log`。
- 本轮仅3个文件更新：窗口、对应单元测试、本审查文档。未运行PostgreSQL、全链路或联合认证，未提交、冻结或部署；继续停在集成测试前。

## 等待Owner确认后执行的集成验证

以下均**尚未执行**。

| 组 | 需要证明的跨层行为 | 场景与失败约束 |
| --- | --- | --- |
| 实际PG来源到手机减仓 | 正常TP1成交后清除活动TP，重新加载Aggregate和持久命令，原始GET采集能生成并签名受理新的Runner减仓预览；完成后自动续管 | 在途Stop、数量变化、未决结果必须继续拒绝；失败过的用户请求不得自动重发 |
| 操作相邻分支 | 有效Stop／TP、原始当前订单和成交变化进入真实operation runner | 当前TP消失／变价／新成交、人工TP部分成交取消、命名空间相同数字ID、原TP自然先成交；无新增副作用越过未知状态 |
| 历史核算 | 正常正式闭仓证明→终态Review补证据预览→精确退出成交进入经济计算 | 重现6.266秒差距；已终态、预算和旧Review不变；只有现有正式Owner批准才能追加修订 |
| Feed与Overview | 真实PG RR快照、连接池等待、接收心跳并发提交与共享最终发送门 | 真实断线、过期租约、未来时钟、接收积压、旧epoch重放、错误commit/Schema均须拒绝；旧gap恢复后不冒充持续中断 |
| 桌面和手机 | 真实API契约、长会话、未知回执、前后台恢复与展示时间 | 价格小数不丢失，帮助不触发订单，进入表单仍需预览确认；页面旧数据降级；真iPhone另验 |
| 发布 | 精确候选认证、安装身份绑定及联合升级 | 本批包含后端变更，不能冒充纯静态更新；独立静态入口保留“前后端契约未变化”的既有约束 |

批准后仍使用本工作区`.venv`和`manual_pytest.sh`，仅允许独立可丢弃手工产品本地PG。正式认证、候选冻结、部署、历史核算应用、真机和自然交易所验收分别记录，不能以本阶段单元证据替代。

## 当前最终状态

改动保留在当前工作区供审查；未冻结发布候选、未部署、未重启服务、未改变Owner开关、未产生交易所写入。等待Owner批准进入集成测试。
