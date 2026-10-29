# App configuration

Public sources contain no deployment address defaults. Configure your own HTTPS service before building. Missing service configuration raises a clear error and never falls back to another deployment.

Release builds require:
- CONTROLLER_BASE_URL: HTTPS service base, without credentials, query or fragment. Used by Dart and Android capture transport. Actions creates a private runtime JSON for Flutter and removes it after building.
- CONTROLLER_APPLICATION_ID: the existing installed application identity. Keep it and the same signing certificate for in-place updates.
- ANDROID_KEYSTORE_BASE64, ANDROID_STORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD: existing signing configuration.
- PRIVATE_ARTIFACT_PASSWORD: existing encrypted-artifact password.

CONTROLLER_DOWNLOAD_URL optionally supplies an HTTPS App update page. If absent the update action reports that the entry is not configured; it never opens a personal or placeholder site. No independent store URL is embedded.

Use the existing Actions secrets or maintainer-controlled environment injection. Do not commit runtime JSON, private addresses, signing material or decrypted artifacts. Local release signing uses ANDROID_KEYSTORE_PATH instead of the CI base64 secret.

For isolated tests use:
```sh
flutter test --dart-define=CONTROLLER_BASE_URL=https://controller.test
python3 -m unittest discover -s ../tools -p test_prepare_app_config.py
```
The .test hostname is only an explicit test fixture; it is not a production default.
