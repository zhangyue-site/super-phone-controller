enum TargetCheckPhase { status, capture, window, renew, recovery }

/// Poll success clears only its own phase in the current physical UI generation.
class TargetCheckErrors {
  int _generation = 0;
  final Map<TargetCheckPhase, String> _errors = {};
  void reset(int generation) {
    _generation = generation;
    _errors.clear();
  }

  void fail(TargetCheckPhase phase, Object error, int generation) {
    if (generation == _generation) _errors[phase] = error.toString();
  }

  void succeed(TargetCheckPhase phase, int generation) {
    if (generation == _generation) _errors.remove(phase);
  }

  List<String> get messages => [
        for (final entry in _errors.entries)
          '${switch (entry.key) {
            TargetCheckPhase.status => '状态检查失败',
            TargetCheckPhase.capture => '云端画面连接正在恢复',
            TargetCheckPhase.window => '控制板连接检查暂不可用',
            TargetCheckPhase.renew => '网关续期失败',
            TargetCheckPhase.recovery => '手机中转恢复检查失败',
          }}：${entry.value}'
      ];
}
