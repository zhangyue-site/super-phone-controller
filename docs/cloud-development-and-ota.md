# 云端开发与固件升级

用户要求后续开发、修复和固件构建放到云端。云端服务运行服务和独立Git工作区；GitHub Actions在官方ESP-IDF6镜像中编译，避免云端服务上的现有业务争用编译资源。

## 固定位置

- 源码工作区：云端服务 `/srv/phone-controller/workspace`，分支 `feat/epaper-interaction-audio`。
- 在线服务：106 `/srv/phone-controller/firmware`，systemd `phone-controller-display`。
- 私有固件：106 `/var/lib/phone-controller/ota`。
- GitHub云构建：`.github/workflows/esp-firmware.yml`，每次相关代码push运行测试和编译，产物位于私有Actions artifact；使用repo secrets注入设备配置。

开发先在工作区修改、测试、commit和push；在线服务目录不直接作为开发区。新板型/设备须独立配置密钥，不能把现有设备身份复用给公共设备。

## 发布与恢复

main分支且OTA_ENABLED=true时，CI通过受限SSH key调用 `tools/cloud_publish_ota.py`。该key只能运行固定设备的发布命令，不能开shell、转发端口或选择任意路径。SSH主机公钥固定，不跳过校验。固件不提供匿名下载，也不添加HTTP上传接口。

发布器验证ESP32-S3芯片、项目名、app descriptor版本、段边界、XOR校验、附加SHA256及0x340000槽容量。按sha保存不可变bin/json，权限600；完成验证后原子替换current.json，旧版本保留previous.json。CI按分支取消过期构建，服务器按构建序号拒绝旧任务晚到覆盖新版本。元数据版本从镜像内读取，避免CI版本和镜像版本不一致。PR分支只构建，不自动覆盖设备的OTA版本。

分支测试版可以在云端显式发布：向发布器输入一行 `{"source":"40位git提交","generation":构建序号}`，接原始app.bin；默认暂存，加 `--activate` 才切换current。仅通过已认证SSH进行，二进制包含设备身份，不放公共Release。

板子在升级页发起云端检查，仍需有效手机ADB隧道。下载校验通过后写非活动分区，启动自检失败由bootloader回滚；屏幕STOP可取消写入阶段。不是后台强制自动刷机。云端保留previous可将发布指针切回，但必须使用已验证版本，不能把改current当作已经回滚实板。

## 手机连接要求（本轮不改硬件）

1. 手机不装App，控制板Wi-Fi保持关闭。
2. 手机需支持作为USB Host识别板子的NCM网络；数据线/OTG角色正确。
3. 用户手动恢复ADB TCP端口5555，保持手机解锁，确认控制板RSA授权。仅开启“USB调试”开关不保证5555已开放；配对密钥也不会自动开端口。
4. 板子点击检测连接，预检通过后开始连续对话。断线后手动恢复并重新开始任务，旧输入不重放。
5. 手机与板子的直连操作、断线停止、云端OTA下载及开机回报仍需实物验收。Mac上的网络或手机Wi-Fi诊断不替代这一验收。
