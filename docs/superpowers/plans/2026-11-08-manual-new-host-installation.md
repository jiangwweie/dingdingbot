# 人工接管项目：独立新机安装与账户交接

## 授权与目标

Owner已确认子账户创建，并授权完成剩余工程和首尔安装；需要提供密钥时由Owner协助。
此前“实施仅限本地”的阶段已结束，不再为同一独立环境安装重复索取许可。
目标是将同一个Kernel部署到独立机器/数据库/账户，保持ENTRY关闭，完成身份和只读事实验收，
最后再按真实Owner控制与App协议证据决定是否具备启用条件。禁止操作Tokyo的运行配置或交易。
当前生产状态仅查[MAIN_CONTROL_ROADMAP](../../current/MAIN_CONTROL_ROADMAP.md)。

## 阶段与边界

| 阶段 | 入口 | 放行条件 | 完成证据 |
| --- | --- | --- | --- |
| 目标检查 | install_manual_host --phase inspect | 显式SSH目标、公网IP、machine-id、root产品标识 | 远程当前事实匹配，无写入 |
| 程序暂存 | --phase stage | 同SHA干净提交、Kernel R4/API/Static证书，目标无旧运行者、有维护围栏 | 三个独立release目录、依赖安装、提交/schema/product标记、无current切换 |
| 数据库基础 | --phase database | 已暂存相同提交、独立容器/卷绑定、端口仅loopback、无旧应用 | 官方Alembic到head、独立PG标识、最小权限角色、零Policy/Profile/Ticket |
| 密钥交接 | configure_manual_account（Owner私有终端） | 实际子账户UID、HMAC API Key/Secret、IP白名单；输入隐藏 | 签名GET证明UID/权限/空仓订单事实；受保护密钥及独立Console认证 |
| 账户初始化 | --phase initialize | 当前签名GET重新核验、真实账户及PG系统身份确定 | 官方seed与既有Owner暂停转换同事务，ENTRY关闭、exchange_commands禁用、SOR-001退役及TradFi/SOR-1H初始暂停 |
| 控制台安装 | --phase install-console | 上阶段精确绑定、全部交易Worker停止、维护围栏存在 | 独立current链接、systemd凭据、API/static与首尔域名；仅启动Owner API，控制写请求由Nginx拒绝 |
| 运行验收 | 后续安装阶段 | 精确提交证据与所需账户/市场事实 | 当前账户模式、5x/Cross、认证/权限、App动作真实覆盖 |
| 放行 | 正式Owner控制与promote_entry | 无工程/身份/账户门槛缺口，既有真实授权有效 | 软件安装、ENTRY授权、自然接单/保护分别记录 |

前三阶段不读取交易所密钥，不建立账户资金授权，不启动任何交易Worker或Owner API。
安装器不是另一套交易链，只调用现有正式schema、seed、role和service边界；旧Tokyo发布入口保持封闭。
当前阶段不支持活动仓位接管、已有运行者迁移、旧数据库恢复、直接SQL修复或绕过认证。

## 身份与凭据

- 编译产品身份固定；期望主机由显式参数声明，并在每次远程阶段从机器、云metadata、root标识重新读取。
- 本地临时归档只运输精确提交的版本化源文件和锁定前端构建；远程校验完整传输SHA256、证书和归档路径。
- root环境生成独立数据库密码；只写root0600文件，不出现在命令参数、日志或Git。
- API Key/Secret由Owner运行交接命令隐藏输入，通过SSH stdin直接传入，不落本地凭据文件。
- 用签名GET /api/v3/account的uid核对Owner提供UID；缺字段/不匹配不猜测，不绑定。
- API读取、合约和IP限制必须明确有效；提现/划转能力不能启用或未知。模式、持仓/挂单不合格只报告，不自动修改。
- 账户探针仅GET，禁重定向和隐式HTTP代理，recvWindow保持5秒，无写接口/交易命令/测试订单。
- 初始Owner Console使用独立密码、TOTP和Session材料；TOTP导入链接仅交付Owner私有终端，不写入诊断报告。

## 本地验收与发布

先验证错主机/产品/账户、危险权限、非空仓、已有运行者、归档越界/符号链接、公开Secret权限等反例，
再验证正例、schema/角色、清洁安装恢复与当前实现边界。静态检查与受影响回归通过后冻结候选，
只对最终精确SHA执行官方R4、API、Static认证；不得把旧提交证书转给新脚本。

服务与前端仍留在维护页面，直到新身份及账户步骤完成。实际账户验证和App操作证据不能由fixture替代。
密钥是当前外部依赖；需要时提供可直接运行的隐私交接命令，不要求Owner在聊天中提供Secret。

## 密钥交接后的安装边界

初始化脚本逐次验证主机machine-id、公网IP、root产品标识、精确提交三面证书与实际release，
并使用相同安装互斥锁。当前账户事实由签名GET获取，网络读取在数据库事务外；
PG读取显式READ ONLY、5秒statement_timeout，空库初始化通过既有Kernel seed及控制转换完成。
不创建交易所命令，不伪造TOTP认证或Resume，不变更交易所模式、杠杆或风险预算。

新账户原始seed包含历史SOR-001控制，安装器必须在同一事务调用既有暂停用例，
落实Owner永久退役决定并保留独立审计事件；不能只依赖全局ENTRY关闭掩盖退役控制。
TradFi和SOR-1H维持初始暂停，本次不从Tokyo复制其授权或Selection配置。

Console通过显式`OWNER_CONSOLE_PUBLIC_ORIGIN`绑定首尔HTTPS域名，同时推导准确Host；
该配置不含Secret。系统服务仅使用新账户的独立凭据和数据库角色。认证、登录、退出与只读页面可用，
Nginx拒绝控制写请求，交易Worker不启动，ENTRY维护围栏和不可写能力保留。
实际App协议覆盖、市场/规则/认证、Worker运行与Owner真实ENTRY授权仍是独立后续门槛。
该阶段只交付可登录查看的安装状态，不宣称已经自动开仓或具备完整人工接管实盘证据。
