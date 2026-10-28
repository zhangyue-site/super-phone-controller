enum AppRole { controller, target }

/// Display readiness only when every prerequisite is independently observed.
class RoleState {
  const RoleState(this.role, {required this.board, required this.capture, required this.relay});
  final AppRole role;
  final bool board;
  final bool capture;
  final bool relay;

  bool get needsCapture => role == AppRole.target && !capture;
  bool get ready => role == AppRole.target ? board && capture && relay : relay;
}
