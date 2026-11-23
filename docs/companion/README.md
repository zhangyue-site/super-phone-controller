# 大肥鱼陪伴页

ESP32-S3-Touch-AMOLED-2.16 的 0.6.47-amoled 固件开机进入「大肥鱼 · 陪着你」。在「手机控制器」页可点「返回陪伴」重新打开。陪伴页的「办件事」打开插件列表，有任务记录时可点「进度」查看状态。语音入口为「按住说话」，授权和设备配对沿用现有服务端配置。

固件构建沿用 [AMOLED 构建说明](../../firmware-amoled/README.md)。原版固件已经实板确认本地试音可闻，完整语音对话仍待实机验收。

## 配套语音服务

从仓库根目录启动 `python3 voice-service/companion_service.py`。服务默认监听回环地址的 19059 端口，可用 `COMPANION_PORT` 覆盖。设备通过已配置的 HTTPS 服务访问，鉴权沿用板端凭据。

- `COMPANION_PHONE_SERVER` 指向现有 `display_service` 包的父目录，默认使用此仓库。
- `COMPANION_DATA` 指向服务可写的独立数据目录。
- `COMPANION_CHAT_RUNTIME` 指向兼容现有 JSON 输入输出协议的对话运行脚本。
- `COMPANION_CHAT_EVENT_DIR` 可选，指向对话进度事件目录。
- `EPAPER_CONFIG` 与 `EPAPER_REMOTE_STATE` 分别指向服务端设备鉴权配置和远程任务状态文件。语音识别和播报沿用现有服务端的订阅配置。

## 角色素材许可

陪伴页的角色动画改编自 [PC2005-cloud/dsh-pet 的待机动画](https://github.com/PC2005-cloud/dsh-pet)。角色原型「溟月」由 [上善无形](https://space.bilibili.com/4456176) 创作，女仆鲸鱼娘形象由 [ZipZipPipe](https://space.bilibili.com/4168597) 设计。这里抽取 8 帧，调整尺寸并转换成 LVGL 索引色。素材及其衍生形式按 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 用于非商业用途，转载需署名并以相同许可共享。原素材及改编记录见 [SOURCE.json](../../firmware-amoled/main/pet/SOURCE.json)。
