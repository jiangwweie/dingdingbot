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
| 账户初始化 | 官方seed与后续安装阶段 | 上阶段事实重新核验、真实账户身份确定 | 新账户PG seed、ENTRY关闭、能力不可写、原暂停/退役策略不隐式恢复 |
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
