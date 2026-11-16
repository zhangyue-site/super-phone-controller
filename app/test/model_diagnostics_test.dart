import 'package:flutter_test/flutter_test.dart';
import 'package:pcflash/model_diagnostics.dart';

void main() {
  test('only fixed model failure stage and cause leave runtime', () {
    final e = ModelLoadFailure.fromError(
        'session',
        StateError(
            'Could not find an implementation for ConvInteger secret/path'));
    expect(e.stage, 'session');
    expect(e.cause, 'unsupported_operator');
    expect(e.toString(), isNot(contains('secret')));
    expect(
        ModelLoadFailure.fromWire({'stage': '/private/file', 'cause': 'secret'})
            .stage,
        'unknown');
  });
  test('library failure remains distinguishable from model incompatibility',
      () {
    expect(
        ModelLoadFailure.fromError('ffi',
                ArgumentError('Failed to load dynamic library /private/file'))
            .cause,
        'runtime_library');
    expect(
        ModelLoadFailure.fromError('schema', const FormatException('private'))
            .cause,
        'invalid_format');
  });
}
