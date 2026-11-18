# App 配置与测试

Public sources contain no deployment address defaults. Configure your own HTTPS service before building. Missing service configuration raises a clear error and never falls back to another deployment.

Release builds require:
- CONTROLLER_BASE_URL: HTTPS service base, without credentials, query or fragment. Used by Dart and Android capture transport. Actions creates a private runtime JSON for Flutter and removes it after building.
- CONTROLLER_APPLICATION_ID: the existing installed application identity. Keep it and the same signing certificate for in-place updates.
- ANDROID_KEYSTORE_BASE64, ANDROID_STORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD: existing signing configuration.
- PRIVATE_ARTIFACT_PASSWORD: existing encrypted-artifact password.

CONTROLLER_DOWNLOAD_URL optionally supplies an HTTPS App update page. If absent the update action reports that the entry is not configured; it never opens a personal or placeholder site. No independent store URL is embedded.

Use the existing Actions secrets or maintainer-controlled environment injection. Do not commit runtime JSON, private addresses, signing material or decrypted artifacts. Local release signing uses ANDROID_KEYSTORE_PATH instead of the CI base64 secret.

## 本地回归

使用与 [App CI](../.github/workflows/app-build.yml) 一致的 Flutter SDK（本分支固定为 3.44.0）。Flutter 打包前需要 `app/assets/controller-button.onnx`；这是 CI 固定校验的模型，不随新版界面变更。请使用维护者提供的已核对资产或从已核对的发布 APK 中提取，并对照工作流中的模型 SHA-256 后再使用。不要提交模型文件、APK 或任何运行时密钥。直接运行 Widget 测试也需要此资源，不要用空文件冒充。

```sh
python3 tools/check_public_source.py
cd app
flutter pub get
flutter analyze lib test
flutter test --dart-define=CONTROLLER_BASE_URL=https://controller.test
python3 -m unittest discover -s ../tools -p test_prepare_app_config.py
```

`.test` 地址仅供测试，不是生产默认。Android 签名与生产运行配置由维护者配置；本地测试不需要生产签名或服务凭据。
