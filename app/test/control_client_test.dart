import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pcflash/control_client.dart';

void main() {
  test('commands require BLE capability and never send without it', () async {
    var requests = 0;
    final client = ControlClient(client: MockClient((request) async {
      requests++;
      return http.Response('{}', 200);
    }));
    expect(client.authorized, false);
    await expectLater(
        client.command('confirm', taskId: 'a' * 32), throwsFormatException);
    await expectLater(client.command('stop'), throwsFormatException);
    expect(requests, 0);
    client.close();
  });
}
