import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:crypto/crypto.dart';
import 'package:pcflash/app_ota_client.dart';
import 'package:pcflash/board_info.dart';
import 'package:pcflash/firmware_image.dart';

Map<String, dynamic> info(
        {String boot = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        String version = 'ci99',
        String elf =
            'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        int state = 2,
        String device = 'one'}) =>
    {
      'protocol': 1,
      'device': device,
      'version': version,
      'elfSha256': elf,
      'boot': boot,
      'imageState': state
    };
void main() {
  test(
      'only advertised policy permits reinstall and slot confirmation requires a different slot',
      () {
    const target = FirmwareImage('0.4.2-amoled', 'sha', 'elf',
        project: 'phone_controller_amoled');
    const old = BoardInfo('one', '0.4.2-amoled', 'elf', 'boot', 2);
    const modern = BoardInfo('one', '0.4.2-amoled', 'elf', 'boot', 2,
        otaVersionPolicy: 'manual-confirmed-any', runningSlot: 'ota_0');
    expect(() => old.assertFirmwareAllowed(target), throwsStateError);
    expect(() => modern.assertFirmwareAllowed(target), returnsNormally);
    const sameSlot = BoardInfo('one', '0.4.2-amoled', 'elf', 'newboot', 2,
        runningSlot: 'ota_0');
    const newSlot = BoardInfo('one', '0.4.2-amoled', 'elf', 'newboot', 2,
        runningSlot: 'ota_1');
    expect(sameSlot.confirms(modern, target.version, 'elf'), isFalse);
    expect(newSlot.confirms(modern, target.version, 'elf'), isTrue);
  });

  test(
      'authorization errors show only stage and HTTP guidance, never server secrets',
      () async {
    for (final status in [403, 429, 410]) {
      final client = AppOtaClient(Uri.parse('https://example.test'),
          client: MockClient(
              (_) async => http.Response('secret nonce proof ticket', status)));
      try {
        await client.authorizeBle('t' * 43, 'one', 'boot', List.filled(32, 1),
            (_) async => List.filled(32, 2));
        fail('must reject');
      } on AppOtaException catch (error) {
        expect(error.stage, '蓝牙刷写授权');
        expect(error.statusCode, status);
        expect(error.toString(), contains('HTTP $status'));
        expect(error.toString(), isNot(contains('secret')));
        expect(error.toString(), isNot(contains('nonce')));
        if (status == 410) expect(error.toString(), contains('重新下载'));
        if (status == 429) expect(error.toString(), contains('频繁'));
      }
    }
  });

  test('boot confirmation requires new boot, correct identity and valid image',
      () {
    final before = BoardInfo.parse(utf8.encode(jsonEncode(info())));
    bool matches(Map<String, dynamic> data) =>
        BoardInfo.parse(utf8.encode(jsonEncode(data)))
            .confirms(before, 'ci99', 'b' * 64);
    expect(matches(info()), isFalse);
    expect(matches(info(boot: 'c' * 32)), isTrue);
    expect(matches(info(boot: 'c' * 32, state: 1)), isFalse);
    expect(matches(info(boot: 'c' * 32, version: 'old')), isFalse);
    expect(matches(info(boot: 'c' * 32, device: 'two')), isFalse);
    expect(matches(info(boot: 'c' * 32, elf: 'd' * 64)), isFalse);
    expect(() => BoardInfo.parse(utf8.encode(jsonEncode(info(boot: '')))),
        throwsFormatException);
  });
  test('download exchanges BLE proof and checks bounded image SHA and size',
      () async {
    final data = Uint8List.fromList(List.filled(4096, 1));
    final digest = sha256.convert(data).toString();
    var signed = false;
    final client = MockClient((request) async {
      expect(request.url.origin, 'https://example.test');
      switch (request.url.path) {
        case '/app-ota/challenge':
          return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
        case '/app-ota/authorize':
          expect(signed, isTrue);
          expect(jsonDecode(request.body)['proof'], 'b' * 64);
          return http.Response(
              jsonEncode({
                'version': 'ci99',
                'size': 4096,
                'sha256': digest,
                'ticket': 't' * 43
              }),
              200);
        case '/app-ota/image':
          expect(request.headers['Authorization'],
              'Bearer ttttttttttttttttttttttttttttttttttttttttttt');
          expect(request.url.query, isEmpty);
          return http.Response.bytes(data, 200);
      }
      return http.Response('', 404);
    });
    final result =
        await AppOtaClient(Uri.parse('https://example.test'), client: client)
            .download('one', (nonce) async {
      expect(nonce, List.filled(32, 0xaa));
      signed = true;
      return List.filled(32, 0xbb);
    });
    expect(result.bytes, data);
    expect(result.version, 'ci99');
  });
  test('denied authorization and corrupted payload never reach BLE transfer',
      () async {
    final bad = MockClient((r) async => http.Response('{}', 403));
    await expectLater(
        AppOtaClient(Uri.parse('https://example.test'), client: bad)
            .download('one', (_) async => []),
        throwsA(isA<Exception>()));
    final badHash = MockClient((r) async {
      if (r.url.path.endsWith('challenge')) {
        return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (r.url.path.endsWith('authorize')) {
        return http.Response(
            jsonEncode({
              'version': 'ci99',
              'size': 4096,
              'sha256': 'c' * 64,
              'ticket': 't' * 43
            }),
            200);
      }
      return http.Response.bytes(List.filled(4096, 1), 200);
    });
    await expectLater(
        AppOtaClient(Uri.parse('https://example.test'), client: badHash)
            .download('one', (_) async => List.filled(32, 0xbb)),
        throwsFormatException);
  });
}
