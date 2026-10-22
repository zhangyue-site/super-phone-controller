# 2026-10-22 发布链路核验与 App 1.0.7

## 本次改动

- App 自身版本由 Android PackageManager 读取，扫描页右上角信息按钮显示真实安装版本；读取失败明确标注未知，不用发布版本冒充安装版本。
- 同一对话框提供固定官方 HTTPS 下载入口。App 本体仍通过官方下载页和系统安装器更新，不是静默自更新；板端固件仍走 App 内授权下载与 BLE OTA。
- 固件页不再从蓝牙广播名推断当前版本；断线、重新连接和升级返回时清除旧值并重新读取，无法读取时显示“版本待核实”。
- 保留包名 site.zhangyue.pcflash、正式 B5 证书、原有 APK 图标与权限范围。

## 构建与发布边界

GitHub 仓库已迁移至 zhangyue-site/super-phone-controller。已将云端 origin 改为新地址并通过既有 gh 身份恢复 HTTPS 推送，未把凭据写入仓库。新流水线 39749886697 在源码 59344ba7054fec88d1eedbaf0ef028f7a3b0ae45 上完成静态检查、21 项 Flutter 测试和正式签名，最终发布的是该流水线产物。106 的隔离 Flutter 3.44.0 原生云构建也通过，作为补充验证，不替换已发布的同名文件。构建临时交换文件已移除。

App 1.0.6+7 现有发布的包名、版本、正式证书、文件大小和 SHA256 已重新核对通过。新包须经相同核验后才更新商店。不能把构建完成、网页发布、手机覆盖安装和 BLE OTA 混写为同一项通过。

## 已有实机证据

板端最近一次实际 BLE 读取为 2026.10.22-server1；此前成功的升级轮次完成下载授权、完整镜像校验、BLE 传输、版本与 ELF 匹配、boot 改变及 imageState=2。云端 current 与最后 boot-confirmed 报告一致。首轮 244 字节分片在 END 失败，原因未定，保留原始失败证据；第二轮与 App 相同分片策略 MTU515/正文511，通过。该结果是 Mac BLE 协议实测，不能替代 Android App 界面升级验收。

此次核验时蓝牙未发现目标控制板；最后启动报告不是实时在线证明。手机实际安装版本也尚未通过本机显示核实，不凭“有手机控制入口”判定为最新版。

## 尚未验收

1. 手机覆盖安装新 APK 后，在信息按钮中看到 1.0.7（8），检查数据和蓝牙连接。
2. Android App 界面完成固件下载、传输与重启确认。
3. 用户同意共享整个屏幕、板端启用 HID 后，App 下发“打开微信找到李洋”：先只生成计划，再确认；另测停止；最终保留搜索结果页，不发消息，中文输入后恢复原输入法。

手机点击、滑动和启动应用必须走 HID，ADB 动作仅用于中文输入。历史 USB 网络仍使用 ADB TLS pipe，不能称整个通信完全不依赖 ADB。未使用 ADB 安装、截图、读取手机 UI 或操作微信。

测试证据：云端静态检查通过、Flutter 21 项测试通过、服务端 unittest 138 项通过。DeepSeek 最终审阅未发现本次改动的阻塞问题；模型审阅不代表设备验收。最终 APK 哈希、下载校验和发布状态另见本次 release-verification.json。


## 最终发布结果

- App 1.0.7（8），50,688,557 字节，SHA256 61849b4f636a1fd8cb2b1d637dc609c92f237a9008323f9e8c9cdf2fb11e32ad。
- 真实正式证书 B5 指纹与 1.0.6 相同，21 张原 PNG 资源内容匹配；不能用此替代覆盖安装验收。
- 官方 Actions ZIP SHA256 8764f133d8a8f6e84cedf3e03287705b51dd0bb82b93647196f05ac73fae0c96，下载完整校验后提取 APK。
- 公网商店 apps/apps.json、详情页和下载 APK 指向同一版本；公网完整下载大小和 SHA256 已匹配。保留旧包，不静默替换同版本。
- 下载：https://d.zhangyue.site/apps/phone-controller-flash/releases/1.0.7/phone-controller-flash-1.0.7-vc8.apk
- 固件云端 server1/generation74 的私有镜像字节、大小和哈希复核通过；在线服务 active。固件未在本轮重发或刷写。
- 手机实际安装版本、Android 覆盖安装、App 界面 BLE 升级及微信真机控制仍未验收。已请求用户读取系统应用版本，不能预先标为通过。
- 云端证据：106 /opt/phone-controller-release/2026-10-22-audit，124 /var/lib/download-publisher/pcflash-1.0.7-review。密钥和设备身份固件不进入公开 APK 或交付 ZIP。
