import 'dart:async';
import 'package:flutter/material.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';
import 'controller_pairing_store.dart';
import 'controller_local_vision.dart';
import 'controller_model_status.dart';
import 'product_widgets.dart';
import 'product_settings.dart';
import 'controller_task_context.dart';
import 'task_frame_preview.dart';

class ControlScreen extends StatefulWidget {
  final BleOtaService? service;
  final ControlClient? client;
  final ControllerLocalVision Function(ControlClient)? visionFactory;
  const ControlScreen(
      {super.key, this.service, this.client, this.visionFactory});
  @override
  State<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends State<ControlScreen>
    with WidgetsBindingObserver {
  late final ControlClient _client;
  final _text = TextEditingController();
  final _scroll = ScrollController();
  Map<String, dynamic> _task = {};
  String? _error;
  List<Map<String, dynamic>> _skills = [];
  bool _busy = false, _polling = false, _stopping = false;
  bool _restoringTask = false, _latestTaskChecked = false;
  Timer? _timer, _visionTimer;
  ControllerLocalVision? _vision;
  bool _stopUnconfirmed = false;
  bool _foreground = true, _visionActive = false, _visionStopped = false;
  bool get _taskTerminal =>
      _task["terminal"] == true ||
      const {
        "done",
        "error",
        "stopped",
        "failed",
        "cancelled",
        "expired",
        "replaced",
        "saved"
      }.contains(_task["state"]);
  int _visionGeneration = 0;
  bool get _visible => mounted && (ModalRoute.of(context)?.isCurrent ?? false);
  bool _currentObservation(
          String taskId, int generation, int visionGeneration) =>
      mounted &&
      _foreground &&
      _visible &&
      !_stopping &&
      !_visionStopped &&
      !_taskTerminal &&
      _client.isPaired &&
      _client.authorized &&
      generation == _generation &&
      visionGeneration == _visionGeneration &&
      _task['task_id'] == taskId &&
      _task['state'] == 'running';

  void _visionChanged() {
    if (mounted) setState(() {});
  }

  void _pauseVision() {
    _visionGeneration++;
    _visionActive = false;
    _vision?.suspend();
  }

  void _prepareVision() {
    if (!mounted ||
        !_client.isPaired ||
        !_client.authorized ||
        _visionStopped ||
        !_foreground ||
        !_visible ||
        _stopping) {
      return;
    }
    _vision ??= (widget.visionFactory?.call(_client) ??
        ControllerLocalVision(_client))
      ..addListener(_visionChanged);
    _visionActive = true;
    unawaited(_vision!.prepare());
  }

  void _observeVision() {
    if (!mounted) return;
    if (!_client.isPaired ||
        !_client.authorized ||
        _visionStopped ||
        !_foreground ||
        !_visible ||
        _stopping) {
      if (_visionActive) _pauseVision();
      return;
    }
    if (_taskTerminal) {
      if (_visionActive) _pauseVision();
      return;
    }
    if (_task['state'] != 'running') return;
    if (!_visionActive) _prepareVision();
    final taskId = _task['task_id'];
    final generation = _generation;
    final visionGeneration = _visionGeneration;
    if (taskId is String &&
        _currentObservation(taskId, generation, visionGeneration)) {
      unawaited(_vision?.observe(taskId,
              isCurrent: () =>
                  _currentObservation(taskId, generation, visionGeneration)) ??
          Future<void>.value());
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_visible && _visionActive) {
      _pauseVision();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (!_foreground) {
      if (_visionActive) _pauseVision();
    } else if (!_taskTerminal && !_visionStopped) {
      _prepareVision();
    }
  }

  int _generation = 0;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _foreground = WidgetsBinding.instance.lifecycleState == null ||
        WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;
    _client = widget.client ?? ControlClient();
    unawaited(_connect());
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
    _visionTimer = Timer.periodic(
        const Duration(milliseconds: 300), (_) => _observeVision());
  }

  Future<void> _connect() async {
    final generation = _generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _authorize();
      _rememberPairing();
      await _restoreLatestTask();
      if (mounted && generation == _generation && !_taskTerminal) {
        _prepareVision();
      }
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() => _error = '云端控制连接失败：$e');
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _authorize() async {
    if (_client.authorized) return;
    final service = widget.service;
    if (service == null) throw StateError('控制连接已失效，请返回重新绑定被控手机');
    await _client.authorize(service);
  }

  DateTime? _storedPairingExpiry;
  void _rememberPairing() {
    if (!mounted) return;
    final pairing = _client.restorablePairing;
    if (pairing == null || pairing.expires == _storedPairingExpiry) return;
    _storedPairingExpiry = pairing.expires;
    unawaited(ControllerPairingStore.save(pairing));
  }

  /// Restore display state only. This never prepares, confirms or replays an action.
  Future<void> _restoreLatestTask() async {
    if (_restoringTask ||
        _latestTaskChecked ||
        _task.isNotEmpty ||
        !_foreground ||
        _stopping ||
        !_client.isPaired ||
        !_client.authorized ||
        !_client.canReadStatus) {
      return;
    }
    final device = _client.deviceId;
    if (device == null || !RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(device)) {
      return;
    }
    final binding = _client.restorablePairing?.bindingToken;
    final generation = _generation;
    bool current() =>
        mounted &&
        _foreground &&
        !_stopping &&
        generation == _generation &&
        _task.isEmpty &&
        _client.isPaired &&
        _client.authorized &&
        _client.canReadStatus &&
        _client.deviceId == device &&
        _client.restorablePairing?.bindingToken == binding;
    _restoringTask = true;
    try {
      // Omitting task_id asks for this authenticated owner's latest task.
      // The service never selects another controller's task by device alone.
      final result = await _client.command('status');
      if (!current()) return;
      if (result['state'] == 'idle') {
        _latestTaskChecked = true;
        return;
      }
      final ident = result['task_id'];
      if (ident is! String ||
          !RegExp(r'^[0-9a-f]{32}$').hasMatch(ident) ||
          result['state'] is! String) {
        throw const FormatException('任务恢复响应无效');
      }
      setState(() {
        _task = Map<String, dynamic>.from(result);
        _latestTaskChecked = true;
        _error = null;
      });
    } catch (e) {
      if (current()) setState(() => _error = '任务进度暂未恢复：$e');
    } finally {
      _restoringTask = false;
    }
  }

  Future<void> _poll() async {
    try {
      await _client.refresh();
      _rememberPairing();
      if (mounted && !_client.authorized) {
        setState(() => _error = _client.connectionStatus);
      } else if (mounted && _client.ownsGateway) {
        setState(
            () {}); // Render board diagnostics even when no task is active.
      }
    } catch (e) {
      if (mounted) setState(() => _error = '连接续期失败：$e');
    }
    if (!_busy && !_stopping && _task.isEmpty && !_latestTaskChecked) {
      await _restoreLatestTask();
    }
    if (_polling ||
        _busy ||
        _stopping ||
        !_client.canReadStatus ||
        _task['state'] == 'pending' ||
        _task['task_id'] == null ||
        _task['terminal'] == true) {
      return;
    }
    _polling = true;
    final generation = _generation;
    try {
      final result =
          await _client.command('status', taskId: _task['task_id'] as String);
      if (mounted && generation == _generation) {
        setState(() {
          _task = result;
          if (result['state'] == 'stopped' && result['stopConfirmed'] == true) {
            _stopUnconfirmed = false;
          }
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) setState(() => _error = '$e');
    } finally {
      _polling = false;
    }
  }

  Future<void> _run(String operation) async {
    if (_busy || _stopping) return;
    if (operation == 'prepare') {
      _visionStopped = false;
      _prepareVision();
    }
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (!_client.authorized) {
        if (operation != 'prepare') {
          throw const FormatException('授权失效，请重新生成计划后确认');
        }
        await _authorize();
      }
      if (generation != _generation) return;
      final result = await _client.command(operation,
          text: operation == 'prepare' ? _text.text.trim() : null,
          taskId: operation == 'prepare' ? null : _task['task_id'] as String?);
      if (mounted && generation == _generation) {
        setState(() {
          _task = result;
          if (result['state'] == 'stopped' && result['stopConfirmed'] == true) {
            _stopUnconfirmed = false;
          }
          _error = null;
        });
        if (operation == 'prepare') _showCurrentTask();
      }
    } catch (e) {
      if (mounted && generation == _generation) setState(() => _error = '$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    if (_stopping) return;
    _visionStopped = true;
    _pauseVision();
    final generation = ++_generation;
    setState(() {
      _stopUnconfirmed = true;
      _stopping = true;
      _busy = false;
      _error = null;
    });
    try {
      final result =
          await _client.command('stop', taskId: _task['task_id'] as String?);
      if (mounted && generation == _generation) {
        setState(() {
          _task = result;
          if (result['state'] == 'stopped' && result['stopConfirmed'] == true) {
            _stopUnconfirmed = false;
          }
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = '停止请求未确认：$e。请使用板子上的停止按钮。');
    } finally {
      if (mounted) setState(() => _stopping = false);
    }
  }

  Future<void> _loadSkills() async {
    if (_busy || _stopping) return;
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (!_client.authorized) await _authorize();
      if (generation != _generation) return;
      final result = await _client.command('skills');
      if (mounted && generation == _generation) {
        setState(() {
          _skills = (result['skills'] as List)
              .map((v) => Map<String, dynamic>.from(v as Map))
              .toList();
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) setState(() => _error = '$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _useSkill(Map<String, dynamic> skill) async {
    final parameters = (skill['parameters'] as List? ?? [])
        .map((v) => Map<String, dynamic>.from(v as Map))
        .toList();
    final controllers = {
      for (final p in parameters)
        p['name'] as String:
            TextEditingController(text: p['value'] as String? ?? '')
    };
    final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: Text(skill['name'] as String),
                content: SingleChildScrollView(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(skill['description'] as String? ?? ''),
                  for (final r in skill['requirements'] as List? ?? [])
                    Text('要求：$r'),
                  for (final p in parameters)
                    TextField(
                        controller: controllers[p['name']],
                        maxLength: 120,
                        decoration: InputDecoration(
                            labelText:
                                p['label'] as String? ?? p['name'] as String)),
                ])),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('取消')),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('预览计划'))
                ]));
    final values = {
      for (final e in controllers.entries) e.key: e.value.text.trim()
    };
    Future<void>.delayed(const Duration(milliseconds: 350), () {
      for (final c in controllers.values) {
        c.dispose();
      }
    });
    if (accepted != true || !mounted) return;
    final generation = ++_generation;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await _client.command('skill',
          skillId: skill['id'] as String, parameters: values);
      if (mounted && generation == _generation) {
        setState(() => _task = result);
        _showCurrentTask();
      }
    } catch (e) {
      if (mounted && generation == _generation) setState(() => _error = '$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _visionTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    _vision?.removeListener(_visionChanged);
    _vision?.suspend();
    unawaited(_vision?.close() ?? Future<void>.value());
    _client.close();
    _scroll.dispose();
    _text.dispose();
    super.dispose();
  }

  void _showCurrentTask() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _scroll.hasClients) _scroll.jumpTo(0);
    });
  }

  Future<void> _openSettings() async {
    _pauseVision();
    var pending = false;
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => StatefulBuilder(
          builder: (settingsContext, update) => Scaffold(
                body:
                    ProductSettingsScreen(client: _client, diagnostic: _error),
                bottomNavigationBar: SafeArea(
                    child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                        backgroundColor: Theme.of(context).colorScheme.error),
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: Text(pending
                        ? '正在请求停止…'
                        : _stopUnconfirmed
                            ? '停止未确认 · 再次请求'
                            : '停止手机操作'),
                    onPressed: pending
                        ? null
                        : () async {
                            update(() => pending = true);
                            await _stop();
                            if (settingsContext.mounted) {
                              update(() => pending = false);
                            }
                          },
                  ),
                )),
              )),
    ));
    if (mounted && !_taskTerminal && !_visionStopped) _prepareVision();
  }

  @override
  Widget build(BuildContext context) {
    final state = _task['state'];
    final previewTaskId = _task['task_id'];
    final labels = {
      'pending': '等待你的确认',
      'queued': '已确认，等待控制板',
      'running': '控制板执行中',
      'done': _task['verified'] == true ? '结果已核验' : '执行结束，尚未核验',
      'error': '未完成',
      'stopped': _task['stopConfirmed'] == true ? '已停止' : '后续任务已取消，设备停止待确认',
      'stopping': '停止请求已发送，等待板端确认',
      'failed': '任务失败',
      'cancelled': '已取消',
      'expired': '已过期',
      'idle': '暂无任务',
      'replaced': '已替换',
      'saved': '已存为技能'
    };
    return Scaffold(
      appBar: AppBar(title: const Text('任务'), actions: [
        IconButton(
            tooltip: '设备与设置',
            onPressed: _openSettings,
            icon: const Icon(Icons.settings_outlined))
      ]),
      body: ListView(
          controller: _scroll,
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null) ProductError(_error!),
            if (_stopUnconfirmed)
              Card(
                  child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Semantics(
                          liveRegion: true,
                          child: const Text(
                              '停止请求尚未确认。已发动作结果未知；必要时请使用板子上的停止按钮。')))),
            if (_task.isNotEmpty)
              Card(
                  child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text(labels[state] ?? '任务状态',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold, fontSize: 18)),
                            const SizedBox(height: 8),
                            Text(_task['reply'] as String? ?? ''),
                            if (state == 'pending')
                              FilledButton(
                                  onPressed: _busy || _stopping
                                      ? null
                                      : () => _run('confirm'),
                                  child: const Text('确认执行')),
                            if (state == 'done' && _task['verified'] == true)
                              OutlinedButton(
                                  onPressed: _busy || _stopping
                                      ? null
                                      : () => _run('save'),
                                  child: const Text('存为技能')),
                            TextButton(
                                onPressed: _busy || _stopping
                                    ? null
                                    : () => _run('status'),
                                child: const Text('刷新状态')),
                            ControllerTaskContext(
                                task: _task,
                                deviceId: _client.deviceId,
                                connected:
                                    _client.authorized && _error == null),
                            const Divider(),
                            if (_client.isPaired &&
                                _client.authorized &&
                                state == 'running' &&
                                !_visionStopped &&
                                !_stopping)
                              TaskFramePreview(
                                source: _client,
                                taskId: _task['task_id'] as String? ?? '',
                                sourceLabel: '当前已绑定被控手机',
                                isCurrent: () =>
                                    mounted &&
                                    _foreground &&
                                    _visible &&
                                    !_stopping &&
                                    !_visionStopped &&
                                    _client.authorized &&
                                    _task['state'] == 'running' &&
                                    _task['task_id'] == previewTaskId,
                              ),
                            if (state == 'done')
                              const Text('结果由服务核验，本端未提供关联结果图'),
                          ]))),
            const Text('发给龙虾',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(_busy
                ? '正在生成任务确认信息…'
                : _client.authorized
                    ? '说说你想让手机做什么，核对任务后执行。'
                    : '控制连接已结束'),
            if (!_busy && !_client.authorized)
              OutlinedButton(
                  onPressed: _connect, child: const Text('重新连接云端控制')),
            if (_task.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Row(children: [
                  Icon(
                      _client.authorized
                          ? Icons.check_circle_outline
                          : Icons.link_off,
                      size: 18),
                  const SizedBox(width: 8),
                  Text(_client.authorized ? '连接已建立' : '需要重新连接'),
                ]),
              ),
            if (_client.supportsSkillReplay)
              OutlinedButton(
                  onPressed: _busy || _stopping ? null : _loadSkills,
                  child: const Text('查看专项技能')),
            for (final skill in _skills)
              Card(
                  child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text(skill['name'] as String,
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold)),
                            Text(skill['description'] as String? ?? ''),
                            for (final r
                                in skill['requirements'] as List? ?? [])
                              Text('要求：$r'),
                            OutlinedButton(
                                onPressed: _busy || _stopping
                                    ? null
                                    : () => _useSkill(skill),
                                child: const Text('使用技能')),
                          ]))),
            const SizedBox(height: 16),
            if (_task.isEmpty) ...[
              Text('可以先试试', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final example in ['打开设置', '打开设置搜索电池'])
                  ActionChip(
                      label: Text(example),
                      onPressed: _busy || _stopping
                          ? null
                          : () {
                              _text.text = example;
                            }),
              ]),
              const SizedBox(height: 12),
            ],
            TextField(
                controller: _text,
                maxLength: 120,
                minLines: 2,
                maxLines: 4,
                enabled: !_busy && !_stopping,
                decoration: const InputDecoration(
                    labelText: '想让被控手机做什么？',
                    helperText: '目标：当前已连接手机',
                    helperMaxLines: 2,
                    hintText: '打开设置 / 打开设置搜索电池',
                    border: OutlineInputBorder())),
            FilledButton(
                key: const ValueKey('phone-task-prepare'),
                onPressed: _busy || _stopping ? null : () => _run('prepare'),
                child: Text(_busy ? '正在准备任务…' : '查看并确认任务')),
            if (_client.isPaired && _vision != null)
              ControllerModelStatus(vision: _vision!, onRetry: _prepareVision),
            const SizedBox(height: 12),
            const Text('执行时可随时请求停止，结果以真实画面核验为准。'),
          ]),
      bottomNavigationBar: SafeArea(
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.error),
                  onPressed: _stopping ? null : _stop,
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: Text(_stopping
                      ? '正在请求停止…'
                      : _stopUnconfirmed
                          ? '停止未确认 · 再次请求'
                          : '停止手机操作')))),
    );
  }
}
