import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'control_client.dart';
import 'controller_gateway_screen.dart';
import 'control_screen.dart';
import 'product_widgets.dart';

/// Controller redeems the binding code explicitly shared by the target.
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
          _error = '连接失败。请确认网络、绑定码及被控端连接；旧连接码失效时请重新生成连接码。输入已保留。';
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
          const ProductHeader(
            icon: Icons.devices_outlined,
            label: '控制手机',
            title: '让两台手机连接起来',
            description: '在另一台手机接好控制板并开始共享，再到「连接控制手机」查看绑定码。本机不用共享。',
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
              onPressed: _busy
                  ? null
                  : () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => const ControllerGatewayScreen())),
              icon: const Icon(Icons.bluetooth),
              label: const Text('使用此手机中转蓝牙连接')),
          const Text('板子已连 Wi-Fi 时，不用再开蓝牙中转。切换中转前，先释放原连接。'),
          const SizedBox(height: 24),
          Form(
              key: _form,
              child: TextFormField(
                controller: _code,
                enabled: !_busy,
                autocorrect: false,
                enableSuggestions: false,
                keyboardType: TextInputType.number,
                style: const TextStyle(
                    fontSize: 28,
                    letterSpacing: 6,
                    fontFeatures: [FontFeature.tabularFigures()]),
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => _connect(),
                decoration: const InputDecoration(
                    labelText: '4位绑定码',
                    hintText: '输入4位数字',
                    helperText: '使用被控手机显示的绑定码，不要转发给他人',
                    helperMaxLines: 2),
                validator: (value) =>
                    RegExp(r'^(?:[0-9]{4}|[A-Za-z0-9_-]{43})$')
                            .hasMatch(value?.trim() ?? '')
                        ? null
                        : '请输入4位数字绑定码，或完整43位旧连接码',
              )),
          if (_error != null) ProductError(_error!),
          TextButton(
              onPressed: _busy
                  ? null
                  : () => showDialog<void>(
                      context: context,
                      builder: (context) => ProductDialog(
                              icon: Icons.key_outlined,
                              title: '使用旧连接码',
                              details: const [
                                ProductDialogDetail('已有旧版连接码？',
                                    '把完整的 43 位旧码粘贴到绑定码输入框。旧码仍按原有效期使用。'),
                                ProductDialogDetail(
                                    '旧码失效时', '回到被控手机查看当前绑定码，不要反复提交过期旧码。'),
                              ],
                              actions: [
                                TextButton(
                                    onPressed: () => Navigator.pop(context),
                                    child: const Text('知道了'))
                              ])),
              child: const Text('使用43位旧连接码')),
          const SizedBox(height: 8),
          Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                  onPressed: _busy ? null : _paste,
                  icon: const Icon(Icons.content_paste),
                  label: const Text('从剪贴板粘贴'))),
          const Text('仅在点击粘贴时读取剪贴板。', style: TextStyle(fontSize: 12)),
        ]),
        bottomNavigationBar: SafeArea(
            child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                FilledButton(
                    onPressed: _busy ? null : _connect,
                    child: Text(_busy ? '正在连接…' : '连接被控手机')),
                if (_busy)
                  TextButton(onPressed: _cancel, child: const Text('取消连接')),
              ]),
        )),
      );
}
