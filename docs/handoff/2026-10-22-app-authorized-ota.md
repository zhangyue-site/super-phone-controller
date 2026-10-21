# App 自动授权下载与实板蓝牙升级验收

用户要求：App 内直接下载固件，不手动传文件；蓝牙写入和重启确认一起检查；使用独立 APK 图标。

## 已完成
- 124公网入口反代到106，保留鉴权与上游TLS验证。新增云端一次性挑战/板端HMAC证明/5分钟仅限设备固定固件SHA的下载凭证。APK不携带长期设备Token。
- ci60新增BLE INFO/AUTH；App下载后检查大小、SHA、S3项目与镜像完整性。READY后显示等待重启，重新连接相同BLE ID，检查设备ID、新boot nonce、完整版本、ELF SHA及imageState2。
- 正式签名App1.0.3+4：云构建39601988987（source1889f52）成功，analyze和11项Flutter测试通过。86项Python测试、17项固件主机测试通过。固件云构建39600396540（sourcecd35fc0，ci60）成功。
- 新图标覆盖旧PNG五密度、Android自适应及主题单色资源。最终APK内五组PNG像素与源码一致，预览已查看；商店图标同步。
- App通过既有publish技能与store_catalog安全入口上架，apps/apps.json含15项，其他App及self保持不变。

## 实板证据（桌面BLE客户端，不是Android App整轮）
1. 唯一PhoneCtl目标，Mac作为BLE central。完整发送1799136字节ci60，with-response写入，521.6秒。
2. 收到READY/SHA校验通过，观察真实断连重启，重连读回2026.10.21-ci60、匹配ELF SHA、imageState2。初始ci55无INFO，因此首次维护升级没有旧boot nonce可比较；版本切换、断连和新固件自检已经实测。App新nonce判断有单元测试。
3. 新固件真实签名云端挑战，取得下载凭证，从公网完整下载1799136字节ci60，大小与SHA核对通过。该下载检查不再次刷写；已释放BLE连接并通知用户可拿走。
4. 未通过ADB安装或操作升级App，遵守ADB仅中文输入限制。Android手机安装、覆盖升级及App内完整点击流程仍待手机验收，不把桌面协议实测写成手机App全程通过。

## 产物
- 商店：https://d.zhangyue.site/apps/phone-controller-flash/
- APK：phone-controller-flash-1.0.3-vc4.apk，47671013字节，SHA256 a2480589aa63051e3db82591390f5811c753848bd25c4436fea09b098edae783。
- 包名site.zhangyue.pcflash；正式B5证书与1.0.1一致；apksigner/audit_apk通过。
- 固件ci60 SHA256 6479156273c5f7cc556f68f99dfa114016b295a9e36d64a919c1ef391969d9b3，私有current已激活，previous保留ci55。不公开固件。
- DeepSeek指定云端审阅首次输出截断，第二次完整JSON confirmed_blockers=[]；模型审阅不替代执行测试。回执位于124:/var/lib/download-publisher/pcflash-1.0.3-review。

## 恢复
服务部署前备份106:/opt/phone-controller-backups/app-ota-1792586194。124反代配置备份及商店目录备份保留。仅回退目标App条目/页面，不覆盖其他应用；不删除已公开不可变APK。旧板需先维护升级到支持INFO/AUTH的基础固件；当前用户板已完成。
