import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/button_detector.dart';

void main() {
  test(
      'only paired controller requests use local vision endpoints with bearer and no redirect',
      () async {
    final paths = <String>[];
    final c = ControlClient(client: MockClient((r) async {
      paths.add(r.url.path);
      if (r.url.path.endsWith('pair-redeem')) {
        return http.Response(
            jsonEncode({
              'ticket': 't' * 43,
              'device': 'test-board',
              'scope': 'phone-commands',
              'expiresIn': 300
            }),
            200);
      }
      expect(r.url.path, '/app-local-vision/manifest');
      expect(r.headers['Authorization'], 'Bearer ${'t' * 43}');
      expect(r.followRedirects, isFalse);
      return http.Response('{"available":false}', 200);
    }));
    await expectLater(c.localVision('manifest', {}), throwsStateError);
    expect(paths, isEmpty);
    await c.pair('c' * 43);
    expect(await c.localVision('manifest', {}), {'available': false});
    await expectLater(c.localVision('../model', {}), throwsArgumentError);
    c.close();
  });
  test('bounded model response rejects redirected and oversized content',
      () async {
    var redirect = true;
    final c = ControlClient(client: MockClient((r) async {
      if (r.url.path.endsWith('pair-redeem')) {
        return http.Response(
            jsonEncode({
              'ticket': 't' * 43,
              'device': 'test-board',
              'scope': 'phone-commands',
              'expiresIn': 300
            }),
            200);
      }
      return redirect
          ? http.Response('', 307,
              headers: {'location': 'https://other.test/leak'})
          : http.Response.bytes([1, 2, 3, 4, 5, 6], 200);
    }));
    await c.pair('c' * 43);
    final m = ButtonModelManifest('test', 'a' * 64, 5);
    await expectLater(c.localModelBytes(m), throwsFormatException);
    redirect = false;
    await expectLater(c.localModelBytes(m), throwsFormatException);
    c.close();
  });
  test('task observation conflict keeps valid controller pairing', () async {
    final c = ControlClient(client: MockClient((r) async {
      if (r.url.path.endsWith('pair-redeem')) {
        return http.Response(
            jsonEncode({
              'ticket': 't' * 43,
              'device': 'test-board',
              'scope': 'phone-commands',
              'expiresIn': 300
            }),
            200);
      }
      return http.Response('{"error":"local observation inactive"}', 409);
    }));
    await c.pair('c' * 43);
    await expectLater(
        c.localVision('frame', {'task_id': 'a' * 32}), throwsFormatException);
    expect(c.authorized, isTrue);
    c.close();
  });
}
