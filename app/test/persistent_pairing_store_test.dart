import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/controller_pairing_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
      'encrypted native storage roundtrip retains binding after ticket expires',
      () async {
    String? stored;
    const channel = MethodChannel('pcflash/app');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'saveControllerPairing') {
        stored = (call.arguments as Map)['value'] as String;
      }
      if (call.method == 'clearControllerPairing') stored = null;
      return call.method == 'readControllerPairing' ? stored : null;
    });
    addTearDown(() => TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null));
    final pairing = ControllerPairing('t' * 43, 'test-board',
        DateTime.now().subtract(const Duration(days: 1)),
        bindingToken: 'b' * 43);
    await ControllerPairingStore.save(pairing);
    expect(stored, isNotNull);
    final raw = jsonDecode(stored!) as Map;
    expect(raw.containsKey('code'), isFalse);
    expect((await ControllerPairingStore.read())!.bindingToken, 'b' * 43);
    await ControllerPairingStore.clear();
    expect(await ControllerPairingStore.read(), isNull);
  });
}
