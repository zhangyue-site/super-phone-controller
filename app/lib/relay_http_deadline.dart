import 'dart:async';
import 'package:http/http.dart' as http;

/// A received denial remains terminal even if its error body stalls.
class RelayHttpResponseIncomplete implements Exception {
  final int status;
  const RelayHttpResponseIncomplete(this.status);
  @override
  String toString() => '中转HTTP $status 响应未完整接收';
}

/// Bound the entire relay exchange, including streamed body delivery, below
/// the server lease. Timeout aborts the actual request; it does not resend it.
Future<http.Response> relayHttpPost(http.Client client, Uri uri,
    {required Map<String, String> headers,
    required String body,
    Duration deadline = const Duration(seconds: 3)}) async {
  final abort = Completer<void>();
  int? status;
  final request = http.AbortableRequest('POST', uri, abortTrigger: abort.future)
    ..headers.addAll(headers)
    ..body = body;
  return (() async {
    try {
      final response = await client.send(request);
      status = response.statusCode;
      return await http.Response.fromStream(response);
    } catch (_) {
      if (status != null && status != 200) {
        throw RelayHttpResponseIncomplete(status!);
      }
      rethrow;
    }
  })()
      .timeout(deadline, onTimeout: () {
    if (!abort.isCompleted) abort.complete();
    if (status != null && status != 200) {
      throw RelayHttpResponseIncomplete(status!);
    }
    throw TimeoutException('中转网络请求超时，已中止本次请求', deadline);
  });
}
