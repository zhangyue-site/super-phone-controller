enum AppRole { controller, target }

/// Readiness requires independent recent frame and operation-permission evidence.
/// Planning a task does not require an already-armed idle board.
class RoleState {
  const RoleState(this.role,
      {required this.board,
      required this.capture,
      required this.relay,
      this.recentFrame = false,
      this.permission = false});
  final AppRole role;
  final bool board, capture, relay, recentFrame, permission;
  bool get needsCapture => role == AppRole.target && !capture;
  bool get canPrepare => relay;
  bool get ready => board && capture && relay && recentFrame && permission;
}
