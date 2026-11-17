# USB 授权与板端 Wi-Fi 直连
用户已批准：USB 授权＋Wi-Fi 直连完整入口，蓝牙作为可选备用；APP 与服务端均更新。现有 PCUSB AUTH 协议可签名，无需为此改固件。
默认入口核验 USB identity 与 session → 用户系统共享确认 → USB 签名控制授权 → 生成绑定码与控制状态。默认不扫描蓝牙，不要求蓝牙开启。
新增独立 /app-control/usb-challenge、usb-authorize、usb-renew，字段 device/serial/challenge/proof。使用 pcusb-v1 既有签名域，但独立一次性 challenge 仓；票据仍为 phone-commands，过期/撤销/跨设备不得续期或控制。续期保持票据身份与控制端绑定，不转移任务。
APP 使用 USB info/sign 原生桥；定期续期校验同一 USB session，拔出、停止和过期不得重放旧动作。USB身份只表示授权，不表示 Wi-Fi 在线；保留未知和等待状态。
蓝牙中转只由明确备用按钮启用，原有停止/安全许可不变。系统共享对话框保持原生。
测试：无蓝牙默认启动、签名身份错配、过期/重放/跨scope、USB拔插与续期、界面失败/停止、原蓝牙备用回归。Android 通过既有GitHub签名构建发布；服务端先兼容增量部署，不自动刷固件。

## 已落实的生命周期边界
每次 USB info/sign、HTTP authorize/renew 返回后校验物理 snapshot/session 与取消代次；成功客户端的续期不依赖页面观察者。
usb-revoke 撤销原 USB parent、配对控制端并取消待执行队列；设备物理停止仍为待确认。403 续期后独立保留撤销凭据。
shutdown 等待正在进行的授权/续期及迟到 grant 清理后关闭 HTTP，STOP 在启动请求结束后读取撤销失败状态。
明确物理 session 改变会立即终止许可并尝试撤销；普通网络超时不自动重新授权或启用蓝牙。
