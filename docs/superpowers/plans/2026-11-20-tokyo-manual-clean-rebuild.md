# Tokyo 全新人工协作产品安装

## Owner 决定

Owner明确授权东京使用首尔实际人工产品代码及参数，替代旧自动产品；东京已外部全平并在控制台关闭ENTRY。域名/证书/Cloudflare、原币安账户/API凭证、飞书机器人、Google登录、密码/TOTP继续沿用东京。首尔运行不变。旧业务数据库、代码release、维护工具和旧写入者从东京运行环境删除；保留独立离线备份追溯，不作为运行authority。

## 设计与约束

- 以首尔实际已安装精确提交为基线，在隔离worktree实施；不读取其他工作区未提交UI修改。
- 不合并旧Tokyo特有参数/MA50/账本；使用首尔当前风险/方向/策略/Selection/退出配置的语义值，生成东京新账户的初始化记录，不复制首尔Ticket、授权、订单、设备或会话。
- 新数据库从人工产品完整迁移链空库安装；两产品0016分叉，禁止伪造兼容升级/旧表回退/双写。
- Tokyo专用重建入口以精确host/machine/source commit/schema、ENTRY关闭、内外部flat、无unknown/debt、五写入者停止、备份校验为硬门。原人工安装工具继续拒绝误指向Tokyo，不通过改别名或删除守卫绕过。
- 站点显示标签和通知链接从受保护启动配置绑定；新东京沿用原飞书token，首尔现有默认显示保持不变，不额外发测试消息。
- 首尔当前配置只迁移语义，不迁移Owner历史授权：全局ENTRY始终false；退休SOR及暂停的产品继续相同状态。API/TOTP身份使用原Tokyo凭证。
- 新软件精确R4/API/static认证通过后才停服切换；首先本地空库重建、配置导入及故障边界演练。
- 完成后清理旧BRC release、旧业务DB/容器/卷和BRC旧配置；不触碰同机owner_ai等其他应用。nginx/证书/Google认证字节保全验证。
- 先启动安全服务与观察，官方promote_entry --prepare-owner-resume，保持真实Owner ENTRY关闭。自然订单/保护/手机合作/真实通知各自独立验收。

## 交付证据

直接事实、备份/restore-list、身份/凭证保全、配置语义对比、清理清单和服务/PG/交易所/HTTPS检查存忽略目录。正式生产状态统一更新MAIN_CONTROL_ROADMAP。失败停写保留围栏，按实际阶段fix-forward，不把旧写入者重新接入新库。


## 初始退出参数发布边界

首尔当前0024的六Event退出/MA50配置要求真实Console TOTP发布；迁移不会复制首尔授权记录或伪造Tokyo step-up。新Tokyo种子保留完整支持能力和待发布参数，安装后由原Tokyo控制台使用原TOTP完成同款参数首次发布；全局ENTRY另行Owner恢复。若缺少该真实授权，promoter保持阻断，不能宣称完整交易就绪。
