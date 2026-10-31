#!/usr/bin/env python3
"""Explicit-device USB maintenance transport; never selects the first port."""
import argparse
import json
import re
import time
from pathlib import Path
import serial
from serial.tools import list_ports

def normalized(value):
    return value.upper().replace(':', '').replace('-', '')

def exchange(port, device, request, binary=None):
    ports = [p for p in list_ports.comports() if p.device == port]
    if len(ports) != 1 or normalized(ports[0].serial_number or '') != normalized(device):
        raise RuntimeError('USB serial does not match the explicit target')
    s = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=5)
    s.dtr = False
    s.rts = False
    s.port = port
    s.open()
    try:
        s.reset_input_buffer()
        s.write(json.dumps(request, ensure_ascii=False).encode() + b'\n')
        s.flush()
        end = time.monotonic() + 12
        line = bytearray()
        while time.monotonic() < end:
            char = s.read(1)
            if char == b'\n':
                break
            line.extend(char)
            if len(line) > 32768:
                raise RuntimeError('oversized response')
        else:
            raise TimeoutError('no complete device response')
        result = json.loads(line)
        if result.get('result') == 'snapshot':
            if binary is None:
                raise RuntimeError('snapshot requires --binary')
            size = result['bytes']
            if not 0 < size <= 1024 * 1024:
                raise RuntimeError('unexpected snapshot size')
            data = bytearray()
            end = time.monotonic() + 35
            while len(data) < size and time.monotonic() < end:
                data.extend(s.read(min(8192, size - len(data))))
            if len(data) != size:
                raise TimeoutError(f'incomplete snapshot: {len(data)} / {size}')
            Path(binary).write_bytes(data)
        return result
    finally:
        s.close()

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', required=True)
    ap.add_argument('--device', required=True)
    ap.add_argument('--request', required=True, help='JSON object or @path')
    ap.add_argument('--binary')
    ap.add_argument('--output')
    args = ap.parse_args()
    text = Path(args.request[1:]).read_text() if args.request.startswith('@') else args.request
    result = exchange(args.port, args.device, json.loads(text), args.binary)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(encoded + '\n')
    print(encoded)
