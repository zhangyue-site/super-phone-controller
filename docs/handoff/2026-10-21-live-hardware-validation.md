# 云端升级与现场联调（2026-10-21）

状态：板子已升级并完成云端开机回报；配套App已上架。实际麦克风→手机操作→TTS及屏幕停止尚未完成，联调期间Mac的目标USB设备消失，手机仍锁屏，等待用户确认接线和解锁。

## 实板已核验

- 原feedback版本TLS反复报mbedtls_ssl_setup -0x7F00，内部可用31419、最大连续15872；输入record缓冲16384且分配限内部RAM。冷重启直接OTA仍失败，不能仅凭云端包发布声称已升级。
- 云端4ffe311改TLS分配到8MB PSRAM，CI检查实际配置；14e6241为本地控制台增加VOICE PREPARE/START/DOWN/UP，复用原有生命周期，不绕过任务校验。
- GitHub ESP-IDF6 run39568849532（构建54）成功，PSRAM配置检查通过。2026.10.21-ci54，1799632字节，SHA256 1fd2881c9b60e05cd3c22257c127f352cb0c48da1855afc1a376c01c007c98a8，私有OTA已发布。
- 旧固件无法联网升级，改用现有BLE OTA救援。只连接已确认D41A目标板，MTU515、数据帧511字节。BEGIN+2044数据后调用同屏幕STOP函数，BLE状态从receiving归idle，进度归0，原ota_1保留；这是实际升级中止，不是触屏按压验收。
- 完整BLE传输270.1秒，板端SHA校验、切槽READY[3,100,0,0]通过；重启读回ci54/ota_0，screen_error=0、8MB PSRAM、音量100。
- 106收到boot-confirmed、imageState2、ci54/ota_0，HTTPS200；此时HEAP largest只有13312，TLS仍成功，支持PSRAM修复有效。播放本地提示后预检stage8、日志上传200，旧TLS分配失败未再出现。

## 手机连接及测试边界

当前板子的USB网络对端是Mac192.168.77.2。临时诊断桥限定192.168.77.1来源：Mac5555到127.0.0.1:15555，后者由明确目标小米192.168.7.235:5555的adb forward创建。原有手机Wi-Fi保持原状态，未开启板端Wi-Fi，没有操作其他ADB机器人。板子自己的RSA认证与只读shell探针通过。它是实际手机中间链路，不能算无Wi-Fi手机USB直连通过。

目标小米随后自动锁屏，读取showing=true、inputRestricted=true、Dozing，没有绕过锁屏或发出手机输入。准备使用Mac固定合成语音从实物麦克风输入时，目标板与FTDI均从MacUSB列表消失，串口无法连接；脚本在播放前退出，Mac原有静音未改变。手机上未出现USB网络接口，不能判定用户是否换线。已异步询问接线与解锁，等待回复。

测试前发现板子持久化静音为true，已临时解除用于播报验收；因后续USB消失尚未恢复，重连后须先读AUDIO并在测试结束恢复原静音。Mac音量50/静音true未改变。

待完成：真实收音、ASR识别手机指令、实际设置/首页动作与新UI验证、结果TTS可听性、连续对话续听、屏幕实际停止、无Wi-Fi直连。不要把此前模拟手机或本轮只读探针当作完成。

## 配套App

控制板升级助手1.0.1+2已发布到 https://d.zhangyue.site/apps/phone-controller-flash/ ，正式B5签名和公网APK下载校验通过。真实目录15项，原14项及商店自身版本保留。详细证据与未验项目见同目录2026-10-21-upgrade-app-store-release.md。控制手机无需安装此可选BLE升级工具。

## 接手入口

云端源码/测试工作区106:/opt/phone-controller-workspace，分支feat/epaper-interaction-audio；在线服务正常。现场脚本及日志在Mac/private/tmp（等价/tmp）：controller-ble-upgrade.log、controller-ble-stop-test.log、controller-ci54-boot.log、controller-ci54-prepare.log、controller-voice-chat-live.log。Mac诊断桥controller-adb-relay.py与controller-ota-relay.py只用于联调，结束须停止并移除本轮adb forward tcp:15555，不影响其他设备。

本轮滴答checkpoint按super-phone-controller键只读定位返回结果未知错误，未执行正文写入；交接已保存仓库，不宣称同步成功。后续有唯一任务ID后再按现有技能对账同步。

收尾复核：目标USB仍为0，手机仍showing=true。已停止本轮Mac5555/18843诊断桥，并精确移除目标手机tcp:15555转发；不影响其他ADB设备。Mac静音保持原值true。下一步须先确认用户实际接线/解锁，若恢复Mac中间联调再重建本轮限定桥；测试结束恢复板子原有静音true。
