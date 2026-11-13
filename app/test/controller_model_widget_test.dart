import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/control_screen.dart';
import 'package:pcflash/controller_local_vision.dart';
import 'package:pcflash/button_detector.dart';
import 'package:pcflash/controller_model_status.dart';

class FakeSource implements LocalVisionSource {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeVision extends ControllerLocalVision {
  FakeVision() : super(FakeSource());
  int prepares = 0, observations = 0, suspensions = 0;
  String? failure;
  double? milliseconds;
  int? detections;
  @override
  String? get error => failure;
  @override
  double? get inferenceMs => milliseconds;
  @override
  int? get boxCount => detections;
  bool Function()? current;
  @override
  String get status => '本地模型已就绪';
  @override
  bool get ready => true;
  @override
  Future<void> prepare() async {
    prepares++;
    notifyListeners();
  }

  @override
  Future<void> observe(String taskId, {bool Function()? isCurrent}) async {
    observations++;
    current = isCurrent;
  }

  @override
  void suspend() {
    suspensions++;
  }

  @override
  Future<void> close() async {}
}

class FakeClient extends ControlClient {
  FakeClient(this.paired);
  final bool paired;
  String statusState = 'running';
  @override
  bool get isPaired => paired;
  @override
  bool get authorized => true;
  @override
  bool get canReadStatus => true;
  @override
  Future<void> refresh() async {}
  @override
  Future<Map<String, dynamic>> command(String operation,
          {String? text,
          String? taskId,
          String? skillId,
          Map<String, String>? parameters}) async =>
      {
        'task_id': 'a' * 32,
        'state': operation == 'stop'
            ? 'stopped'
            : operation == 'prepare'
                ? 'pending'
                : operation == 'status'
                    ? statusState
                    : 'running',
        'reply': '测试任务',
        'terminal': operation == 'stop'
      };
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  testWidgets('inline error can retry and unknown measurements stay unknown',
      (tester) async {
    final vision = FakeVision()..failure = '下载校验失败';
    var retries = 0;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ControllerModelStatus(
                vision: vision, onRetry: () => retries++))));
    expect(find.text('下载校验失败'), findsOneWidget);
    expect(find.textContaining('实际推理'), findsNothing);
    await tester.tap(find.text('重试准备本机模型'));
    expect(retries, 1);
    vision.milliseconds = 12.4;
    vision.detections = 3;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ControllerModelStatus(
                key: const ValueKey('updated'),
                vision: vision,
                onRetry: () => retries++))));
    expect(find.text('实际推理 12.4 毫秒 · 按钮 3 个'), findsOneWidget);
  });
  testWidgets('paired controller automatically prepares; target never starts',
      (tester) async {
    final vision = FakeVision();
    var factories = 0;
    await tester.pumpWidget(MaterialApp(
        home: ControlScreen(
            client: FakeClient(true),
            visionFactory: (_) {
              factories++;
              return vision;
            })));
    await tester.pump();
    expect(factories, 1);
    expect(vision.prepares, 1);
    expect(find.text('控制手机本机模型'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(MaterialApp(
        home: ControlScreen(
            client: FakeClient(false),
            visionFactory: (_) {
              factories++;
              return vision;
            })));
    await tester.pump();
    expect(factories, 1);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('terminal task suspends once and remains closed', (tester) async {
    final vision = FakeVision();
    final client = FakeClient(true);
    await tester.pumpWidget(MaterialApp(
        home: ControlScreen(client: client, visionFactory: (_) => vision)));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('发给龙虾，查看计划'), 150,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('发给龙虾，查看计划'));
    await tester.pump();
    await tester.scrollUntilVisible(find.text('确认执行'), 150,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('确认执行'));
    await tester.pump();
    client.statusState = 'done';
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 350));
    expect(vision.suspensions, greaterThan(0));
    final suspensions = vision.suspensions, prepares = vision.prepares;
    await tester.pump(const Duration(milliseconds: 900));
    expect(vision.suspensions, suspensions);
    expect(vision.prepares, prepares);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('STOP and background invalidate a pending observation',
      (tester) async {
    final vision = FakeVision();
    await tester.pumpWidget(MaterialApp(
        home: ControlScreen(
            client: FakeClient(true), visionFactory: (_) => vision)));
    await tester.pump();
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('发给龙虾，查看计划'), 150,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('发给龙虾，查看计划'));
    await tester.pump();
    await tester.scrollUntilVisible(find.text('确认执行'), 150,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('确认执行'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(vision.observations, greaterThan(0));
    final oldCurrent = vision.current!;
    expect(oldCurrent(), isTrue);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    expect(oldCurrent(), isFalse);
    expect(vision.suspensions, greaterThan(0));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump(const Duration(milliseconds: 350));
    expect(oldCurrent(), isFalse);
    final beforeRoute = vision.current!;
    final navigator =
        tester.state<NavigatorState>(find.byType(Navigator).first);
    unawaited(navigator.push(MaterialPageRoute<void>(
        builder: (_) => const Scaffold(body: Text('另一个页面')))));
    await tester.pumpAndSettle();
    expect(beforeRoute(), isFalse);
    navigator.pop();
    await tester.pumpAndSettle();
    await tester.pump(const Duration(milliseconds: 350));
    expect(beforeRoute(), isFalse);
    final beforeStop = vision.current!;
    await tester.tap(find.text('停止手机操作'));
    await tester.pump();
    expect(beforeStop(), isFalse);
    final stoppedPrepares = vision.prepares;
    await tester.pump(const Duration(milliseconds: 900));
    expect(vision.prepares, stoppedPrepares);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump(const Duration(milliseconds: 700));
    expect(vision.prepares, stoppedPrepares);
    await tester.scrollUntilVisible(find.text('发给龙虾，查看计划'), -150,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('发给龙虾，查看计划'));
    await tester.pump();
    expect(vision.prepares, greaterThan(stoppedPrepares));
    await tester.pumpWidget(const SizedBox());
  });
}
