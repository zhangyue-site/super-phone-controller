import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/io_client.dart';
import 'package:pcflash/cloud_relay.dart';
import 'package:pcflash/relay_http_deadline.dart';

void main() {
  for (final consumed in [false, true]) {
    test('real timed out HTTP poll: consumed=$consumed never replays input',
        () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final client = IOClient();
      var polls = 0, writes = 0, disconnects = 0;
      final nonces = <Object?>[];
      server.listen((r) async {
        final body = jsonDecode(await utf8.decoder.bind(r).join()) as Map;
        nonces.add(body['nonce']);
        polls++;
        if (polls == 1) {
          await Future<void>.delayed(const Duration(milliseconds: 400));
        }
        try {
          r.response.write(jsonEncode(
              {'state': consumed && polls > 1 ? 'awaiting_receipt' : 'idle'}));
          await r.response.close();
        } catch (_) {}
      });
      final relay = CloudRelay(
        post: (p, b) async {
          if (p != 'poll') return {'state': 'connected'};
          final response = await relayHttpPost(
              client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
              headers: {},
              body: jsonEncode(b),
              deadline: const Duration(milliseconds: 150));
          return jsonDecode(response.body) as Map<String, dynamic>;
        },
        read: () async => {'nonce': '12121212121212121212121212121212'},
        write: (_) async {
          writes++;
        },
        disconnect: () async {
          disconnects++;
        },
        onError: (_) {},
      );
      try {
        await relay.start();
        await Future<void>.delayed(const Duration(milliseconds: 1000));
        expect(polls, greaterThanOrEqualTo(2));
        expect(nonces.toSet(), {'12121212121212121212121212121212'});
        expect(writes, 0);
        expect(relay.isClosed, consumed);
        expect(disconnects, consumed ? 1 : 0);
      } finally {
        await relay.close();
        client.close();
        await server.close(force: true);
      }
    });
  }
}
