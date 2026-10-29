#pragma once
namespace controller {
// UI-only state: never feeds online/server checks, actuator permission or preflight.
enum RelayDisplay { RELAY_LEGACY=-1, RELAY_CONNECTED=0, RELAY_CONTROLLING=1, RELAY_DIRECT_OFFLINE=2 };
inline int relay_display(bool usb, bool connected, bool owns, bool direct_online, bool failed, bool stopped) {
 if (!usb || failed || stopped) return RELAY_LEGACY;
 if (connected) return owns ? RELAY_CONTROLLING : RELAY_CONNECTED;
 return direct_online ? RELAY_LEGACY : RELAY_DIRECT_OFFLINE;
}
}
