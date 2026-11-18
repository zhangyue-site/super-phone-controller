import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'product_widgets.dart';

class AppRelease {
  static const channel = MethodChannel('pcflash/app');
  static Future<void> show(BuildContext context) async {
    String version;
    try {
      final value = await channel.invokeMapMethod<String, dynamic>('info');
      version =
          '${value?["versionName"] ?? "未知"}（${value?["versionCode"] ?? "未知"}）';
    } catch (_) {
      version = '暂时无法读取';
    }
    if (!context.mounted) return;
    String? failure;
    var opening = false;
    await showDialog<void>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
            builder: (stateContext, update) => ProductDialog(
                  icon: Icons.system_update_alt,
                  title: 'App 版本与更新',
                  details: [
                    ProductDialogDetail('本机已安装', version),
                    const ProductDialogDetail(
                        '更新手机 App', '从官方下载页获取同包名、同签名新版。安装时保留原应用，不要先卸载。'),
                    const ProductDialogDetail(
                        '更新控制板', '在设备维护里单独操作，不需要同时更新手机 App。'),
                    if (failure case final message?) ProductError(message),
                  ],
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(dialogContext),
                        child: const Text('关闭')),
                    FilledButton(
                        onPressed: opening
                            ? null
                            : () async {
                                update(() {
                                  opening = true;
                                  failure = null;
                                });
                                try {
                                  await channel
                                      .invokeMethod<void>('openDownload');
                                } catch (_) {
                                  if (stateContext.mounted) {
                                    update(() =>
                                        failure = '更新入口未配置或暂时无法打开，请联系应用维护者');
                                  }
                                } finally {
                                  if (stateContext.mounted) {
                                    update(() => opening = false);
                                  }
                                }
                              },
                        child: Text(opening ? '正在打开…' : '官方下载与更新')),
                  ],
                )));
  }
}
