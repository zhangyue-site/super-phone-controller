import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/cloud_relay.dart';

void main() {
  for (final amoled in [false, true]) {
    test('heartbeat survives control-only capability ($amoled)', () async {
      final heartbeat = Completer<int>();
      final relay = CloudRelay(
        post: (path, body) async {
          if (path == 'maintenance' && !heartbeat.isCompleted) {
            heartbeat.complete(body['op'] as int);
          }
          return {'state': 'idle'};
        },
        read: () async => {
          'nonce': 'ab' * 16, 'relayOnline': 0,
          if (amoled) 'wifiOtaSupported': false,
        },
        write: (_) async => fail('Idle maintenance must not write a packet'),
        disconnect: () async {},
        onError: (e) => fail('$e'),
      );
      await relay.start();
      expect(relay.supportsMaintenance, !amoled);
      if (amoled) expect(relay.requestWifiUpgrade, throwsStateError);
      expect(await heartbeat.future.timeout(const Duration(seconds: 2)), 12);
      await relay.close();
    });
  }
}
