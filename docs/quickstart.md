# 自行部署与离线验证

公开源代码基线的 Flutter 版本号为 **1.3.9+46**。组件以 Git 提交标识版本，固件另用 `PROJECT_VER` 标识实际构建。应用和固件的签名、配对和 OTA 由部署者配置。

## 协调服务

需要 Python 3.11+。在仓库根目录启动本机演练，使用独立状态和临时设备令牌。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'Pillow>=12,<13' -r requirements-keyboard.txt
python tools/run_offline_tests.py

umask 077
demo="$(mktemp -d)"
export EPAPER_STATE="$demo/state" EPAPER_CONFIG="$demo/devices.json"
export EPAPER_MODEL_CONFIG="$demo/models.json" EPAPER_PORT=18943
mkdir "$EPAPER_STATE"
printf '%s\n' '{"demo":"synthetic-local-test"}' > "$EPAPER_CONFIG"
printf '%s\n' '{"models":{"providers":{}}}' > "$EPAPER_MODEL_CONFIG"
python -m display_service.app
```

另开终端，以合成令牌验证本机鉴权及状态接口。

```sh
curl -fsS -H 'Authorization: Bearer synthetic-local-test' http://127.0.0.1:18943/status
```

实际部署使用独立服务账号、TLS、每设备独立令牌、受保护的配置文件和可写状态目录。参见 [部署示例](../deploy/README.md)及[服务配置](../display_service/README.md)。真实远控还需启用 `EPAPER_REMOTE_CONTROL=1`，完成 App 配对、目标设备系统共享、板端本地 HID 许可和与固件匹配的传输。服务持有队列、短期授权、帧和执行回执。

## Android 和 iOS

使用 Flutter 3.44.0。Android 配置 JDK 17 和 Android SDK，iOS 配置 macOS、Xcode 和 CocoaPods，并按项目 CI 使用 CocoaPods。

```sh
cd app
flutter pub get
flutter test --dart-define=CONTROLLER_BASE_URL=https://controller.test
flutter build apk --debug --dart-define=CONTROLLER_BASE_URL=https://controller.test
# 在 macOS 上将 simulator_id 设为已启动的 iOS 模拟器 ID
flutter test integration_test/startup_test.dart -d "$simulator_id" \
  --dart-define=CONTROLLER_BASE_URL=https://controller.test
# 构建无签名的 iPhone 设备版本
flutter build ios --release --no-codesign --dart-define=CONTROLLER_BASE_URL=https://controller.test
```

`controller.test` 供构建和测试。连接自建服务时填自己的 HTTPS 地址。iOS 真机需部署者签名，配置 `APP_BUNDLE_ID`、`BROADCAST_BUNDLE_ID` 和 Runner 与广播扩展共享的 Keychain access group。发起任务角色通过配对和服务 API 发起任务。被控角色另需 ReplayKit 系统广播、捕获授权、画面上传及板端 HID，最后用动作后画面核验。两种角色分别验收。

## ESP32-S3

当前公开集成入口为 `firmware-epaper/`。`firmware/` 是早期原型，`firmware-recovery/` 是单独的恢复工程。AMOLED 的公开开发源码位于 [0.6.31 分支提交](https://github.com/zhangyue-site/super-phone-controller/tree/c2fe1ee8f495cc56f4903186bad010e1b5721123/firmware-amoled)，使用 ESP-IDF 5.5.2，接口和板型需独立核对。

在已初始化 ESP-IDF 6.0 或 5.5.2 的 shell 执行构建命令，生成带占位身份的开发镜像。

```sh
cd firmware-epaper
cp -n main/device_config.example.h main/device_config.h
cp -n main/device_adb_keys.example.h main/device_adb_keys.h
idf.py -DIDF_TARGET=esp32s3 -DPROJECT_VER=0.0.1-public \
  -DSDKCONFIG=sdkconfig.usb-local \
  -DSDKCONFIG_DEFAULTS='sdkconfig.defaults;sdkconfig.usb-local.defaults' \
  -B build-public build
```

实际部署按板型、分区、协议和自建服务配置设备身份。占位镜像用于编译核验。旧固件工作流含可选 OTA 发布步骤，纯构建验证应在隔离环境使用上述命令。工作流只有在使用全套占位配置时才上传构建产物。发布镜像前逐项核对板型、构建版本、OTA 槽容量和 SHA-256，携带设备身份的镜像保存在私有交付渠道。

## 安装任务规划 Skill

将整个 `skills/phone-control-verification` 目录放到项目 `.agents/skills/` 下，或复制到自己的 Codex 用户技能目录。显式调用 `$phone-control-verification`，并提供公开仓库检出目录。可直接执行 Skill 中的离线演练。任务规划、页面判断、有限恢复和验收可复用，真实运行仍需要上述服务和授权设备。
