import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/target_check_errors.dart';

void main() {
  test('old generation cannot clear or overwrite a new generation error', () {
    final errors = TargetCheckErrors()..reset(1);
    errors.fail(TargetCheckPhase.window, 'old', 1);
    errors.reset(2);
    errors.fail(TargetCheckPhase.window, 'new', 2);
    errors.succeed(TargetCheckPhase.window, 1);
    errors.fail(TargetCheckPhase.capture, 'late failure', 1);
    expect(errors.messages.single, contains('new'));
    errors.succeed(TargetCheckPhase.capture, 2);
    expect(errors.messages.single, contains('new'));
    errors.succeed(TargetCheckPhase.window, 2);
    expect(errors.messages, isEmpty);
  });
}
