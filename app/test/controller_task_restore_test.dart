import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/control_screen.dart';
import 'package:pcflash/controller_local_vision.dart';
import 'package:pcflash/controller_pairing_store.dart';

Map<String, dynamic> task(String state, {String reply = '恢复的任务进度'}) => {
      'task_id': 'a' * 32,
      'state': state,
      'reply': reply,
      'terminal': ['done', 'error', 'stopped'].contains(state),
      'verified': state == 'done',
    };

class RestoredClient extends ControlClient {
  RestoredClient(this.latest) {
    deviceId = 'target-a';
  }
  final Future<Map<String, dynamic>> latest;
  String binding = 'b' * 43;
  bool live = true;
  final operations = <String>[];
  final statusIds = <String?>[];
  @override
  bool get isPaired => true;
  @override
  bool get authorized => live;
  @override
  bool get canReadStatus => live;
  @override
  ControllerPairing? get restorablePairing => ControllerPairing(
      't' * 43, deviceId!, DateTime.now().add(const Duration(minutes: 5)),
      bindingToken: binding);
  @override
  Future<void> refresh() async {}
  @override
  Future<Map<String, dynamic>> command(String operation,
      {String? text,
      String? taskId,
      String? skillId,
      Map<String, String>? parameters}) async {
    operations.add(operation);
    if (operation == 'status') {
      statusIds.add(taskId);
      if (taskId == null) return latest;
      return task('running', reply: '仍在查询原任务');
    }
    if (operation == 'stop') {
      return {...task('stopped', reply: '停止回执已确认'), 'stopConfirmed': true};
    }
    throw StateError('restoration must never dispatch $operation');
  }
}

class NoNativeVision extends ControllerLocalVision {
  NoNativeVision(super.source);
  @override
  Future<void> prepare() async {}
  @override
  Future<void> observe(String taskId, {bool Function()? isCurrent}) async {}
  @override
  void suspend() {}
  @override
  Future<void> close() async {}
}

Future<void> mount(WidgetTester tester, RestoredClient client) async {
  await tester.pumpWidget(MaterialApp(
      home: ControlScreen(client: client, visionFactory: NoNativeVision.new)));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 20));
}

void main() {
  testWidgets(
      'restored connection reads current owner task once without confirming or replaying',
      (tester) async {
    final client = RestoredClient(Future.value(task('running')));
    await mount(tester, client);
    expect(client.operations, ['status']);
    expect(client.statusIds, [null]);
    expect(find.text('恢复的任务进度'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();
    expect(client.statusIds, [null, 'a' * 32]);
    expect(client.operations.every((op) => op == 'status'), isTrue);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('idle restoration leaves task card empty', (tester) async {
    final client = RestoredClient(
        Future.value({'state': 'idle', 'terminal': true, 'reply': '不应成为任务卡'}));
    await mount(tester, client);
    expect(client.operations, ['status']);
    expect(find.text('不应成为任务卡'), findsNothing);
    await tester.pump(const Duration(seconds: 4));
    expect(client.statusIds, [null]);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('pending restoration still requires explicit confirmation',
      (tester) async {
    final client = RestoredClient(Future.value(task('pending')));
    await mount(tester, client);
    expect(find.text('等待你的确认'), findsOneWidget);
    expect(client.operations, ['status']);
    await tester.pump(const Duration(seconds: 4));
    expect(client.operations, ['status']);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('STOP wins over late restored task response', (tester) async {
    final response = Completer<Map<String, dynamic>>();
    final client = RestoredClient(response.future);
    await mount(tester, client);
    expect(client.operations, ['status']);
    await tester.tap(find.text('停止手机操作'));
    await tester.pump();
    await tester.pump();
    response.complete(task('running', reply: '不可恢复的旧任务'));
    await tester.pump();
    await tester.pump();
    expect(find.text('不可恢复的旧任务'), findsNothing);
    expect(find.text('停止回执已确认'), findsOneWidget);
    expect(client.operations, ['status', 'stop']);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('binding switch invalidates late owner response', (tester) async {
    final response = Completer<Map<String, dynamic>>();
    final client = RestoredClient(response.future);
    await mount(tester, client);
    expect(client.operations, ['status']);
    client.deviceId = 'target-b';
    client.binding = 'c' * 43;
    response.complete(task('running', reply: '另一绑定的旧任务'));
    await tester.pump();
    await tester.pump();
    expect(find.text('另一绑定的旧任务'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('revoked binding cannot restore a late task', (tester) async {
    final response = Completer<Map<String, dynamic>>();
    final client = RestoredClient(response.future);
    await mount(tester, client);
    expect(client.operations, ['status']);
    client.live = false;
    response.complete(task('running'));
    await tester.pump();
    await tester.pump();
    expect(find.text('恢复的任务进度'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('disposed screen ignores a late restored response',
      (tester) async {
    final response = Completer<Map<String, dynamic>>();
    final client = RestoredClient(response.future);
    await mount(tester, client);
    expect(client.operations, ['status']);
    await tester.pumpWidget(const SizedBox());
    response.complete(task('running'));
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
