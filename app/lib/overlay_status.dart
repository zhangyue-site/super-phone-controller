/// Passive connection facts only; never infers board HID permission.
(int, String) gatewayIndicator(
    {required bool hasClient, required bool sessionReady}) {
  if (!hasClient) return (3, '本机未中转');
  if (!sessionReady) return (1, '本机中转待恢复');
  return (0, '本机中转已连接');
}
