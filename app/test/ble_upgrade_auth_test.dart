import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/app_ota_client.dart';

void main() {
  test('BLE OTA uses firmware ticket and board proof, not control ticket',
      () async {
    final client = AppOtaClient(Uri.parse('https://example.com'),
        client: MockClient((request) async {
      expect(request.url.path, '/app-ota/ble-authorize');
      expect(request.headers['Authorization'], 'Bearer firmware-ticket');
      final body = jsonDecode(request.body) as Map;
      expect(body['challenge'], '01' * 32);
      expect(body['proof'], '02' * 32);
      expect(body['boot'], 'a' * 32);
      return http.Response(
          jsonEncode({
            'scope': 'ble-ota',
            'expiresIn': 60,
            'authorization': '03' * 32
          }),
          200);
    }));
    final result = await client.authorizeBle('firmware-ticket', 'board',
        'a' * 32, List.filled(32, 1), (nonce) async => List.filled(32, 2));
    expect(result, List.filled(32, 3));
  });
  test('BLE OTA rejects a phone command grant', () async {
    final client = AppOtaClient(Uri.parse('https://example.com'),
        client: MockClient((_) async => http.Response(
            jsonEncode({
              'scope': 'phone-commands',
              'expiresIn': 60,
              'authorization': '03' * 32
            }),
            200)));
    await expectLater(
        client.authorizeBle('firmware-ticket', 'board', 'a' * 32,
            List.filled(32, 1), (_) async => List.filled(32, 2)),
        throwsFormatException);
  });
  test(
      'AMOLED image grant is 100 bytes and cannot fall back to legacy authorization',
      () async {
    var legacy = false;
    final client = AppOtaClient(Uri.parse('https://example.test'),
        client: MockClient((_) async => http.Response(
            jsonEncode({
              'scope': 'ble-ota',
              'expiresIn': 60,
              'protocol': legacy ? null : 'hmac-sha256-image-v2',
              'authorization': legacy ? '03' * 32 : '03' * 100,
            }),
            200)));
    final result = await client.authorizeBle('ticket', 'board', 'a' * 32,
        List.filled(32, 1), (_) async => List.filled(32, 2),
        protocol: 'hmac-sha256-image-v2');
    expect(result.length, 100);
    legacy = true;
    await expectLater(
        client.authorizeBle('ticket', 'board', 'a' * 32, List.filled(32, 1),
            (_) async => List.filled(32, 2),
            protocol: 'hmac-sha256-image-v2'),
        throwsFormatException);
  });
}
