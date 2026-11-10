# 管理协议回放语料

来源：首尔独立账户2026-11-10只读采集的 Binance USD-M allOrders/allAlgoOrders；交易动作发生于2026-11-09。四个样本为真实BNB订单记录，保留端点字段、金融数值、状态及时间；订单ID和clientOrderID做确定性脱敏映射。输入是采集时实际CCXT解码后的字段形状，重新经过当前锁定CCXT的on_json_response；不是声称原始HTTP字节归档。原始HTTP/WS字节覆盖单独验收，未由这些样本证明。反事实修改属于derived/synthetic。

禁止保存API key、signature、listenKey或账户Secrets。生产不读取此目录。真实创建时的回执/WS未留存，不能用终态REST样本补造原始创建基线。
