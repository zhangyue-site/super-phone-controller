# 控制板升级助手｜乐天应用商店正式发布

状态：已正式上架并完成公网完整下载校验；App 真机安装和 App BLE 全程未验证。证据时间：2026-10-21 16:45 CST。

## 交付边界

本 App 是可选的 BLE 控制板固件升级工具；控制手机无需安装本 App。面向 Android 8.0+，需要 BLE 和蓝牙权限。只能选择获授权且与控制板型号匹配的本地 app.bin。服务器固件下载需要设备授权，App 不携带设备 Token，401/403 提示改选本地文件。未发布任何私有固件、设备 Token 或维护者凭据。

真实安装、首次启动、App BLE 全程与用户手机测试未执行。本次不接触手机、ADB、串口或板端 OTA。新 App 无正式上一版本，覆盖升级不适用；仅商店分发，无 App 内自更新验收。

## 来源与审阅

- 仓库：private xiaoletian64/super-phone-controller，feat/epaper-interaction-audio，发布来源 72a13cd。
- 云端构建：GitHub Actions 39570177863，pcflash-android。
- 使用既有 publish 技能、audit_apk.py 和 publish.py；真实生产根目录 124:/www/wwwroot/download-hub。
- 云端源码审阅隔离目录：124:/var/lib/download-publisher/pcflash-review-20261021；source-hashes.json 绑定选定 app/lib、app/test、pubspec、Android 配置及 workflow。
- DeepSeek 回执：deepseek-receipt.json、deepseek-followup-receipt.json 均确认 ok:true / model_used:deepseek-chat / provider:deepseek；首个过大请求 HTTP400，缩小必要源码后成功。
- 静态审阅复核撤回：镜像文件版本偏移48正确（24字节镜像头+8字节段头+16字节desc内偏移）；先订阅后BEGIN；512字节ATT值未超协商MTU；非营利个人分发不当然商业；最终APK单独核对B5证书与debuggable。
- DeepSeek 第二次返回 confirmed_blockers:[]。其残留表述中“BEGIN后通知早于listen”与源码顺序冲突，未采信；iOS未发布。保留真实限制：本地固件没有App端project/chip绑定检查，必须选型号匹配的授权固件；App BLE实际表现未验证。模型文字不代替运行测试。

## 发布与验收

| 项目 | 结论与证据 |
|---|---|
| 商店入口 | https://d.zhangyue.site/ ，搜索“控制板”，实用工具分类可见 |
| 独立下载页 | https://d.zhangyue.site/apps/phone-controller-flash/ ，HTTP200 |
| APK | https://d.zhangyue.site/apps/phone-controller-flash/releases/1.0.1/phone-controller-flash-1.0.1-vc2.apk |
| 身份 | site.zhangyue.pcflash；1.0.1 / versionCode 2；minSDK26；targetSDK36；label控制板升级助手 |
| 大小 | 47,098,069 bytes |
| APK SHA256 | `5da39e2f13f816535a72ef85fd2cd5c6d8f319bb0f898ea7479e5112777da5ff` |
| 正式证书SHA256 | `b5aaac0eb0369165d34ee3bae1cddd637eaa2bc3566adf9e3f2dc2f5a1a473e4`，与保险库B5固定证书匹配 |
| 签名/包体 | audit_apk.py --new-app passed:true；无debug证书，非debuggable；未捆绑固件/签名钥匙文件；AssetManifest.bin和DebugProbesKt.bin是框架资源，不是板端固件 |
| 构建测试 | GitHub Actions 39570177863 success；analyze、Regression tests、Build signed APK成功 |
| 商店登记 | 124真实apps/apps.json锁内重读、私有备份、原子新增；slug phone-controller-flash唯一；此前14项和self逐值相同 |
| 数据一致 | catalog.json、独立latest.json、apps/apps.json的版本、URL、SHA、bytes一致 |
| 浏览器UI | 首页新增项显示1.0.1/47.1MB；搜索“控制板”+实用工具分类只剩本项；详情说明、Flutter默认图标、下载APK链接正常；1280×720桌面截图已在会话工具结果查看 |
| 图标 | https://d.zhangyue.site/apps/icons/phone-controller-flash.png ，HTTP200 image/png，1443bytes |
| 公网完整下载 | 本机curl -fL下载最终URL；67秒完成；SHA256和47,098,069bytes与已审计APK完全相同 |
| 云端执行测试 | 124隔离执行 metadata一致、唯一包名、APK哈希/大小、原14项与self保留断言通过，exitCode0；cloud-execution-tests.json |
| 新装/首次启动 | 未验证，无设备操作 |
| 覆盖升级 | 不适用，新App首次正式发布 |
| App BLE端到端 | 未验证，主代理板端测试不替代本App安装和传输验收 |
| App内自更新 | 未实现/不适用，仅商店下载；未新增latest.json作为App自更新协议 |
| 原生商店客户端读取/手机布局 | 未验证；网页及公开真实数据源已核对，不等同原生客户端实测 |
| 账户 | 不提供App登录；服务器固件授权下载401场景仅源码已知，未做账户实测 |

审计与产物：106:/opt/phone-controller-release/2026-10-21/{apk-audit.json,package-content-check.json,release.json,phone-controller-flash-1.0.1-vc2.apk}。
商店合并回执：124:/var/lib/download-publisher/pcflash-store-registration.json。
生产目录备份：124:/var/lib/download-publisher/catalog-backups/apps-before-pcflash-20261021T164316.json。
本机完整下载：/tmp/pcflash-public-download.apk。

## 回退与交接

新增App回退需在发布锁内重读apps/apps.json，仅移除此slug/package条目，保留其他应用与self；catalog.json仅移除本slug，页面可标为撤回。不可删除已公开不可变APK或以旧全量目录覆盖当前目录。

本子任务未单独创建或覆盖滴答任务；由主代理将本报告合并到原任务同步，最后成功同步状态以主代理读回为准。

源码清单 SHA256：`572029fd3d05557e8dda0dcbba039d47dcfdfef81f24205337cc65c01d2a9f14`；复核回执 SHA256：`709329846ac4b594c431696872651672e9072d6ba3d0e7370deb4c257f9447ab`。
