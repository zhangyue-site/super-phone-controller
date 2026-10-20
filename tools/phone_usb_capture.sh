#!/system/bin/sh
# Run only on the authorized target phone. No package installation, no Wi-Fi.
# Capture for at most ~2 minutes; writes no audio, screen or user data.
for tick in $(seq 1 40); do
 date '+%H:%M:%S'
 for path in /sys/class/net/usb* /sys/class/net/eth*; do
  [ -e "$path" ] || continue
  iface=${path##*/}
  ip -brief address show dev "$iface"
  ip route show dev "$iface"
  ping -I "$iface" -c 1 -W 1 192.168.77.1
 done
 sleep 2
done
