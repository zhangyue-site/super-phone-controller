import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';
import 'package:pcflash/diagnostics.dart';
import 'control_client_test.dart' show FakeBoard;

void main() {
  test('old denied request cannot revoke a newer authorization', () async {
    final oldResponse = Completer<http.Response>(), seen = Completer<void>();
    var grants = 0, statuses = 0;
    final client = ControlClient(client: MockClient((r) async {
      final op = r.url.path.split('/').last;
      if (op == 'challenge') {
        return http.Response(jsonEncode({'challenge': 'a' * 64}), 200);
      }
      if (op == 'authorize') {
        return http.Response(
            jsonEncode({
              'ticket': (++grants == 1 ? 'a' : 'b') * 43,
              'scope': 'phone-commands',
              'expiresIn': 300
            }),
            200);
      }
      if (op == 'command' && ++statuses == 1) {
        seen.complete();
        return oldResponse.future;
      }
      return http.Response('{"state":"idle"}', 200);
    }));
    try {
      await client.authorize(FakeBoard());
      final late = expectLater(
          client.command('status'), throwsA(isA<ControlHttpFailure>()));
      await seen.future;
      await client.authorize(FakeBoard());
      oldResponse
          .complete(http.Response('{"reply":"old authorization denied"}', 403));
      await late;
      expect(grants, 2);
      expect(client.authorized, isTrue);
      expect((await client.command('status'))['state'], 'idle');
    } finally {
      await client.shutdown();
    }
  });
}
