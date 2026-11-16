#!/usr/bin/env python3
"""Select a modern available runtime/device pair, never device-list order."""
import json
import re
import sys
from pathlib import Path


def select_simulator(devices, runtimes):
    candidates = []
    for runtime in runtimes.get('runtimes', []):
        identifier = runtime.get('identifier', '')
        version = runtime.get('version', '')
        if not identifier.startswith('com.apple.CoreSimulator.SimRuntime.iOS-'):
            continue
        if not runtime.get('isAvailable') or not re.fullmatch(r'\d+(?:\.\d+)*', version):
            continue
        parts = tuple(int(p) for p in version.split('.'))
        if parts[0] != 27:
            continue
        for device in devices.get('devices', {}).get(identifier, []):
            if device.get('isAvailable') and device.get('name', '').startswith('iPhone') and device.get('udid'):
                candidates.append((parts, device['udid'], identifier))
    if not candidates:
        raise ValueError('iOS27 simulator required: no available iPhone/runtime pair')
    version, udid, runtime = max(candidates)
    return {'udid': udid, 'runtime': runtime, 'version': '.'.join(map(str, version))}


if __name__ == '__main__':
    selected = select_simulator(json.loads(Path(sys.argv[1]).read_text()),
                                json.loads(Path(sys.argv[2]).read_text()))
    print(json.dumps(selected), file=sys.stderr)
    print(selected['udid'])
