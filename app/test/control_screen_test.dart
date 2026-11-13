import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/control_screen.dart';
import 'control_client_test.dart' show FakeBoard;

http.Response reply(String body, int status) => http.Response(body, status,
    headers: {'content-type': 'application/json; charset=utf-8'});

void main() {
  testWidgets('stop acknowledgement is not a stopped result', (tester) async {
    final client = ControlClient(client: MockClient((request) async {
      if (request.url.path.endsWith('/challenge')) {
        return reply(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (request.url.path.endsWith('/authorize')) {
        return reply(
            jsonEncode({
              'ticket': 't' * 43,
              'scope': 'phone-commands',
              'expiresIn': 300
            }),
            200);
      }
      return reply(
          jsonEncode({
            'task_id': 'c' * 32,
            'state': 'stopping',
            'reply': '请求已接收',
            'terminal': false
          }),
          200);
    }));
    await tester.pumpWidget(
        MaterialApp(home: ControlScreen(service: FakeBoard(), client: client)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('停止手机操作'));
    await tester.pumpAndSettle();
    expect(find.text('已停止'), findsNothing);
    expect(find.text('停止未确认 · 再次请求'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
      'preview never confirms automatically; STOP wins over late confirm',
      (tester) async {
    final operations = <String>[];
    final confirm = Completer<http.Response>();
    final client = ControlClient(client: MockClient((request) async {
      final body = jsonDecode(request.body) as Map;
      if (request.url.path.endsWith('/challenge')) {
        return reply(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (request.url.path.endsWith('/authorize')) {
        return reply(
            jsonEncode({
              'ticket': 't' * 43,
              'scope': 'phone-commands',
              'expiresIn': 300
            }),
            200);
      }
      final op = body['operation'] as String;
      operations.add(op);
      if (op == 'prepare') expect(body['text'], '打开微信找到测试联系人');
      if (op == 'confirm') return confirm.future;
      return reply(
          jsonEncode({
            'task_id': 'c' * 32,
            'state': op == 'stop' ? 'stopped' : 'pending',
            if (op == 'stop') 'stopConfirmed': true,
            'reply': op == 'stop' ? '本次手机操作已停止' : '计划：从桌面搜索联系人',
            'terminal': op == 'stop'
          }),
          200);
    }));
    await tester.pumpWidget(
        MaterialApp(home: ControlScreen(service: FakeBoard(), client: client)));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '打开微信找到测试联系人');
    await tester.scrollUntilVisible(find.text('发给龙虾，查看计划'), 120,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('发给龙虾，查看计划'));
    await tester.pumpAndSettle();
    expect(operations, ['prepare']);
    expect(tester.getTopLeft(find.text('等待你的确认')).dy, lessThan(220));
    await tester.tap(find.byTooltip('设备与设置'));
    await tester.pumpAndSettle();
    expect(find.text('停止手机操作'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '打开微信找到测试联系人');
    expect(operations, ['prepare']);
    tester.testTextInput.hide();
    await tester.pump();
    await tester.scrollUntilVisible(find.text('确认执行'), 160,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('确认执行'), findsOneWidget);
    await tester.ensureVisible(find.text('确认执行'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('确认执行'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('确认执行'));
    await tester.pump();
    await tester.tap(find.text('停止手机操作'));
    await tester.pumpAndSettle();
    expect(operations, ['prepare', 'confirm', 'stop']);
    expect(find.text('已停止'), findsOneWidget);
    confirm.complete(
        reply(jsonEncode({'state': 'queued', 'reply': '晚到的确认'}), 200));
    await tester.pumpAndSettle();
    expect(find.text('晚到的确认'), findsNothing);
    expect(find.text('已停止'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
