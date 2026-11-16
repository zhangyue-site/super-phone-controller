/// Passive connection facts only; never infers board HID permission.
(int, String) gatewayIndicator(
    {required bool hasClient, required bool sessionReady}) {
  if (!hasClient) return (3, '控制板未连接');
  if (!sessionReady) return (1, '控制链路待恢复');
  return (0, '控制链路已连接');
}
