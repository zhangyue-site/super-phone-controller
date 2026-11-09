# 模型接入和分发

## 端侧按钮检测

`app/lib/controller_model_runtime.dart` 使用 ONNX Runtime 隔离线程运行推理，`app/lib/button_detector.dart` 负责预处理、解码与抑制重叠框。服务端 `display_service/local_vision.py` 校验文件哈希并通过认证接口提供模型和接收帧绑定的观测。按钮几何信息不授予动作许可。

模型契约为一个名为 `images` 的 float32 NCHW 输入 `[1,3,320,320]`，RGB 拉伸至 320×320 后缩放到 0–1。单类别输出为 `[1,5,2100]`，每列依次为像素中心 x、中心 y、宽、高和 0–1 分数。模型为单文件 ONNX，最多 32 MiB。

从有权使用的来源自行获得兼容模型，再在支持 ONNX Runtime 的本机环境用合成 JPEG 验证。

```sh
cd app
flutter pub get
CONTROLLER_MODEL_SMOKE=/path/to/your/model.onnx flutter test test/local_model_real_test.dart
cd ..
python3 tools/prepare_local_model.py /path/to/your/model.onnx /path/to/new-model-directory --version my-export-v1
export CONTROLLER_LOCAL_MODEL_MANIFEST=/path/to/new-model-directory/manifest.json
```


macOS 上若 Flutter 的 shell 启动器未传递动态库路径，可直接用 Flutter SDK 中的 Dart 启动同一个测试。将 `flutter_sdk` 与 `ort_dir` 设置为本机 SDK 和 `libonnxruntime.1.15.1.dylib` 所在目录，在 `app/` 下运行：

```sh
CONTROLLER_MODEL_SMOKE=/path/to/your/model.onnx DYLD_LIBRARY_PATH="$ort_dir" \
  "$flutter_sdk/bin/cache/dart-sdk/bin/dart" \
  "$flutter_sdk/bin/cache/flutter_tools.snapshot" test --no-pub test/local_model_real_test.dart
```

部署时让服务账号只读访问该目录。准备工具校验大小、生成 SHA-256 和部署清单。实际张量兼容性由上面的原生运行测试确认。通过认证接口向配对设备传送模型前，需拥有面向这些设备分发该导出的权限。模型目录留在 Git 之外。

## 云端推理

视觉及对话客户端在 `display_service/general_vision.py`、`wechat_vision.py`、`conversation.py` 与 `model_routing.py`。部署者配置 `EPAPER_MODEL_CONFIG`，按权限选择 `EPAPER_VISION_PROVIDER` 和 `EPAPER_VISION_MODEL`。下面是配置形状，实际值从部署者有权使用的服务取得并保存在仓库外。

```json
{
  "models": {
    "providers": {
      "opencode-go": {
        "baseUrl": "https://opencode.ai/inference/go/openai/v1",
        "apiKey": "SET_OUTSIDE_GIT",
        "models": [{"id": "mimo-v2.6-flash"}]
      }
    }
  }
}
```

通用视觉的 Go 路由按源码固定到订阅端点，其他调用按各自适配器契约配置。Jev 适配器需要部署者自有的服务访问权限和独立凭据。语音订阅和本地 ASR 配置独立，见[服务配置](../display_service/README.md)。离线回归以模拟响应验证契约。

## 来源与再分发范围

| 项目 | 来源与许可 | 公开处理 |
| --- | --- | --- |
| 端侧检测训练检查点 | 未获得可追溯的训练基座、数据许可和检查点授权 | 由部署者自行获取，源码仓库仅提供推理接口 |
| 端侧检测浮点 ONNX 导出 | 未获得导出物的再分发许可，现场导出超过 32 MiB | 由部署者自行获取符合契约的导出 |
| 端侧检测 INT8 ONNX 导出 | 未获得量化导出物的再分发许可 | 由部署者自行获取 |
| 服务端现场 OCR 导出与预览识别适配 | 未获得可追溯的可分发权重清单 | 现场权重与候选代码单独保留，公开入口使用已审查的通用视觉或自备模型 |
| MiMo、DeepSeek、GLM、Jev 远端调用 | 本项目按各服务的访问条款调用 API，未收集可分发权重 | 部署者自行申请访问并配置 |
| ONNX Runtime | [Microsoft 上游 MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE)，二进制还附带[第三方通知](https://github.com/microsoft/onnxruntime/blob/main/ThirdPartyNotices.txt) | 由依赖管理器获取，分发成品时按实际版本附通知 |
| onnxruntime_plus 1.5.0 | [pub.dev MIT](https://pub.dev/packages/onnxruntime_plus/versions/1.5.0/license) | 由 Flutter 解析 |
| image 4.8.0 | [pub.dev MIT](https://pub.dev/packages/image/versions/4.8.0/license) | 由 Flutter 解析 |
| Pillow 12 | [上游 MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | 由 pip 解析 |
| pypinyin 0.55.0 | [上游 MIT](https://github.com/mozillazg/python-pinyin/blob/master/LICENSE.txt) | 由 pip 解析 |

固件及 App 的依赖由各构建工具按清单解析。发布二进制前，按实际解析结果另核对传递依赖、原生运行库和随包通知。项目自身许可见首页。

## 客户端和固件的直接依赖

以下对应当前 App 锁定版本和 ESP-IDF 构建清单。源码方案由依赖管理器获取这些包，成品分发另需保留适用的许可证与通知。

| 依赖 | 上游许可 |
| --- | --- |
| Flutter SDK | [BSD-3-Clause](https://github.com/flutter/flutter/blob/3.44.0/LICENSE) |
| cupertino_icons 1.0.9 | [MIT](https://pub.dev/packages/cupertino_icons/versions/1.0.9/license) |
| flutter_blue_plus 2.3.14 | [FlutterBluePlus License 1.6](https://pub.dev/packages/flutter_blue_plus/versions/2.3.14/license)，商业使用受单独授权约束 |
| file_picker 11.0.3 | [MIT](https://pub.dev/packages/file_picker/versions/11.0.3/license) |
| http 1.6.0 | [BSD-3-Clause](https://pub.dev/packages/http/versions/1.6.0/license) |
| crypto 3.0.8 | [BSD-3-Clause](https://pub.dev/packages/crypto/versions/3.0.8/license) |
| path_provider 2.1.6 | [BSD-3-Clause](https://pub.dev/packages/path_provider/versions/2.1.6/license) |
| intl 0.20.3 | [BSD-3-Clause](https://pub.dev/packages/intl/versions/0.20.3/license) |
| ESP-IDF 6.0 | [Apache-2.0 与各组件单独条款](https://github.com/espressif/esp-idf/blob/v6.0/LICENSE) |
| esp_codec_dev 1.6.2 | [Apache-2.0，内含需单独核对的厂商文件](https://components.espressif.com/components/espressif/esp_codec_dev/versions/1.6.2) |
| esp_tinyusb 2.4.0 | [Apache-2.0](https://components.espressif.com/components/espressif/esp_tinyusb/versions/2.4.0) |
| TinyUSB | [MIT](https://github.com/hathach/tinyusb/blob/master/LICENSE)，打包前核对实际使用的 Espressif 组件版本及其附带条款 |
