import 'dart:async';
import 'usb_launch.dart';

/// Preserve explicit BLE ownership across the same board's USB mode switch.
/// A different board or a sustained detach ends that route, never retargets it.
class UsbRouteLease {
  final void Function() onLost;
  String? _serial;
  Timer? _detach;
  UsbRouteLease(this.onLost);
  void select(UsbAttachment board) {
    _detach?.cancel();
    _serial = board.serial;
  }

  void update(UsbAttachment? board) {
    if (_serial == null) return;
    _detach?.cancel();
    if (board == null) {
      _detach = Timer(const Duration(seconds: 3), _lose);
    } else if (board.serial != _serial) {
      _lose();
    }
  }

  void _lose() {
    if (_serial == null) return;
    _serial = null;
    onLost();
  }

  void dispose() {
    _detach?.cancel();
    _serial = null;
  }
}
