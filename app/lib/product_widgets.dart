import 'package:flutter/material.dart';

class ProductDialog extends StatelessWidget {
  const ProductDialog({
    super.key,
    required this.icon,
    required this.title,
    required this.details,
    required this.actions,
  });

  final IconData icon;
  final String title;
  final List<Widget> details, actions;

  @override
  Widget build(BuildContext context) => AlertDialog(
        scrollable: true,
        insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
        icon: Icon(icon, color: Theme.of(context).colorScheme.primary),
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: details,
        ),
        actionsOverflowButtonSpacing: 8,
        actions: actions,
      );
}

class ProductDialogDetail extends StatelessWidget {
  const ProductDialogDetail(this.label, this.description, {super.key});

  final String label, description;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(description),
          ],
        ),
      );
}

class ProductHeader extends StatelessWidget {
  const ProductHeader({
    super.key,
    required this.icon,
    required this.label,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String label, title, description;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.primaryContainer,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              ProductIcon(icon),
              const SizedBox(width: 12),
              Expanded(
                child: Text(label,
                    style: theme.textTheme.labelLarge?.copyWith(
                        color: colors.onPrimaryContainer,
                        fontWeight: FontWeight.w700)),
              ),
            ]),
            const SizedBox(height: 16),
            Semantics(
              header: true,
              child: Text(title,
                  style: theme.textTheme.headlineSmall
                      ?.copyWith(color: colors.onPrimaryContainer)),
            ),
            const SizedBox(height: 8),
            Text(description,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: colors.onPrimaryContainer)),
          ],
        ),
      ),
    );
  }
}

class ProductIcon extends StatelessWidget {
  const ProductIcon(this.icon, {super.key});
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
          color: colors.surfaceContainerLow,
          borderRadius: BorderRadius.circular(14)),
      child: SizedBox.square(
          dimension: 44, child: Icon(icon, color: colors.primary, size: 22)),
    );
  }
}

class ProductSectionTitle extends StatelessWidget {
  const ProductSectionTitle(this.title, {super.key});
  final String title;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 20, 4, 8),
        child: Semantics(
            header: true,
            child: Text(title, style: Theme.of(context).textTheme.titleMedium)),
      );
}

class ProductActionBar extends StatelessWidget {
  const ProductActionBar({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
          color: colors.surfaceContainerLow,
          border: Border(top: BorderSide(color: colors.outlineVariant))),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: child,
        ),
      ),
    );
  }
}

ButtonStyle productStopButtonStyle(BuildContext context) {
  final colors = Theme.of(context).colorScheme;
  return FilledButton.styleFrom(
      backgroundColor: colors.error, foregroundColor: colors.onError);
}

String productError(Object error) {
  var text = error.toString().replaceFirst(
      RegExp(
          r'(FormatException|StateError|Bad state|Unsupported operation):\s*'),
      '');
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
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const ProductSectionTitle('连接与授权'),
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
                                  ProductIcon(item.$1),
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
