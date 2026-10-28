import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/role_state.dart';

void main() {
  test('controller never requests capture and target requires all links', () {
    expect(const RoleState(AppRole.controller, board: true, capture: false, relay: true).needsCapture, isFalse);
    const target = RoleState(AppRole.target, board: true, capture: false, relay: true);
    expect(target.needsCapture, isTrue);
    expect(target.ready, isFalse);
    expect(const RoleState(AppRole.target, board: true, capture: true, relay: true).ready, isTrue);
    expect(const RoleState(AppRole.target, board: false, capture: true, relay: true).ready, isFalse);
    expect(const RoleState(AppRole.target, board: true, capture: true, relay: false).ready, isFalse);
  });
}
