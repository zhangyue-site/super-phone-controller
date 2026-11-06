class ControllerConfig {
  static const _configuredBase = String.fromEnvironment('CONTROLLER_BASE_URL');
  static String get base => validateBase(_configuredBase);

  static String validateBase(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      throw StateError('尚未配置有效的服务地址，请联系应用维护者');
    }
    return value.trim().replaceFirst(RegExp(r'/+$'), '');
  }
}
