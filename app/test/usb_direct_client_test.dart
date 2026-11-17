import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/diagnostics.dart';
import 'package:pcflash/usb_launch.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const usb = UsbAttachment('AABBCCDDEEFF', 'AABBCCDDEEFF:1', null, null);
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  Map<String, dynamic> identity() =>
      {'protocol': 1, 'device': 'test-board', 'usbSerial': usb.serial};
  Map<String, dynamic> grant() => {
        'ticket': 't' * 43,
        'scope': 'phone-commands',
        'expiresIn': 300,
        'device': 'test-board',
        'serial': usb.serial,
        'protocol': 'pcusb-v1'
      };
  setUp(() {
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'snapshot') {
        return {'serial': usb.serial, 'session': usb.session};
      }
      if (call.method == 'info') return identity();
      if (call.method == 'sign') return {...identity(), 'proof': 'b' * 64};
      throw StateError('Unexpected USB call');
    });
  });
  tearDown(() => messenger.setMockMethodCallHandler(UsbLaunch.channel, null));
  test('USB authorize pairs and renews without BLE or relay attach', () async {
    final paths = <String>[];
    final client = ControlClient(client: MockClient((r) async {
      final path = r.url.path.split('/').last;
      paths.add(path);
      if (path == 'usb-challenge') {
        return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (path == 'usb-authorize') {
        return http.Response(jsonEncode(grant()), 200);
      }
      if (path == 'usb-renew') {
        expect(r.headers['Authorization'], 'Bearer ${'t' * 43}');
        return http.Response(jsonEncode(grant()), 200);
      }
      if (path == 'pair-issue') {
        return http.Response('{"code":"0246","persistent":true}', 200);
      }
      if (path == 'usb-revoke') return http.Response('{}', 200);
      throw StateError('Unexpected request: $path');
    }));
    await client.authorizeUsb(usb);
    expect(client.authorized, isTrue);
    expect(client.usesUsbDirect, isTrue);
    expect(client.ownsGateway, isFalse);
    expect((await client.pairingCode())['code'], '0246');
    await client.refreshUsbAuthorization();
    expect(paths, [
      'usb-challenge',
      'usb-authorize',
      'pair-issue',
      'usb-challenge',
      'usb-renew'
    ]);
    await client.shutdown();
    expect(paths.last, 'usb-revoke');
    expect(client.authorized, isFalse);
  });
  test('mismatched signature identity cannot authorize', () async {
    final paths = <String>[];
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'snapshot') {
        return {'serial': usb.serial, 'session': usb.session};
      }
      if (call.method == 'info') return identity();
      return {...identity(), 'device': 'other', 'proof': 'b' * 64};
    });
    final client = ControlClient(client: MockClient((r) async {
      paths.add(r.url.path);
      return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
    }));
    await expectLater(client.authorizeUsb(usb), throwsStateError);
    expect(client.authorized, isFalse);
    expect(paths.length, 1);
    await client.shutdown();
  });
  test('USB session changes before signing prevent authorization', () async {
    int snapshots = 0;
    final paths = <String>[];
    messenger.setMockMethodCallHandler(UsbLaunch.channel, (call) async {
      if (call.method == 'snapshot') {
        return {
          'serial': usb.serial,
          'session': snapshots++ < 2 ? usb.session : 'AABBCCDDEEFF:2'
        };
      }
      if (call.method == 'info') return identity();
      return {...identity(), 'proof': 'b' * 64};
    });
    final client = ControlClient(client: MockClient((r) async {
      paths.add(r.url.path);
      return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
    }));
    await expectLater(client.authorizeUsb(usb), throwsStateError);
    expect(client.authorized, isFalse);
    expect(paths.where((p) => p.endsWith('/usb-authorize')), isEmpty);
    await client.shutdown();
  });
  test('cancelled grant is revoked and never becomes authorized', () async {
    var current = true;
    final paths = <String>[];
    final client = ControlClient(client: MockClient((r) async {
      final path = r.url.path.split('/').last;
      paths.add(path);
      if (path == 'usb-challenge') {
        return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (path == 'usb-authorize') {
        current = false;
        return http.Response(jsonEncode(grant()), 200);
      }
      return http.Response('{}', 200);
    }));
    await expectLater(
        client.authorizeUsb(usb, isCurrent: () => current), throwsStateError);
    expect(client.authorized, isFalse);
    expect(paths.last, 'usb-revoke');
    await client.shutdown();
  });
  test('rejected USB renewal never reauthorizes or attaches a gateway',
      () async {
    final paths = <String>[];
    final client = ControlClient(client: MockClient((r) async {
      final path = r.url.path.split('/').last;
      paths.add(path);
      if (path == 'usb-challenge') {
        return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (path == 'usb-authorize') {
        return http.Response(jsonEncode(grant()), 200);
      }
      return http.Response('{}', 403);
    }));
    await client.authorizeUsb(usb);
    await expectLater(
        client.refreshUsbAuthorization(), throwsA(isA<ControlHttpFailure>()));
    expect(client.authorized, isFalse);
    expect(paths.where((p) => p == 'usb-authorize').length, 1);
    expect(paths, isNot(contains('attach')));
    await client.shutdown();
    expect(paths.last, 'usb-revoke');
  });
  test('shutdown waits for late USB grant cleanup before closing HTTP',
      () async {
    final arrived = Completer<void>(), response = Completer<http.Response>();
    final paths = <String>[];
    final client = ControlClient(client: MockClient((r) async {
      final path = r.url.path.split('/').last;
      paths.add(path);
      if (path == 'usb-challenge') {
        return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (path == 'usb-authorize') {
        arrived.complete();
        return response.future;
      }
      return http.Response('{}', 200);
    }));
    final grantFuture = client.authorizeUsb(usb);
    final failed = expectLater(grantFuture, throwsStateError);
    await arrived.future;
    var closed = false;
    final closing = client.shutdown().then((_) {
      closed = true;
    });
    await Future<void>.delayed(Duration.zero);
    expect(closed, isFalse);
    response.complete(http.Response(jsonEncode(grant()), 200));
    await failed;
    await closing;
    expect(paths.last, 'usb-revoke');
    expect(client.usbRevokeFailed, isFalse);
    expect(client.authorized, isFalse);
  });
  test('physical session loss immediately revokes; network failure does not',
      () async {
    for (final detached in [true, false]) {
      var changed = false;
      final paths = <String>[];
      messenger.setMockMethodCallHandler(UsbLaunch.channel, (c) async {
        if (c.method == 'snapshot') {
          return {
            'serial': usb.serial,
            'session': changed && detached ? 'AABBCCDDEEFF:2' : usb.session
          };
        }
        if (c.method == 'info') return identity();
        return {...identity(), 'proof': 'b' * 64};
      });
      final client = ControlClient(client: MockClient((r) async {
        final path = r.url.path.split('/').last;
        paths.add(path);
        if (path == 'usb-challenge') {
          if (changed && !detached) throw TimeoutException('network');
          return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
        }
        if (path == 'usb-authorize') {
          return http.Response(jsonEncode(grant()), 200);
        }
        return http.Response('{}', 200);
      }));
      await client.authorizeUsb(usb);
      changed = true;
      await expectLater(client.refreshUsbAuthorization(), throwsA(anything));
      expect(client.authorized, !detached);
      expect(paths.contains('usb-revoke'), detached);
      await client.shutdown();
    }
  });
}
