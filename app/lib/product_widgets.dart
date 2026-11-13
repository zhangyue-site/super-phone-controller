import 'package:flutter/material.dart';

String productError(Object error) {
  var text = error.toString().replaceFirst(
      RegExp(r'(FormatException|StateError|Bad state|Unsupported operation):\s*'), '');
  if (text.contains('usb_window') || text.contains('USB窗口')) {
    return '控制板连接检查暂不可用。画面共享会保留，请稍后重新检查。';
  }
  if (text.contains('键盘输入')) return '键盘输入未完成，请检查被控手机的输入框与可见候选，再重新规划。';
  if (text.contains('系统已停止')) {
    return '屏幕共享已结束，请在被控手机主动开始共享。';
  }
  return text
      .replaceAll('HTTP', '云端连接')
      .replaceAll('HID', '手机操作许可')
      .replaceAll('nonce', '连接检查')
      .replaceAll('USB窗口', '连接检查')
      .replaceAll('Relay', '手机中转')
      .replaceAll('ticket', '云端授权');
}

class ProductError extends StatelessWidget {
  const ProductError(this.message, {super.key});
  final String message;
  @override
  Widget build(BuildContext context) => Semantics(
      liveRegion: true,
      child: Card(
          color: Theme.of(context).colorScheme.errorContainer,
          child: Padding(
              padding: const EdgeInsets.all(16),
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(Icons.info_outline,
                    color: Theme.of(context).colorScheme.onErrorContainer),
                const SizedBox(width: 12),
                Expanded(
                    child: Text(productError(message),
                        style: TextStyle(
                            color: Theme.of(context)
                                .colorScheme
                                .onErrorContainer)))
              ]))));
}

class TargetStatusOverview extends StatelessWidget {
  const TargetStatusOverview(
      {super.key,
      required this.board,
      required this.capture,
      required this.permission,
      required this.network,
      this.error});
  final String board, capture, permission, network;
  final String? error;
  @override
  Widget build(BuildContext context) => Column(children: [
        Card(
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(children: [
                  for (final item in [
                    (Icons.usb, '控制板与 USB', board),
                    (Icons.screen_share_outlined, '整屏共享', capture),
                    (Icons.cloud_outlined, '云端任务服务', network),
                    (Icons.touch_app_outlined, '操作许可', permission),
                  ])
                    Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(item.$1, size: 22),
                              const SizedBox(width: 12),
                              Expanded(
                                  child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                    Text(item.$2,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleSmall),
                                    const SizedBox(height: 4),
                                    Text(item.$3),
                                  ])),
                            ])),
                ]))),
        if (error != null) ProductError(error!),
      ]);
}
