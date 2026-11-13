import 'dart:convert';

import 'package:flutter/services.dart';

import 'controller_config.dart';

class ControllerPairing {
  const ControllerPairing(this.ticket, this.device, this.expires,
      {this.bindingToken});

  final String ticket;
  final String device;
  final DateTime expires;
  final String? bindingToken;
  bool get hasPersistentBinding =>
      bindingToken != null &&
      RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(bindingToken!);

  bool get valid =>
      RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(ticket) &&
      RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(device) &&
      (expires.isAfter(DateTime.now()) || hasPersistentBinding);
}

class ControllerPairingStore {
  static const _storage = MethodChannel('pcflash/app');
  static Future<void> _pending = Future<void>.value();

  static Future<ControllerPairing?> read() async {
    await _pending;
    try {
      final raw = await _storage.invokeMethod<String>('readControllerPairing');
      if (raw == null) return null;
      final value = jsonDecode(raw) as Map<String, dynamic>;
      final pairing = ControllerPairing(
        value['ticket'] as String,
        value['device'] as String,
        DateTime.fromMillisecondsSinceEpoch(value['expires'] as int),
        bindingToken: value['bindingToken'] as String?,
      );
      if (value['origin'] == ControllerConfig.base && pairing.valid) {
        return pairing;
      }
      await clear();
    } catch (_) {
      // Storage can be unavailable, for example before the device unlocks.
    }
    return null;
  }

  static Future<void> save(ControllerPairing pairing) => _enqueue(() {
        if (!pairing.valid) return Future<void>.value();
        return _storage.invokeMethod<void>('saveControllerPairing', {
          'value': jsonEncode({
            'origin': ControllerConfig.base,
            'ticket': pairing.ticket,
            'device': pairing.device,
            'expires': pairing.expires.millisecondsSinceEpoch,
            if (pairing.hasPersistentBinding)
              'bindingToken': pairing.bindingToken,
          }),
        });
      });

  static Future<void> clear() =>
      _enqueue(() => _storage.invokeMethod<void>('clearControllerPairing'));

  static Future<void> _enqueue(Future<void> Function() operation) {
    return _pending = _pending.then((_) async {
      try {
        await operation();
      } catch (_) {
        // The live control session remains usable if storage is unavailable.
      }
    });
  }
}
