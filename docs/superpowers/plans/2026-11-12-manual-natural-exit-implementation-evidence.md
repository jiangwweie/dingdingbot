# MA-NATURAL-CLOSE-01 实施与验证证据

## 授权与范围

Owner于2026-11-12明确要求部署，授权实施已交付方案和精确自然退出恢复合同；真实Owner暂停已只读核验为Policy11。当前生产身份与现场完成阶段只由MAIN_CONTROL_ROADMAP.md及行动时事实决定。

本轮实现同0021 schema确证退出证明、只读事件／会计收尾、精确因果事故集合、空仓事实分支、TP自然终态基线分类、模式感知采集、生命周期／dispatch原因留存、限定安装scope与GET-only恢复入口。没有新增migration或放宽普通安装门禁。

## 不变量与实现

- 原管理模式和人工接管历史保留，不通过恢复AUTO或伪造MANUAL收尾。
- 准确命令／namespace／订单／client ID／父子单／条款与持久基线；原委托量和实际退出量分开，所有退出fills严格守恒。
- 新VerifiedExitClosed事件保存完整typed证明，复用既有UnitOfWork、ReleaseCapitalAuthorities、settlement／Review链，预算恰一次释放；PG投影与事件回放一致。
- 事故按精确IDs且集合一致才解决；额外事故／命令unknown／源版本变化拒绝。
- 恢复安装同schema、真实全账户flat、全部writer停止、Owner暂停；新scope绑定目标票／版本／事故且capabilities disabled；旧普通恢复不自动接受开放事故。
- 维护工具preview真实事务回滚，apply重新取证并核对内容digest；无venue write port。正常身份只在终态清洁与fresh venue门禁通过后恢复。
- 保留现有配置、Owner策略／预算／Selection和原命令；5412950b本地只读权限补丁纳入候选。

## 先导验证

- 原缺失能力RED已记录；纯域准确退出及身份／数量／缺口反例通过。
- 37项初步PG／管理／退出回归通过；扩大回归2206项先通过，文档锚点与既有测试辅助函数边界问题已定位并修复。
- 精确协议、父子／方向／余量／重复、空仓缺价与非零缺价、限定安装、PG一次释放／rollback／MANUAL保留等组合通过。
- 完整链及相关集成组合124通过；正式冻结候选的原生证书仍为最终认证权威，早期组合不代替新SHA认证。
- 实际只读生产dump恢复到独立manual PG，保留原活动票与事故，限定identity→preview rollback→apply两次→正常identity演练通过；Owner控制／配置／原Command逐行保全，terminal／positions／预算／incident全部归零。协议使用已脱敏准确HTTP记录，当前flatness在现场重新GET核验，不能以fixture授予生产权限。

## 证据入口与限制

`.local/manual-natural-close-20261112/`保存RED/GREEN、静态分析、实际源恢复演练及正式认证日志；私有dump不提交。标准测试fixtures只保存脱敏订单协议。

BNB历史费用及funding证据缺失时，初始Review明确经济不完整并进入原有补证据预览队列，不填0、不自动修订其他已终态旧票。后续自然退出／TP／Runner／App以及手机实际收件仍需分别观察。

本文件随实际完成追加，不能以本地实施记录宣称已安装或已恢复交易。

## 候选复核与资源前置条件修正

69ea610c完整unit／architecture2185、integration1948、full-chain76及Ruff／Mypy／Golden均通过，但最后core parity因启动环境未传既有SOR_DYNAMIC_SELECTION_CACHE_DIR而未生成R4证书。使用原冻结cache的单独core parity通过961快照／23064成员决定；不得手工补证书。

独立四项resource组合中两项保护与warming并行场景最初在warming target为空处失败。trace证明任意active-scope事实读取也会记录warming_source_hung，旧等待条件在准确generation物化前就可能结束。用同一70秒／总600秒预算等待准确generation target进入warming后，保留原全部仓位／命令／CPU／内存断言，四项串行通过134.67秒。修正仅在测试等待条件，不修改生产策略、Selection或资源边界。最终SHA使用完整环境重新认证。

## 安装后新增边界复核

55a56c43三证通过并已完成同schema限定安装／真实GET预览及apply，当前票terminal、仓位／预算／因果事故0，正常身份恢复、Owner仍暂停。现场发现两项补充缺口：REVIEW终态收尾通知误归residual；readonly认证以启动前采样时间判断稍后读取的RR feed，可能把已ready的新鲜水位误作未来证据而阻止promoter。前者先RED后修为确证事件下residual0；后者新增PG时序反例，实时feed按读取时刻校验，显式历史now仍严格拒绝未来数据，未放宽lease／TTL。补充候选单独认证后按普通terminal-clean同schema程序安装，不再次运行已完成的恢复apply。
