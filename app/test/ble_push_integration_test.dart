import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_blue_plus_platform_interface/flutter_blue_plus_platform_interface.dart'
    as bm;
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/ble_ota_service.dart';
import 'package:pcflash/app_ota_client.dart';
import 'amoled_firmware_image_test.dart' show amoledImage;

final class BoardPlatform extends bm.FlutterBluePlusPlatform {
  final id = const bm.DeviceIdentifier('00:11:22:33:44:55');
  final service = bm.Guid(BleOtaService.svcUuid);
  final states = StreamController<bm.BmConnectionStateResponse>.broadcast();
  final mtus = StreamController<bm.BmMtuChangedResponse>.broadcast();
  final discovered = StreamController<bm.BmDiscoverServicesResult>.broadcast();
  final reads = StreamController<bm.BmCharacteristicData>.broadcast();
  final writes = StreamController<bm.BmCharacteristicData>.broadcast();
  final descriptors = StreamController<bm.BmDescriptorData>.broadcast();
  @override
  Stream<bm.BmDescriptorData> get onDescriptorWritten => descriptors.stream;
  final List<String> events = [];
  bm.Guid uuid(int n) =>
      bm.Guid('6f6f7461-2d6f-7461-0000-${n.toString().padLeft(12, '0')}');
  @override
  Stream<bm.BmConnectionStateResponse> get onConnectionStateChanged =>
      states.stream;
  @override
  Stream<bm.BmMtuChangedResponse> get onMtuChanged => mtus.stream;
  @override
  Stream<bm.BmDiscoverServicesResult> get onDiscoveredServices =>
      discovered.stream;
  @override
  Stream<bm.BmCharacteristicData> get onCharacteristicReceived => reads.stream;
  @override
  Stream<bm.BmCharacteristicData> get onCharacteristicWritten => writes.stream;
  @override
  Future<bm.BmBluetoothAdapterState> getAdapterState(
          bm.BmBluetoothAdapterStateRequest r) async =>
      bm.BmBluetoothAdapterState(adapterState: bm.BmAdapterStateEnum.on);
  @override
  Future<bool> connect(bm.BmConnectRequest r) async {
    states.add(bm.BmConnectionStateResponse(
        remoteId: id,
        connectionState: bm.BmConnectionStateEnum.connected,
        disconnectReasonCode: null,
        disconnectReasonString: null));
    mtus.add(bm.BmMtuChangedResponse(remoteId: id, mtu: 517));
    return true;
  }

  @override
  Future<bool> disconnect(bm.BmDisconnectRequest r) async {
    states.add(bm.BmConnectionStateResponse(
        remoteId: id,
        connectionState: bm.BmConnectionStateEnum.disconnected,
        disconnectReasonCode: 0,
        disconnectReasonString: ''));
    return true;
  }

  @override
  Future<bool> discoverServices(bm.BmDiscoverServicesRequest r) async {
    discovered.add(bm.BmDiscoverServicesResult(
        remoteId: id,
        services: [
          bm.BmBluetoothService(
              remoteId: id,
              primaryServiceUuid: null,
              serviceUuid: service,
              characteristics: [
                for (final n in [2, 3, 4, 5, 8, 9])
                  bm.BmBluetoothCharacteristic(
                      remoteId: id,
                      primaryServiceUuid: null,
                      serviceUuid: service,
                      characteristicUuid: uuid(n),
                      instanceId: 0,
                      descriptors: [],
                      properties: bm.BmCharacteristicProperties(
                          broadcast: false,
                          read: true,
                          writeWithoutResponse: false,
                          write: true,
                          notify: true,
                          indicate: false,
                          authenticatedSignedWrites: false,
                          extendedProperties: false,
                          notifyEncryptionRequired: false,
                          indicateEncryptionRequired: false))
              ])
        ],
        success: true,
        errorCode: 0,
        errorString: ''));
    return true;
  }

  bm.BmCharacteristicData value(bm.Guid uuid, List<int> bytes) =>
      bm.BmCharacteristicData(
          remoteId: id,
          primaryServiceUuid: null,
          serviceUuid: service,
          characteristicUuid: uuid,
          instanceId: 0,
          value: bytes,
          success: true,
          errorCode: 0,
          errorString: '');
  @override
  Future<bool> readCharacteristic(bm.BmReadCharacteristicRequest r) async {
    final u = r.characteristicUuid;
    final bytes = u == uuid(4)
        ? utf8.encode(jsonEncode({
            'protocol': 1,
            'device': 'test-board',
            'version': '0.2.1-amoled',
            'elfSha256': 'a' * 64,
            'boot': 'b' * 32,
            'imageState': 2,
            'boardModel': 'esp32-s3-touch-amoled-2.16',
            'otaSupported': true,
            'otaAuth': 'hmac-sha256-image-v2'
          }))
        : List.filled(32, u == uuid(9) ? 1 : 2);
    reads.add(value(u, bytes));
    return true;
  }

  @override
  Future<bool> writeCharacteristic(bm.BmWriteCharacteristicRequest r) async {
    final u = r.characteristicUuid;
    if (u == uuid(5)) events.add('identity-proof');
    if (u == uuid(9)) {
      expect(r.value.length, 100);
      events.add('image-authorization');
    }
    writes.add(value(u, r.value));
    if (u == uuid(2) && r.value.first == 1) {
      events.add('begin');
      reads.add(value(uuid(3), [4, 0, 1, 0]));
    }
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
      'real push signs inside busy transfer before image authorization and BEGIN',
      () async {
    final platform = BoardPlatform();
    bm.FlutterBluePlusPlatform.instance = platform;
    final helper = BleOtaService(
        upgradeClientFactory: () =>
            AppOtaClient(Uri.parse('https://example.test'),
                client: MockClient((r) async {
              platform.events.add('cloud-authorize');
              expect(jsonDecode(r.body)['proof'], '02' * 32);
              return http.Response(
                  jsonEncode({
                    'scope': 'ble-ota',
                    'expiresIn': 60,
                    'protocol': 'hmac-sha256-image-v2',
                    'authorization': '03' * 100
                  }),
                  200);
            })));
    await helper.connect(BluetoothDevice.fromId(platform.id.str));
    final bytes = amoledImage();
    helper.retainOfficialUpgrade(
        DownloadedFirmware(bytes, '0.3.0-amoled', ticket: 'ticket'));
    final result = await helper.push(bytes, chunkSize: 511).toList();
    expect(platform.events,
        ['identity-proof', 'cloud-authorize', 'image-authorization', 'begin']);
    expect(result.last.success, isFalse);
    expect(result.last.log, contains('状态不允许'));
    await helper.disconnect();
  });
}
