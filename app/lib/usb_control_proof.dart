import 'usb_launch.dart';

class UsbSessionChanged extends StateError {
  UsbSessionChanged() : super('USB连接已改变，请重新连接；旧动作不会重发');
}

/// Possession proof for this physical USB attachment; never scans Bluetooth.
class UsbControlProof {
  final UsbAttachment usb;
  final bool Function()? isCurrent;
  UsbControlProof(this.usb, {this.isCurrent});

  Future<void> check() async {
    if (isCurrent?.call() == false) throw StateError('USB控制授权已取消');
    final current = await UsbLaunch.snapshot();
    if (isCurrent?.call() == false ||
        current?.session != usb.session ||
        current?.serial != usb.serial) {
      throw UsbSessionChanged();
    }
  }

  Future<Map<String, dynamic>> request(
      Future<Map<String, dynamic>> Function(Map<String, dynamic>) challenge,
      {String? expectedDevice}) async {
    await check();
    final info = await UsbLaunch.channel
        .invokeMapMethod<String, dynamic>('info', {'session': usb.session});
    await check();
    final device = info?['device'];
    if (info?['protocol'] != 1 ||
        info?['usbSerial'] != usb.serial ||
        device is! String ||
        !RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(device) ||
        (expectedDevice != null && expectedDevice != device) ||
        (usb.deviceId != null && usb.deviceId != device)) {
      throw StateError('USB控制板身份不一致');
    }
    final issued = await challenge({'device': device, 'serial': usb.serial});
    await check();
    final nonce = issued['challenge'];
    if (nonce is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(nonce)) {
      throw const FormatException('USB控制授权挑战无效');
    }
    final signed = await UsbLaunch.channel.invokeMapMethod<String, dynamic>(
        'sign', {'session': usb.session, 'nonce': nonce});
    await check();
    final proof = signed?['proof'];
    if (signed?['device'] != device ||
        signed?['usbSerial'] != usb.serial ||
        proof is! String ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(proof)) {
      throw StateError('USB签名身份不一致');
    }
    return {
      'device': device,
      'serial': usb.serial,
      'challenge': nonce,
      'proof': proof
    };
  }
}
