class ControllerConfig {
  static const base = String.fromEnvironment('CONTROLLER_BASE_URL',
      defaultValue: 'https://controller.example.invalid/phone-controller');
}
