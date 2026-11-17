import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/io_client.dart';
import 'package:pcflash/relay_http_deadline.dart';

void main() {
  for (final status in [401, 403, 409]) {
    test('known HTTP $status with truncated body stays terminal', () async {
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final client = IOClient();
      server.listen((socket) {
        var sent = false;
        socket.listen((_) async {
          if (sent) return;
          sent = true;
          socket.write(
              'HTTP/1.1 $status Denied\r\nContent-Length: 100\r\nConnection: close\r\n\r\n{');
          await socket.flush();
          socket.destroy();
        });
      });
      Object? error;
      try {
        try {
          await relayHttpPost(
              client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
              headers: {}, body: '{}');
        } catch (e) {
          error = e;
        }
        expect(error, isA<RelayHttpResponseIncomplete>());
        expect((error as RelayHttpResponseIncomplete).status, status);
      } finally {
        client.close();
        await server.close();
      }
    });
  }

  test('timeout itself closes real socket before client cleanup', () async {
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final peerClosed = Completer<void>();
    Socket? peer;
    var sent = false;
    final client = IOClient();
    server.listen((socket) {
      peer = socket;
      socket.listen((_) {
        if (sent) return;
        sent = true;
        socket.add(utf8.encode(
            'HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: keep-alive\r\n\r\n{'));
      }, onDone: () {
        if (!peerClosed.isCompleted) peerClosed.complete();
      });
    });
    try {
      await expectLater(
          relayHttpPost(
              client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
              headers: {},
              body: '{}',
              deadline: const Duration(milliseconds: 150)),
          throwsA(isA<TimeoutException>()));
      await peerClosed.future.timeout(const Duration(seconds: 1));
      expect(peerClosed.isCompleted, isTrue);
    } finally {
      client.close();
      peer?.destroy();
      await server.close();
    }
  });

  for (final status in [401, 403, 409]) {
    test('known HTTP $status denial is not downgraded to retryable timeout',
        () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final client = IOClient();
      server.listen((r) async {
        r.response.statusCode = status;
        r.response.contentLength = 100;
        r.response.write('{');
        try {
          await r.response.flush();
        } catch (_) {}
      });
      Object? error;
      try {
        try {
          await relayHttpPost(
              client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
              headers: {},
              body: '{}',
              deadline: const Duration(milliseconds: 150));
        } catch (e) {
          error = e;
        }
        expect(error, isNotNull);
        expect(error, isNot(isA<TimeoutException>()));
        expect(error.toString(), contains('$status'));
      } finally {
        client.close();
        await server.close(force: true);
      }
    });
  }

  test('relay header stall aborts actual HTTP request before lease budget',
      () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final client = IOClient();
    var requests = 0;
    server.listen((r) {
      requests++;
    });
    try {
      await expectLater(
          relayHttpPost(
              client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
              headers: {},
              body: '{}',
              deadline: const Duration(milliseconds: 150)),
          throwsA(isA<TimeoutException>()));
      expect(requests, 1);
    } finally {
      client.close();
      await server.close(force: true);
    }
  });
  test('relay streamed body stall has the same bounded deadline', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final client = IOClient();
    server.listen((r) async {
      r.response.contentLength = 100;
      r.response.write('{');
      try {
        await r.response.flush();
      } catch (_) {}
    });
    try {
      await expectLater(
          relayHttpPost(
              client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
              headers: {},
              body: '{}',
              deadline: const Duration(milliseconds: 150)),
          throwsA(isA<TimeoutException>()));
    } finally {
      client.close();
      await server.close(force: true);
    }
  });
  test('normal response is returned without synthetic retry', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final client = IOClient();
    var requests = 0;
    server.listen((r) async {
      requests++;
      r.response.write('{"state":"idle"}');
      await r.response.close();
    });
    try {
      final r = await relayHttpPost(
          client, Uri.parse('http://127.0.0.1:${server.port}/poll'),
          headers: {}, body: '{}');
      expect(r.statusCode, 200);
      expect(r.body, '{"state":"idle"}');
      expect(requests, 1);
    } finally {
      client.close();
      await server.close(force: true);
    }
  });
}
