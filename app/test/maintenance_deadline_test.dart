import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/cloud_relay.dart';
import 'package:pcflash/control_client.dart';

void main() {
  for (final slow in ['maintenance', 'read', 'ack']) {
    test('shared monotonic maintenance deadline includes $slow', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final client = http.Client();
      var writes = 0, acks = 0, reads = 0;
      final ended = Completer<Object>();
      server.listen((request) async {
        final path = request.uri.path.substring(1);
        await request.drain<void>();
        if (path == 'ack') acks++;
        if (path == slow) {
          await Future<void>.delayed(const Duration(milliseconds: 1150));
        }
        final body = path == 'maintenance'
            ? {
                'state': 'action',
                'id': 'm',
                'seq': 1,
                'op': 12,
                'packet': '00' * 48,
                'expiresIn': 1
              }
            : {'state': 'acknowledged'};
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(body));
        await request.response.close();
      });
      final relay = CloudRelay(
        post: (path, body) async {
          final result = await client.post(
              Uri.parse('http://127.0.0.1:${server.port}/$path'),
              body: jsonEncode(body));
          return jsonDecode(result.body) as Map<String, dynamic>;
        },
        read: () async {
          if (reads++ > 0 && slow == 'read') {
            await Future<void>.delayed(const Duration(milliseconds: 1150));
          }
          return {
            'nonce': 'ab' * 16,
            'relayOnline': 0,
            'seq': 1,
            'op': 12,
            'busy': 0,
            'result': 3
          };
        },
        write: (_) async {
          writes++;
        },
        disconnect: () async {},
        onError: (e) {
          if (!ended.isCompleted) ended.complete(e);
        },
      );
      await relay.start();
      await ended.future.timeout(const Duration(seconds: 4));
      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(writes, slow == 'maintenance' ? 0 : 1);
      expect(acks, slow == 'ack' ? 1 : 0);
      expect(relay.isClosed, isTrue);
      await relay.close();
      client.close();
      await server.close(force: true);
    });
  }
  test('HTTP skills are explicit unsupported and never sent', () async {
    var requests = 0;
    final client = ControlClient(client: MockClient((_) async {
      requests++;
      return http.Response('{}', 200);
    }));
    await expectLater(client.command('skills'), throwsUnsupportedError);
    await expectLater(
        client.command('skill', skillId: 'saved', parameters: {'x': 'y'}),
        throwsUnsupportedError);
    expect(requests, 0);
    client.close();
  });
}
