#!/usr/bin/env python3
"""Follow the plugged-in phone's regular Wi-Fi.

The phone decides the network. A 5 GHz name is matched to the 2.4 GHz name
the phone can see, because the board has no 5 GHz radio. Known passphrases
are used first. Anything else comes from this Mac's keychain and is never printed.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import time

ADB = "/Users/zhangyue/Library/Android/sdk/platform-tools/adb"
# Optional legacy Mac helper; not part of the standalone runtime.
# Keep credentials in environment/keychain, never in the repository.
KNOWN_PASSWORDS = {}



def adb(serial, *args):
    return subprocess.run(
        [ADB, "-s", serial, *args],
        check=False,
        capture_output=True,
        text=True,
    ).stdout


def phone_seen():
    result = subprocess.run([ADB, "devices", "-l"], check=False, capture_output=True, text=True)
    found = []
    for line in result.stdout.splitlines()[1:]:
        if "saiph_oversea" in line or "OS_R_DR01" in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if serial == "7ac09109" or "nezha" in line or "25128PNA1C" in line or "usb:" in line:
            found.append((serial, state))
    return found


def current_ssid(serial):
    text = adb(serial, "shell", "cmd", "wifi", "status")
    match = re.search(r'Wifi is connected to "([^"]+)"', text)
    if not match:
        return None, None, None
    ssid = match.group(1)
    freq = re.search(r"Frequency:\s*(\d+)", text)
    security = "wpa2" if "wpa2-psk" in text else "wpa3" if "wpa3" in text else "open" if "open" in text else "other"
    return ssid, (int(freq.group(1)) if freq else None), security


def scan_24(serial):
    names = set()
    for line in adb(serial, "shell", "cmd", "wifi", "list-scan-results").splitlines():
        parts = line.split()
        if len(parts) < 5 or not parts[1].isdigit():
            continue
        if int(parts[1]) < 3000:
            names.add(parts[4])
    return names


def board_name(phone_ssid, seen_24):
    if not phone_ssid:
        return None
    if phone_ssid.endswith("_5G"):
        twin = phone_ssid[:-3] + "_2.4G"
        if twin in seen_24:
            return twin
        plain = phone_ssid[:-3]
        if plain in seen_24:
            return plain
        return None
    return phone_ssid


def keychain_password(ssid):
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-D", "AirPort network password", "-a", ssid, "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        print(f"读取 {ssid} 的密码时，钥匙串没有在时间内返回")
        return None
    if result.returncode != 0:
        return None
    password = result.stdout.strip()
    return password or None


def board_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    return ports[0] if ports else None


def send_wifi(port, ssid, password):
    payload = f"WIFI\t{ssid}\t{password}\n".encode()
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def read_target(serial):
    ssid, frequency, security = current_ssid(serial)
    if not ssid:
        return None
    if security not in ("wpa2", "wpa3", "open"):
        print(f"手机在 {ssid}，不是普通 Wi-Fi，继续等它切换")
        return None
    seen = scan_24(serial) if frequency and frequency >= 3000 else set()
    target = board_name(ssid, seen) if frequency and frequency >= 3000 else ssid
    if not target:
        print(f"手机在 {ssid}，板子只有 2.4GHz，这一次还没扫到对应网络")
        return None
    if security == "open":
        return target, ""
    password = os.environ.get("PHONE_WIFI_PASSWORD") or KNOWN_PASSWORDS.get(target) or KNOWN_PASSWORDS.get(ssid)
    if password is None:
        password = keychain_password(target) or keychain_password(ssid)
    if password is None:
        print(f"手机在 {ssid}，要连 {target}，这台电脑没有存过这个普通网络的密码")
        return None
    return target, password


def apply_once(previous):
    phones = phone_seen()
    if not phones:
        if previous not in (None, "absent"):
            print("手机已拔出，等下一次插入")
        elif previous is None:
            print("没有检测到插入的手机")
        return "absent"
    serial, state = phones[0]
    if state != "device":
        marker = f"wait:{serial}:{state}"
        if previous != marker:
            print(f"看到手机了，调试连接是 {state}，还读不到 Wi-Fi。若手机上有 USB 调试授权，点允许。")
        return marker
    found = read_target(serial)
    if not found:
        return previous
    target, password = found
    if previous == target:
        return previous
    port = board_port()
    if not port:
        print(f"手机网络是 {target}，板子还没插上")
        return previous
    send_wifi(port, target, password)
    print(f"已按手机当前网络连接 {target}")
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    previous = None
    if args.once:
        apply_once(None)
        return 0
    while True:
        previous = apply_once(previous)
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
