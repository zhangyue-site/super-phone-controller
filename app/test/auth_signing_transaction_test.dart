import 'dart:async';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/app_ota_client.dart';
import 'amoled_firmware_image_test.dart' show amoledImage;
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_blue_plus_platform_interface/flutter_blue_plus_platform_interface.dart'
    as bm;
import 'package:pcflash/ble_ota_service.dart';
import 'ble_push_integration_test.dart' show BoardPlatform;

final class SigningPlatform extends BoardPlatform {
  List<int> proof = List.filled(32, 0);
  var firstWrite = Completer<void>();
  var releaseFirst = Completer<void>();
  int authWrites = 0;
  Completer<void>? readStarted, releaseRead;
  final transactions = <String>[];
  List<int> sign(List<int> nonce) =>
      Hmac(sha256, [7, 8, 9]).convert(nonce).bytes;
  @override
  Future<bool> writeCharacteristic(bm.BmWriteCharacteristicRequest r) async {
    if (r.characteristicUuid != uuid(5)) return super.writeCharacteristic(r);
    proof = sign(r.value);
    transactions.add('write${r.value.first}');
    authWrites++;
    if (authWrites == 1) {
      firstWrite.complete();
      await releaseFirst.future;
    }
    writes.add(value(r.characteristicUuid, r.value));
    return true;
  }

  @override
  Future<bool> readCharacteristic(bm.BmReadCharacteristicRequest r) async {
    if (r.characteristicUuid != uuid(5)) return super.readCharacteristic(r);
    transactions.add('read${proof.first}');
    final gate = releaseRead;
    if (gate != null) {
      readStarted?.complete();
      await gate.future;
      releaseRead = null;
    }
    reads.add(value(r.characteristicUuid, proof));
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('AUTH nonce write and proof read are a single serialized transaction',
      () async {
    final platform = SigningPlatform();
    bm.FlutterBluePlusPlatform.instance = platform;
    final service = BleOtaService();
    await service.connect(BluetoothDevice.fromId(platform.id.str));
    final a = List.filled(32, 1), b = List.filled(32, 2);
    final signingA = service.signDownloadChallenge(a);
    await platform.firstWrite.future;
    final signingB = service.signDownloadChallenge(b);
    // B is queued while A's native write receipt is still pending.
    await Future<void>.delayed(Duration.zero);
    platform.releaseFirst.complete();
    final result = await Future.wait([signingA, signingB]);
    expect(result[0], platform.sign(a),
        reason: platform.transactions.toString());
    expect(result[1], platform.sign(b),
        reason: platform.transactions.toString());
    final secondService = BleOtaService();
    await secondService.connect(BluetoothDevice.fromId(platform.id.str));
    platform.authWrites = 0;
    platform.firstWrite = Completer<void>();
    platform.releaseFirst = Completer<void>();
    platform.transactions.clear();
    final multiA = service.signDownloadChallenge(a);
    await platform.firstWrite.future;
    final multiB = secondService.signDownloadChallenge(b);
    await Future<void>.delayed(Duration.zero);
    platform.releaseFirst.complete();
    final multiResult = await Future.wait([multiA, multiB]);
    expect(multiResult[0], platform.sign(a),
        reason: platform.transactions.toString());
    expect(multiResult[1], platform.sign(b),
        reason: platform.transactions.toString());
    platform.transactions.clear();
    platform.readStarted = Completer<void>();
    platform.releaseRead = Completer<void>();
    final late = service.signDownloadChallenge(a);
    final lateRejected = expectLater(late, throwsStateError);
    await platform.readStarted!.future;
    final queued = service.signDownloadChallenge(b);
    final queuedRejected = expectLater(queued, throwsStateError);
    final disconnecting = service.disconnect();
    await Future<void>.delayed(Duration.zero);
    platform.releaseRead!.complete();
    await Future.wait([lateRejected, queuedRejected, disconnecting]);
    expect(
        platform.transactions.where((e) => e.startsWith('write')), ['write1']);
    // A failed old-epoch transaction must release its queue, with no retry.
    await service.connect(BluetoothDevice.fromId(platform.id.str));
    expect(await service.signDownloadChallenge(b), platform.sign(b));
    await expectLater(secondService.signDownloadChallenge(a), throwsStateError);
    platform.transactions.clear();
    platform.readStarted = Completer<void>();
    platform.releaseRead = Completer<void>();
    final timedOut = service.signDownloadChallenge(a);
    final timeoutChecked =
        expectLater(timedOut, throwsA(isA<TimeoutException>()));
    await platform.readStarted!.future;
    final afterTimeout = service.signDownloadChallenge(b);
    await timeoutChecked;
    platform.releaseRead!.complete();
    expect(await afterTimeout, platform.sign(b));
    expect(platform.transactions.where((e) => e.startsWith('write')),
        ['write1', 'write2']);
    await secondService.disconnect();
    await service.disconnect();
    var cloudCalls = 0;
    final ota = BleOtaService(
        upgradeClientFactory: () =>
            AppOtaClient(Uri.parse('https://example.test'),
                client: MockClient((_) async {
              cloudCalls++;
              return http.Response('{}', 403);
            })));
    await ota.connect(BluetoothDevice.fromId(platform.id.str));
    final bytes = amoledImage();
    ota.retainOfficialUpgrade(
        DownloadedFirmware(bytes, '0.3.0-amoled', ticket: 'ticket'));
    ota.confirmFirmware(
        device: 'test-board',
        boot: 'b' * 32,
        currentVersion: platform.version,
        sha: sha256.convert(bytes).toString());
    platform.readStarted = Completer<void>();
    platform.releaseRead = Completer<void>();
    platform.events.clear();
    final pushing = ota.push(bytes, chunkSize: 511).toList();
    await platform.readStarted!.future;
    final cancelling = ota.cancelPush();
    await Future<void>.delayed(Duration.zero);
    platform.releaseRead!.complete();
    final stopped = await pushing;
    await cancelling;
    expect(stopped.last.success, isFalse);
    expect(cloudCalls, 0);
    expect(platform.events, isNot(contains('image-authorization')));
    expect(platform.events, isNot(contains('begin')));
    await ota.disconnect();
  });
}
