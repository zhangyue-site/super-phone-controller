import 'dart:async';
import 'package:flutter/material.dart';
import 'ble_ota_service.dart';
import 'control_client.dart';

class ControlScreen extends StatefulWidget {
  final BleOtaService service;
  final ControlClient? client;
  const ControlScreen({super.key, required this.service, this.client});
  @override
  State<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends State<ControlScreen> {
  late final ControlClient _client;
  final _text = TextEditingController();
  Map<String, dynamic> _task = {};
  String? _error;
  List<Map<String, dynamic>> _skills = [];
  bool _busy = false, _polling = false, _stopping = false;
  Timer? _timer;
  int _generation = 0;
  @override
  void initState() {
    super.initState();
    _client = widget.client ?? ControlClient();
    _timer = Timer.periodic(const Duration(seconds: 2), (_) => _poll());
  }

  Future<void> _poll() async {
    if (_polling ||
        _busy ||
        _stopping ||
        !_client.authorized ||
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
        await _client.authorize(widget.service);
      }
      if (generation != _generation) return;
      final result = await _client.command(operation,
          text: operation == 'prepare' ? _text.text.trim() : null,
          taskId: operation == 'prepare' ? null : _task['task_id'] as String?);
      if (mounted && generation == _generation) {
        setState(() {
          _task = result;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) setState(() => _error = '$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    if (_stopping) return;
    final generation = ++_generation;
    setState(() {
      _stopping = true;
      _busy = false;
      _error = null;
    });
    try {
      if (!_client.authorized) await _client.authorize(widget.service);
      final result = await _client.command('stop');
      if (mounted && generation == _generation) {
        setState(() {
          _task = result;
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
      if (!_client.authorized) await _client.authorize(widget.service);
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
      if (mounted && generation == _generation) setState(() => _task = result);
    } catch (e) {
      if (mounted && generation == _generation) setState(() => _error = '$e');
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _client.close();
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = _task['state'];
    final labels = {
      'pending': '等待你的确认',
      'queued': '已确认，等待控制板',
      'running': '控制板执行中',
      'done': _task['verified'] == true ? '结果已核验' : '执行结束，尚未核验',
      'error': '未完成',
      'stopped': '已停止',
      'expired': '已过期',
      'idle': '暂无任务',
      'replaced': '已替换',
      'saved': '已存为技能'
    };
    return Scaffold(
      appBar: AppBar(title: const Text('手机控制')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('文字下发 · 确认后执行',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        const Text(
            'A 通过蓝牙把通用指令交给控制板与云端 AI。B 需经 USB 连接、保持解锁并在被控手机页面授权整屏共享及 HID 操作。控制板需要可访问云端的网络。'),
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
                            style:
                                const TextStyle(fontWeight: FontWeight.bold)),
                        Text(skill['description'] as String? ?? ''),
                        for (final r in skill['requirements'] as List? ?? [])
                          Text('要求：$r'),
                        OutlinedButton(
                            onPressed: _busy || _stopping
                                ? null
                                : () => _useSkill(skill),
                            child: const Text('使用技能')),
                      ]))),
        const SizedBox(height: 16),
        TextField(
            controller: _text,
            maxLength: 120,
            minLines: 2,
            maxLines: 4,
            enabled: !_busy && !_stopping,
            decoration: const InputDecoration(
                labelText: '手机操作指令',
                hintText: '打开浏览器搜索天气 / 打开地图搜索公园',
                border: OutlineInputBorder())),
        FilledButton(
            onPressed: _busy || _stopping ? null : () => _run('prepare'),
            child: Text(_busy ? '正在请求…' : '生成计划')),
        if (_error != null)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error))),
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
                      ]))),
        const SizedBox(height: 12),
        const Text('A 下发指令并查看计划与结果，确认后由控制板操作 B。离开此页不会自动取消任务；也可使用控制板停止按钮。'),
      ]),
      bottomNavigationBar: SafeArea(
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.error),
                  onPressed: _stopping ? null : _stop,
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: Text(_stopping ? '正在请求停止…' : '停止手机操作')))),
    );
  }
}
