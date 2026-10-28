import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/controller_pair_screen.dart';
import 'package:pcflash/theme.dart';

const code = 'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG';
http.Response grant() => http.Response(
    jsonEncode({
      'ticket': code,
      'device': 'test-board',
      'scope': 'phone-commands',
      'expiresIn': 300
    }),
    200);

class TrackedHttp extends MockClient {
  TrackedHttp(super.fn);
  bool closed = false;
  @override
  void close() {
    closed = true;
    super.close();
  }
}

Finder get button => find.widgetWithText(FilledButton, '连接被控手机');
void main() {
  testWidgets('validates locally and redeems trimmed code once then navigates',
      (tester) async {
    var requests = 0;
    final transport = TrackedHttp((request) async {
      requests++;
      expect(request.url.path, endsWith('/pair-redeem'));
      expect(jsonDecode(request.body), {'code': code});
      return grant();
    });
    final client = ControlClient(client: transport);
    addTearDown(client.close);
    await tester.pumpWidget(MaterialApp(
        home: ControllerPairScreen(
            clientFactory: () => client,
            connectedBuilder: (client) {
              expect(client.isPaired, isTrue);
              return const Scaffold(body: Text('连接成功'));
            })));
    await tester.tap(button);
    await tester.pump();
    expect(find.text('请粘贴完整的43位连接码'), findsOneWidget);
    expect(requests, 0);
    await tester.enterText(find.byType(TextFormField), ' $code ');
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(requests, 1);
    expect(find.text('连接成功'), findsOneWidget);
    expect(transport.closed, isFalse);
  });
  testWidgets('cancel closes pending client and ignores late response',
      (tester) async {
    final pending = Completer<http.Response>();
    final transport = TrackedHttp((_) => pending.future);
    await tester.pumpWidget(MaterialApp(
        home: ControllerPairScreen(
            clientFactory: () => ControlClient(client: transport),
            connectedBuilder: (_) => const Text('不应出现'))));
    await tester.enterText(find.byType(TextFormField), code);
    await tester.tap(button);
    await tester.pump();
    expect(find.text('正在连接…'), findsOneWidget);
    await tester.tap(find.text('取消连接'));
    await tester.pump();
    expect(transport.closed, isTrue);
    pending.complete(grant());
    await tester.pumpAndSettle();
    expect(find.text('不应出现'), findsNothing);
    expect(find.textContaining('连接失败'), findsNothing);
  });
  testWidgets('leaving closes pending request and no navigation occurs',
      (tester) async {
    final pending = Completer<http.Response>();
    final transport = TrackedHttp((_) => pending.future);
    await tester.pumpWidget(MaterialApp(
        home: ControllerPairScreen(
            clientFactory: () => ControlClient(client: transport))));
    await tester.enterText(find.byType(TextFormField), code);
    await tester.tap(button);
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    expect(transport.closed, isTrue);
    pending.complete(grant());
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
  testWidgets('expired code reports retry without exposing server secrets',
      (tester) async {
    final transport =
        TrackedHttp((_) async => http.Response('{"reply":"expired"}', 403));
    await tester.pumpWidget(MaterialApp(
        home: ControllerPairScreen(
            clientFactory: () => ControlClient(client: transport))));
    await tester.enterText(find.byType(TextFormField), code);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(find.textContaining('重新生成连接码'), findsOneWidget);
    expect(transport.closed, isTrue);
    expect(tester.widget<FilledButton>(button).onPressed, isNotNull);
  });
  for (final dark in [false, true]) {
    testWidgets('manual clipboard access and narrow enlarged layout ($dark)',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var reads = 0;
      tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.getData') {
          reads++;
          return {'text': code};
        }
        return null;
      });
      addTearDown(() => tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null));
      await tester.pumpWidget(MaterialApp(
          theme: dark ? AppTheme.build() : AppTheme.light(),
          home: Builder(
              builder: (context) => MediaQuery(
                  data: MediaQuery.of(context)
                      .copyWith(textScaler: const TextScaler.linear(1.6)),
                  child: const ControllerPairScreen()))));
      expect(reads, 0);
      await tester.drag(find.byType(ListView), const Offset(0, -350));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('从剪贴板粘贴'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('从剪贴板粘贴'));
      await tester.pump();
      expect(reads, 1);
      expect(
          tester
              .widget<TextFormField>(find.byType(TextFormField))
              .controller!
              .text,
          code);
      expect(tester.takeException(), isNull);
    });
  }
}
