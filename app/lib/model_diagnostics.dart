class ModelLoadFailure extends FormatException {
  static const stages = {
    'asset',
    'cache',
    'hash',
    'ffi',
    'env',
    'session',
    'warmup',
    'schema',
    'unknown'
  };
  static const causes = {
    'unsupported_operator',
    'runtime_library',
    'invalid_format',
    'timeout',
    'runtime_error',
    'unknown'
  };
  final String stage, cause;
  ModelLoadFailure._(this.stage, this.cause)
      : super('本地模型准备失败（$stage / $cause）');
  factory ModelLoadFailure.fromWire(Map value) => ModelLoadFailure._(
      stages.contains(value['stage']) ? value['stage'] as String : 'unknown',
      causes.contains(value['cause']) ? value['cause'] as String : 'unknown');
  factory ModelLoadFailure.fromError(String stage, Object error) {
    final text = error.toString();
    final cause =
        text.contains('ConvInteger') || text.contains('NOT_IMPLEMENTED')
            ? 'unsupported_operator'
            : text.contains('dynamic library')
                ? 'runtime_library'
                : error is FormatException
                    ? 'invalid_format'
                    : error.runtimeType.toString() == 'TimeoutException'
                        ? 'timeout'
                        : 'runtime_error';
    return ModelLoadFailure.fromWire({'stage': stage, 'cause': cause});
  }
}
