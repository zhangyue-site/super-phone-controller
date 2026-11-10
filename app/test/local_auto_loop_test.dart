import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../lib/local_auto_loop.dart';

void main() {
  testWidgets('starts each native step only when offered for a capture',
      (tester) async {
    const channel = MethodChannel('pcflash/local-loop');
    final calls = <MethodCall>[];
    Map<String, Object> state = {};
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      switch (call.method) {
        case 'recognitionStatus':
          return state;
        case 'startBillOcr':
          state = {'autoEpoch': 101, 'autoStep': 'wait'};
          return true;
        case 'beginButtonRecognition':
          state = {'autoEpoch': 101, 'autoStep': 'wait'};
          return null;
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: LocalAutoLoopCard())),
    ));
    Future<void> poll() async {
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
    }

    Iterable<MethodCall> callsTo(String name) =>
        calls.where((call) => call.method == name);

    await poll();
    expect(callsTo('startBillOcr'), isEmpty);
    state = {'autoEpoch': 101, 'autoStep': 'ocr'};
    await poll();
    await poll();
    expect(callsTo('startBillOcr').single.arguments, {'autoEpoch': 101});
    expect(callsTo('beginButtonRecognition'), isEmpty);
    state = {'autoEpoch': 101, 'autoStep': 'buttons'};
    await poll();
    await poll();
    expect(
        callsTo('beginButtonRecognition').single.arguments, {'autoEpoch': 101});
    state = {'autoEpoch': 102, 'autoStep': 'ocr'};
    await poll();
    expect(callsTo('startBillOcr').last.arguments, {'autoEpoch': 102});
    await tester.pumpWidget(const SizedBox());
  });
}
