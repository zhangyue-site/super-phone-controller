# 微信 / Telegram 确认控制交接

## 已部署
106控制服务增加独立鉴权的 /bridge/phone 和板端 /remote/claim、/remote/status；单设备任务互斥，双入口各自绑定受信任的私人发送者与账号，确认120秒有效，确认队列60秒未领取即过期。任务领取先持久化消费，一次领取不重放；服务重启取消未完成任务。解绑入口会撤销已确认任务。预览和状态查询不执行手机动作。线上两个入口授权状态查询均200/idle。

OpenClaw openclaw-phone 0.1.0 已安装、启用，注册 /phone 命令和持久化结果监听。真实渠道健康探测：微信账号enabled/configured/running，无错误；Telegram configured/running/connected，probe.ok=true。配置只授权每个渠道现有主人，独立桥凭证不复用设备令牌。配置与状态均在受控服务器目录，不入Git。安装时网关一次堆内存退出，系统自动恢复；后续服务active，需继续留意既有网关资源使用。

## 用户操作
- /phone 打开微信找到李洋：只返回计划，不执行。
- /phone 确认 <计划编号>：仅同一私聊可确认，原计划不可篡改，不发消息，保留搜索结果。
- /phone 停止：两个已授权入口均可停止此设备，取消待确认/待领取任务；结果仍只回原私聊。
- /phone 状态 [编号]：查看当前入口任务或失败原因；网络主动回传不明确时恢复查询。
- /phone 存为技能 [编号]：仅当前入口最近核验成功且未被新任务替换的结果可保存，复用通用采集器和微信专项模板。

手机须解锁，在升级助手中授权整屏共享；板子须接手机并已启用HID与连接预检。点击/移动/拖动走HID，ADB动作仅现有中文输入并恢复原输入法；历史网络代理仍是单连接ADB隧道，不宣称整个运行完全去ADB。旧cardputer-phone不是这个项目的执行器。

## 软件测试证据
131项根测试、9项屏幕接口测试、18项C/C++主机测试、5项Node插件测试通过。跨语言HTTP测试实际运行插件handler→真实HTTP桥→真实mailbox→模拟板端HID/中文回执→合成画面核验→原私聊模拟回传，覆盖微信和Telegram。覆盖跨入口确认拒绝、结果隔离、停止、ASR在途停止、确认竞争、过期、重启、旧启动会话和序号重放、解绑撤销、初始握手前/重启后停止，以及画面锁顺序检查。测试没有发送真实聊天或操作真实手机。

## 板端实现和剩余验收
固件源5ef46837afc6e8a8f26fe20e12fcd6e31e49cce6，官方IDF构建39722598744（ci67）通过。已激活私有升级版本2026.10.22-ci67，1805376字节，SHA256 b0d0bb17e60723dd487573178f2bb7c2e48325daab615068f8b2e7895e0a9178；App可下载，未宣称已刷入板子。公网 /app-ota/challenge→authorize→image 完整1805376字节下载及SHA256核对通过；由私有服务器签名器代算BLE HMAC，未声称测试了真实BLE。106直接访问公网TLS曾超时，从Mac公网重试通过，未传出设备长效凭证。空闲3秒轮询，启动租约握手与递增序号，严格保留本地HID许可。后台画面/事件请求与远程领取互斥，待上报STOP阻止新领取，OTA时不接任务。
单连接传输中，云端STOP在每次取命令/动作前检查；不能中断已开始的中文shell、HTTP传输或播报中的整段音频，原中文12秒截止及输入法清理保留。本地屏幕STOP仍直接撤销板端许可。实机HID兼容、中文恢复、停止时延及蓝牙升级/重启确认没有验收，不能把模拟当真实手机通过。微信/Telegram真实来信元数据兼容仍待用户各发送 /phone 状态。

## 回退
在线服务备份 /var/lib/phone-controller/backups/remote-20261022-122130，新增systemd配置50-openclaw-remote.conf可关闭EPAPER_REMOTE_CONTROL；保留其他语音修复。OpenClaw工作区AGENTS已补S3/微信找联系人任务的专用路由，备份AGENTS.md.before-s3-phone-20261022；不调用旧ADB点击工具。OpenClaw只关闭openclaw-phone入口，不回退其他插件/账号；安装前配置备份在同目录openclaw.json.bak-phone-bridge-20261022。固件私有发布保留previous.json，不强制刷板。

## 真实入口复测修复（14:36后）
用户报告两个入口没有正常回复。根因复现：使用实际OpenClaw启动规划器读取部署配置，openclaw-phone不在pluginIds中；原manifest没有activation.onStartup和runtime-slash命令归属，配置enabled不等于加载。已补activation.onStartup=true、onCommands=['phone']及commandAliases runtime-slash phone。新增回归先失败再通过，现6项Node测试通过，跨语言HTTP三项通过。
实际启动规划器修复后包含openclaw-phone，网关14:36:12记录phone runtime initialized，14:36:16监听插件列表包含openclaw-phone；14:41:12窄范围插件替换成功。补充不含身份/任务文本的入口与处理阶段日志。CLI commands.list的WebSocket诊断连接超时，不能把该项写成已验证；网关HTTP health为200且运行中。真实私聊仍需新命令进入日志并返回正常状态，不能将普通AI回复当作phone控制通路成功。
