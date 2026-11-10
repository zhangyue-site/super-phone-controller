import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:pcflash/ota_data_write.dart';

void main() {
  final busy = FlutterBluePlusException(ErrorPlatform.android,
      'writeCharacteristic', 17, 'GATT_INSUFFICIENT_RESOURCES');
  test('retries only explicitly rejected data writes', () async {
    var attempts = 0;
    final waits = <Duration>[];
    await writeOtaData(
        write: () async {
          if (++attempts < 3) throw busy;
        },
        checkActive: () {},
        wait: (d) async {
          waits.add(d);
        });
    expect(attempts, 3);
    expect(waits,
        [const Duration(milliseconds: 100), const Duration(milliseconds: 100)]);
  });
  test('unknown result and disconnected write are never retried', () async {
    for (final error in [
      TimeoutException('unknown'),
      FlutterBluePlusException(
          ErrorPlatform.android, 'writeCharacteristic', 133, 'GATT_ERROR')
    ]) {
      var attempts = 0;
      await expectLater(
          writeOtaData(
              write: () async {
                attempts++;
                throw error;
              },
              checkActive: () {},
              wait: (_) async {}),
          throwsA(same(error)));
      expect(attempts, 1);
    }
  });
  test('STOP during backoff prevents another write', () async {
    var stopped = false, attempts = 0;
    await expectLater(
        writeOtaData(write: () async {
          attempts++;
          throw busy;
        }, checkActive: () {
          if (stopped) throw StateError('stopped');
        }, wait: (_) async {
          stopped = true;
        }),
        throwsStateError);
    expect(attempts, 1);
  });
  test('persistent resource rejection ends with useful message', () async {
    var attempts = 0;
    await expectLater(
        writeOtaData(
            write: () async {
              attempts++;
              throw busy;
            },
            checkActive: () {},
            wait: (_) async {}),
        throwsA(isA<StateError>()
            .having((e) => e.message, 'message', contains('控制板接收繁忙'))));
    expect(attempts, 21);
  });
  test('other platforms and operations do not enter Android data retry',
      () async {
    for (final error in [
      FlutterBluePlusException(
          ErrorPlatform.apple, 'writeCharacteristic', 17, 'other'),
      FlutterBluePlusException(
          ErrorPlatform.android, 'readCharacteristic', 17, 'other')
    ]) {
      var attempts = 0;
      await expectLater(
          writeOtaData(
              write: () async {
                attempts++;
                throw error;
              },
              checkActive: () {},
              wait: (_) async {}),
          throwsA(same(error)));
      expect(attempts, 1);
    }
  });
  test('waits for BEGIN processing before first data write', () async {
    var reads = 0, waits = 0;
    await waitForOtaReceiver(
        read: () async => [++reads < 3 ? 0 : 1, 0, 0],
        checkActive: () {},
        wait: (_) async {
          waits++;
        });
    expect(reads, 3);
    expect(waits, 2);
  });
  test('receiver error stops without sending data', () async {
    await expectLater(
        waitForOtaReceiver(
            read: () async => [4, 0, 3],
            checkActive: () {},
            wait: (_) async {}),
        throwsStateError);
  });
  test('STOP during receiver preparation prevents another read', () async {
    var stopped = false, reads = 0;
    await expectLater(
        waitForOtaReceiver(read: () async {
          reads++;
          return [0, 0, 0];
        }, checkActive: () {
          if (stopped) throw StateError('stopped');
        }, wait: (_) async {
          stopped = true;
        }),
        throwsStateError);
    expect(reads, 1);
  });
  test('receiver preparation has a bounded deadline', () async {
    var reads = 0;
    await expectLater(
        waitForOtaReceiver(
            read: () async {
              reads++;
              return [0, 0, 0];
            },
            checkActive: () {},
            wait: (_) async {}),
        throwsStateError);
    expect(reads, 150);
  });
}
