#pragma once
// Copy to device_config.h (ignored). Use a device-only token, never the server admin token.
#define DISPLAY_ENDPOINT "https://controller.example.invalid/phone-controller"
#define DISPLAY_TOKEN "replace-with-device-specific-token"

// Register a distinct device identity/token pair in the matching service.
// #define DISPLAY_DEVICE_ID "your-device-id"

// Normal HTTPS validates the URL hostname and derives Host automatically.
// For a separately addressed authenticated proxy only, configure its TLS identity:
// #define DISPLAY_TLS_SERVER_NAME "controller.example.invalid"
// #define DISPLAY_HTTP_HOST "controller.example.invalid"
// Optional legacy maintenance transport; production ADB remains disabled:
// #define DISPLAY_ADB_PROXY_HOST "203.0.113.10"
// #define DISPLAY_ADB_PROXY_PORT 443
