import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'control_client.dart';
import 'controller_gateway_screen.dart';
import 'control_screen.dart';

/// Controller phone A redeems a short-lived code explicitly shared by phone B.
class ControllerPairScreen extends StatefulWidget {
  const ControllerPairScreen(
      {super.key, this.clientFactory, this.connectedBuilder});
  final ControlClient Function()? clientFactory;
  final Widget Function(ControlClient client)? connectedBuilder;

  @override
  State<ControllerPairScreen> createState() => _ControllerPairScreenState();
}

class _ControllerPairScreenState extends State<ControllerPairScreen> {
  final _code = TextEditingController();
  final _form = GlobalKey<FormState>();
  ControlClient? _pending;
  bool _busy = false;
  int _generation = 0;
  String? _error;

  void _cancel() {
    _generation++;
    _pending?.close();
    _pending = null;
    setState(() => _busy = false);
  }

  Future<void> _paste() async {
    final generation = _generation;
    try {
      final value = await Clipboard.getData(Clipboard.kTextPlain);
      if (!mounted || _busy || generation != _generation) return;
      if (value?.text == null || value!.text!.trim().isEmpty) {
        setState(() => _error = '剪贴板中没有连接码，请在被控手机生成并复制。');
        return;
      }
      _code.text = value.text!.trim();
      setState(() => _error = null);
    } on PlatformException {
      if (mounted && !_busy && generation == _generation) {
        setState(() => _error = '无法读取剪贴板，请长按输入框手动粘贴连接码。');
      }
    }
  }

  Future<void> _connect() async {
    if (_busy || !_form.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    final generation = ++_generation;
    final client = (widget.clientFactory ?? ControlClient.new)();
    _pending = client;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await client.pair(_code.text.trim());
      if (!mounted || generation != _generation) {
        client.close();
        return;
      }
      _pending = null; // The connected route now owns this client.
      _code.clear();
      setState(() => _busy = false);
      await Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) =>
              widget.connectedBuilder?.call(client) ??
              ControlScreen(client: client)));
    } catch (_) {
      client.close();
      if (mounted && generation == _generation) {
        _pending = null;
        setState(() {
          _busy = false;
          _error = '连接失败。请确认网络正常，并在被控手机重新生成连接码后重试。';
        });
      }
    }
  }

  @override
  void dispose() {
    _generation++;
    _pending?.close();
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('连接被控手机')),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          Text('输入被控手机的连接码', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          const Text('在被控手机连接控制板后生成连接码。连接码为一次性使用，2分钟后过期。'),
          const SizedBox(height: 12),
          const Text('此手机用于发送任务和查看进度，无需共享此手机的屏幕。'),
          const SizedBox(height: 16),
          OutlinedButton.icon(
              onPressed: _busy
                  ? null
                  : () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => const ControllerGatewayScreen())),
              icon: const Icon(Icons.bluetooth),
              label: const Text('使用此手机中转蓝牙连接')),
          const Text('控制板可直接连接 Wi-Fi，也可通过一台手机中转蓝牙与网络；切换前请先释放原连接。'),
          const SizedBox(height: 24),
          Form(
              key: _form,
              child: TextFormField(
                controller: _code,
                enabled: !_busy,
                autocorrect: false,
                enableSuggestions: false,
                keyboardType: TextInputType.visiblePassword,
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => _connect(),
                decoration: const InputDecoration(
                    labelText: '一次性连接码',
                    hintText: '粘贴43位连接码',
                    helperText: '连接码仅用于本次连接，不会保存',
                    helperMaxLines: 2),
                validator: (value) =>
                    RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(value?.trim() ?? '')
                        ? null
                        : '请粘贴完整的43位连接码',
              )),
          const SizedBox(height: 8),
          Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                  onPressed: _busy ? null : _paste,
                  icon: const Icon(Icons.content_paste),
                  label: const Text('从剪贴板粘贴'))),
          const Text('仅在点击粘贴时读取剪贴板。', style: TextStyle(fontSize: 12)),
          if (_error != null) ...[
            const SizedBox(height: 16),
            Semantics(
                liveRegion: true,
                child: Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error))),
          ],
          const SizedBox(height: 24),
          FilledButton(
              onPressed: _busy ? null : _connect,
              child: Text(_busy ? '正在连接…' : '连接被控手机')),
          if (_busy) TextButton(onPressed: _cancel, child: const Text('取消连接')),
        ]),
      );
}
