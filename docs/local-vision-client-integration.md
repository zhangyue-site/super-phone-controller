# 端侧小模型接入（ZY-Button-v5）

服务端协议由 `display_service/local_vision.py` 定义（`/app-local-vision/{manifest,model,frame,result}`）。
本文件补客户端：`app/lib/local_vision_client.dart`。

## 一、依赖

```yaml
dependencies:
  onnxruntime: ^1.4.1   # Flutter ONNX Runtime（iOS/Android）
  image: ^4.2.0         # 纯 Dart 解码与缩放
```

## 二、模型

- 线上模型：`button-v5`（sha256 `f61ec1ac825d4472e4bc6f5432efed97880f5361fd52264d9a4069290652fb7b`，12.6MB）
- 注册表：`/opt/phone-controller-private/models/controller-button/manifest.json`（服务端校验通过）
- 输入 320×320，预处理 `stretch-rgb-0-1`（直接拉伸，无 letterbox），输出布局 `xywh-score`
- 训练：v3 基础上用 OmniParser 图标检测器蒸馏 264 张真机帧（221 train / 24 val）
- 实测：真机留出集检出 61 框（v3 为 21 框），置信度 0.6–0.86

## 三、调用时序

1. `ensureModel()` → 拉 manifest；sha 变化才下载模型并落盘缓存
2. `requestFrame(taskId)` → 服务端只在任务/取屏授权有效时返回帧
3. `infer(frame, model)` → 端侧 ONNX 推理（Pixel3/TFLite 同级 20–50ms，iPhone 更低）
4. `submit(taskId, frame, model, boxes, ms)` → 回传几何提示；服务端校验 frame_id/barrier/sequence/model_sha256 四元一致

## 四、接入点（建议）

- `control_screen.dart` / `screen_task_status.dart` 的屏幕任务循环里，拿到帧后先跑端侧推理；
  命中（有框且最高分 ≥ 0.5）→ 直接作为候选目标给现有决策层；否则回落云端 OCR/VLM。
- 注意：服务端**不授予动作权限**，本客户端只产出几何提示，点击仍走既有 HID 闸门。

## 五、降级

- 端侧引擎不可用（设备不支持/初始化失败）→ 直接跳过本客户端，维持现有云端链路；服务器侧另有
  `ui-merge`（v5 + OmniParser，POST `/detect_ui`）可作兜底，已验证 ~250ms。

## 六、回滚

- 服务端 manifest 改回 `button-v3`（v3 的 ONNX 仍在同目录，sha `f1a6c751…`）即可，无需发版。

## 七、iOS

同一份 `local_vision_client.dart` 在 iOS 直接可用：`onnxruntime_plus` 通过 `onnxruntime-objc`（iOS 11+）
提供运行时，项目 Podfile 为 iOS 15.0，无需额外改动；构建时 `pod install` 会拉取 framework。

### Core ML（可选，更低延迟）

v5 已转出 Core ML 包（Linux 上 coremltools 9.0 转换成功）：

- 下载：`https://jiujiu.zhangyue.site/models/zy-button-v5-coreml.tgz`（解包为 `best.mlpackage`，6.2MB）
- ONNX 对照：`https://jiujiu.zhangyue.site/models/zy-button-v5.onnx`（12.6MB，与注册表同源）

接入方式：把 `best.mlpackage` 加入 Runner target，用 Vision/CoreML 直接推理，输出为 320×320
坐标系的框；后处理与本客户端的 `_nms` 相同（xywh-score → 归一化 → NMS 0.45）。
如需保持单一实现，可先继续用 onnxruntime_plus，Core ML 作为后续优化项。
