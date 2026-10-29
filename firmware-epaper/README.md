# 墨水屏手机控制器固件（1.6.8 源码）

目标硬件为 Waveshare ESP32-S3 Touch ePaper 1.54，8MB Flash、8MB PSRAM、200×200屏幕。这里同步的是已用于私有1.6.8镜像的通用实现，不包含设备身份、私钥、生成的sdkconfig或可分发固件。公开候选增加了配置化及默认关闭维护命令，不能把原私有镜像的构建结果等同本候选的新镜像验收。

## 日常链路与安全边界

- 手机App提供经Android系统授权的真实屏幕；板子通过USB HID完成点击、拖动、导航和键盘输入。日常使用不要求ADB、ADBKeyboard或开发者调试。
- 云端执行可经手机蓝牙中转签名BLE08指令，或由板端Wi-Fi直接领取HTTPS任务。中文由服务器生成拼音，结合新画面选择候选、核验实际文字；并未保证所有输入法与实体键盘布局均兼容。
- 每次启动输入许可关闭。ARM、STOP、签名、序号、任务代次及本地长按许可仍受各自安全策略约束；动作回执不代表目标界面成功，结果须由动作后的真实画面支持。
- 当前仍在允许/关闭HID时切换USB描述符；BLE断线或DISARM可引发重枚举，并使App结束对应共享会话。固定USB身份、仅逻辑门控的方案尚未实现，不能承诺所有连续任务都不再出现系统共享授权。
- USB安全配置保留CDC/NCM维护接口，HID配置使用CDC、键鼠及直接触摸接口。NCM本地租约不代表手机互联网或云端已就绪；现有两套配置不同时启用。
- STOP撤销旧任务与输入许可，停止后不重放动作。电源按键采用5秒提示后松手关机/待机、持续按住30秒重启；升级提交保护不因关机请求而绕过。USB供电时可能保持维护待机，而非真正断电。
- 蓝牙OTA、Wi-Fi OTA、断点续传、取消、启动健康检查及回滚保护均保留。实际升级需要明确授权；只发布app镜像，不用bootloader/整片镜像替代。

## 公开配置与构建

优先使用ESP-IDF6.0及现有云端CI。复制`main/device_config.example.h`到被忽略的`main/device_config.h`，或使用CI的设备配置注入；填写设备独立令牌和HTTPS入口，不能使用服务器管理凭据。不要提交生成的配置、私钥、含身份镜像或私有诊断资产。

普通HTTPS根据URL核验服务器主机名并自动生成Host，证书bundle和主机名检查保持开启。只有独立寻址的受信代理需要可选`DISPLAY_TLS_SERVER_NAME`/`DISPLAY_HTTP_HOST`覆盖；示例文件提供通用占位值。不要关闭证书校验来适配部署。

`CONFIG_CONTROLLER_ADB_MAINTENANCE`和`CONFIG_CONTROLLER_USB_MAINTENANCE`均默认关闭。后者控制额外CDC维护控制台，不控制App必需的PCUSB握手与STOP，也不等于日常执行许可。显式维护构建如需历史ADB代理，还须自行配置代理地址/密钥，不能当作生产自动兜底。

主机验证：`PYTHON=python3 bash tools/test_firmware168_host.sh`，需要C/C++编译器、Pillow及Noto CJK字体。该脚本不构建ESP-IDF镜像、不接触设备或服务器。页面通过`tools/generate_product_screens.py`在构建期生成，正常运行不加载额外字体。

版本、源码差异、兼容性及验证范围见[源码同步说明](../docs/firmware-1.6.8-source-sync.md)。现有云构建工作流仍负责私有配置注入；需要代理TLS覆盖时，将可选宏加入维护者的私有配置，不把真实主机写回源码。

## 页面与维护

首页、许可、四页手控、声音/静音/试听、语音阶段、网络、升级和电源页面使用统一静态资源及原触摸边界；额度/余额、任务计划和结果正文由云端提供。旧board_control/board_transport RPC源码仅保留参考，本版本默认构建使用BLE08，不启用旧RPC服务。

屏幕驱动保留BUSY超时与故障隔离，避免屏幕故障破坏USB维护。App所需的PCUSB INFO/AUTH身份与随机challenge证明、明确的STOP默认可用；STATUS/LOGS及其他完整控制台命令需要显式维护配置。网络、USB和任务状态应分层读取，不能把IP或HID回执当作整体成功。

官方恢复说明：[Waveshare FAQ](https://docs.waveshare.net/ESP32-S3-ePaper-1.54/FAQ/)；[硬件资料](https://docs.waveshare.com/ESP32-S3-ePaper-1.54)。只有在明确维护授权且升级已安全退出后，才按官方步骤进入下载模式；不要强制断电中断提交。侧键为BOOT/PWR，不能凭其他板型要求寻找RST。
