import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:pcflash/button_detector.dart';
import 'package:pcflash/task_frame_preview.dart';

const task = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

class Source implements LocalVisionSource {
  @override
  bool isPaired = true, authorized = true;
  int calls = 0;
  late Future<Map<String, dynamic>> Function() response;
  @override
  Future<Map<String, dynamic>> localVision(
      String op, Map<String, dynamic> body) {
    calls++;
    expect(op, 'frame');
    expect(body, {'task_id': task});
    return response();
  }

  @override
  Future<Uint8List> localModelBytes(ButtonModelManifest _) =>
      throw UnimplementedError();
}

Map<String, dynamic> frame() {
  final bytes = img.encodeJpg(img.Image(width: 2, height: 3));
  return {
    'task_id': task,
    'frame_id': sha256.convert(bytes).toString(),
    'barrier': 'b' * 32,
    'sequence': 1,
    'width': 2,
    'height': 3,
    'jpegBase64': base64Encode(bytes)
  };
}

Widget host(Source source, {String id = task, bool active = true}) =>
    MaterialApp(
        home: Scaffold(
            body: TaskFramePreview(
                source: source,
                taskId: id,
                sourceLabel: '当前已绑定被控手机',
                active: active)));

void main() {
  testWidgets('fetch is explicit, authentic JPEG is labelled and can be closed',
      (tester) async {
    final source = Source()..response = () async => frame();
    await tester.pumpWidget(host(source));
    expect(source.calls, 0);
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsOneWidget);
    expect(find.text('当前观察画面，不是最终核验证据'), findsOneWidget);
    expect(find.textContaining('当前已绑定被控手机'), findsWidgets);
    await tester.tap(find.byTooltip('关闭当前画面'));
    await tester.pump();
    expect(find.byType(Image), findsNothing);
  });
  testWidgets('wrong task and corrupt data stay errors and permit retry',
      (tester) async {
    final source = Source()
      ..response = () async => {...frame(), 'task_id': 'other'};
    await tester.pumpWidget(host(source));
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('未能显示'), findsOneWidget);
    source.response = () async => {...frame(), 'width': 5000};
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    source.response = () async => {...frame(), 'jpegBase64': '%invalid'};
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    source.response = () async => {...frame(), 'width': 3};
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    source.response = () async => {...frame(), 'frame_id': '0' * 64};
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    source.response = () async => frame();
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsOneWidget);
  });
  testWidgets('task replacement and terminal state discard old responses',
      (tester) async {
    final pending = Completer<Map<String, dynamic>>();
    final source = Source()..response = () => pending.future;
    await tester.pumpWidget(host(source));
    await tester.tap(find.text('查看当前画面'));
    await tester.pump();
    await tester.pumpWidget(host(source, id: 'c' * 32));
    pending.complete(frame());
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    source.response = () async => frame();
    await tester.pumpWidget(host(source));
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsOneWidget);
    await tester.pumpWidget(host(source, active: false));
    expect(find.text('查看当前画面'), findsNothing);
    expect(find.byType(Image), findsNothing);
  });
  testWidgets('waiting frame and disposed request never expose stale image',
      (tester) async {
    final source = Source()
      ..response = () async => {'state': 'waiting', 'task_id': task};
    await tester.pumpWidget(host(source));
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsNothing);
    expect(find.textContaining('等待被控手机'), findsOneWidget);
    source.response = () async => throw StateError('HTTP409');
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpAndSettle();
    expect(find.textContaining('未能显示'), findsOneWidget);
    final pending = Completer<Map<String, dynamic>>();
    source.response = () => pending.future;
    await tester.tap(find.text('查看当前画面'));
    await tester.pumpWidget(const SizedBox());
    pending.complete(frame());
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
