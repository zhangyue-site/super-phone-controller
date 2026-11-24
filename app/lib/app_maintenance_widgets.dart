import 'dart:async';
import 'package:flutter/material.dart';
import 'app_maintenance.dart';
import 'control_client.dart';

class MaintenanceTile extends StatelessWidget {
  const MaintenanceTile(
      {super.key, this.target = false, this.cloudBound = false});
  final bool target, cloudBound;

  @override
  Widget build(BuildContext context) {
    final model = AppMaintenance.shared;
    return ListenableBuilder(
        listenable: model,
        builder: (context, _) => ListTile(
              leading: const Icon(Icons.system_update_alt),
              title: const Text('App 版本与更新'),
              subtitle: Text([
                if (model.installedCode != null) '本机 ${model.installedLabel}',
                model.summary,
                if (target && !cloudBound) '本地状态 · 尚无已授权的被控连接',
              ].join('\n')),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => showMaintenance(context, model),
            ));
  }
}

Future<void> showMaintenance(BuildContext context, AppMaintenance model) {
  return showDialog<void>(
      context: context,
      builder: (dialog) => ListenableBuilder(
          listenable: model,
          builder: (_, __) {
            final state = model.state;
            final transferring = state == AppUpdateState.downloading ||
                state == AppUpdateState.verifying;
            final installable = state == AppUpdateState.ready ||
                state == AppUpdateState.permissionRequired;
            return AlertDialog(
              title: const Text('App 版本与更新'),
              content: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('本机已安装：${model.installedLabel}'),
                    const SizedBox(height: 12),
                    Text(model.summary),
                    if (model.observedAt case final time?)
                      Text('本机观测 ${time.toLocal().toString().split('.').first}',
                          style: Theme.of(context).textTheme.bodySmall),
                    if (transferring) ...[
                      const SizedBox(height: 12),
                      LinearProgressIndicator(
                          value: state == AppUpdateState.downloading
                              ? model.progress
                              : null)
                    ],
                  ]),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(dialog),
                    child: const Text('关闭')),
                if (transferring)
                  TextButton(
                      onPressed: model.cancel, child: const Text('取消下载')),
                if (installable)
                  FilledButton(
                      onPressed: model.busy ? null : model.requestInstall,
                      child: Text(state == AppUpdateState.permissionRequired
                          ? '打开安装权限设置'
                          : '确认安装')),
                if (!installable && !transferring)
                  FilledButton(
                      onPressed: model.busy ? null : () => model.check(),
                      child: Text(switch (state) {
                        AppUpdateState.error => '重试',
                        AppUpdateState.available => '下载并校验',
                        AppUpdateState.installerOpened => '核对安装结果',
                        _ => '检查更新',
                      })),
              ],
            );
          }));
}

class RemoteMaintenanceCard extends StatefulWidget {
  const RemoteMaintenanceCard({super.key, required this.client});
  final ControlClient client;
  @override
  State<RemoteMaintenanceCard> createState() => _RemoteMaintenanceCardState();
}

class _RemoteMaintenanceCardState extends State<RemoteMaintenanceCard>
    with WidgetsBindingObserver {
  Map<String, dynamic>? row;
  String? reportedDevice;
  DateTime? readAt;
  bool busy = false, failed = false;
  Timer? timer;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _read());
    timer = Timer.periodic(const Duration(seconds: 30), (_) => _read());
  }

  @override
  void didUpdateWidget(RemoteMaintenanceCard old) {
    super.didUpdateWidget(old);
    if (!identical(old.client, widget.client)) {
      row = null;
      failed = false;
      _read();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _read();
  }

  Future<void> _read() async {
    if (!mounted || busy || ModalRoute.of(context)?.isCurrent == false) return;
    final life = WidgetsBinding.instance.lifecycleState;
    if (life != null && life != AppLifecycleState.resumed) return;
    final client = widget.client;
    final device = client.deviceId;
    if (!client.canReadStatus || device == null) return;
    busy = true;
    try {
      final value = await client.readAppMaintenance();
      if (mounted &&
          identical(client, widget.client) &&
          device == client.deviceId &&
          client.canReadStatus) {
        setState(() {
          row = value;
          reportedDevice = device;
          readAt = DateTime.now();
          failed = false;
        });
      }
    } catch (_) {
      if (mounted &&
          identical(client, widget.client) &&
          device == client.deviceId) {
        setState(() => failed = true);
      }
    } finally {
      busy = false;
    }
  }

  @override
  void dispose() {
    timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final data =
        widget.client.canReadStatus && widget.client.deviceId == reportedDevice
            ? row
            : null;
    String text = failed ? '未取得最新上报，请稍后刷新' : '尚无被控手机上报';
    if (data != null) {
      const labels = {
        'idle': '等待检查',
        'checking': '检查更新中',
        'current': '当前版本已是最新',
        'available': '有新版可下载',
        'downloading': '正在下载',
        'verifying': '校验中',
        'ready': '已校验，等待本人确认安装',
        'permission_required': '等待本人允许安装',
        'installer_opened': '已打开系统安装器，结果待核实',
        'error': '更新未完成',
      };
      final age = (data['ageSeconds'] as int) +
          DateTime.now().difference(readAt!).inSeconds;
      final stale = age > 90 ? ' · 上报已过期' : '';
      final stamp =
          DateTime.tryParse(data['receivedAt'] as String? ?? '')?.toLocal();
      final when = stamp == null ? '接收时间未知' : stamp.toString().split('.').first;
      text =
          '已装 ${data['installedName']}（${data['installedCode']}） · ${labels[data['state']] ?? '未知'}'
          '${data['targetCode'] is int && data['targetCode'] != data['installedCode'] ? ' · 目标 ${data['targetCode']}' : ''}'
          '\n上次云端接收 $when$stale${failed ? ' · 本次刷新失败' : ''}';
    }
    return Card(
        child: ListTile(
            leading: const Icon(Icons.phone_android_outlined),
            title: const Text('被控手机的 App 维护状态'),
            subtitle: Text(text),
            trailing: IconButton(
                tooltip: '刷新被控手机维护状态',
                icon: const Icon(Icons.refresh),
                onPressed: _read)));
  }
}
