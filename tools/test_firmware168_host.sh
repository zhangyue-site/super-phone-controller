#!/usr/bin/env bash
# Host-only verification. Does not build ESP-IDF images or contact devices/services.
set -euo pipefail
cd "$(dirname "$0")/.."
task_dir=$(mktemp -d)
trap 'rm -rf "$task_dir"' EXIT
cc_cmd=${CC:-cc}
cxx_cmd=${CXX:-c++}
python_cmd=${PYTHON:-python3}
"$cc_cmd" -std=c11 -Ifirmware-epaper/main -c firmware-epaper/main/ota_guard.c -o "$task_dir/ota_guard.o"
for suite in tap_consent usb_console_policy http_keyboard_policy product_display_policy touch_ui interaction keyboard_policy ble_local_policy usb_consent usb_endpoint_budget power_key_policy ota_resume_policy ota_health hid_pointer relay_display_policy; do
 "$cxx_cmd" -std=c++17 -pthread -Ifirmware-epaper/main "tests/${suite}_test.cpp" firmware-epaper/main/gesture.cpp "$task_dir/ota_guard.o" -o "$task_dir/$suite"
 "$task_dir/$suite"
 echo "$suite PASS"
done
"$cxx_cmd" -std=c++17 -DCONFIG_CONTROLLER_USB_LOCAL=1 -DCONFIG_CONTROLLER_ADB_MAINTENANCE=0 -Ifirmware-epaper/main -Itests/fixtures/adb_disabled tests/no_adb_transport_test.cpp firmware-epaper/main/adb_local.cpp -o "$task_dir/no_adb_transport"
"$task_dir/no_adb_transport"
if nm -u "$task_dir/no_adb_transport" | grep -E 'socket|connect|send|recv|bind|listen'; then exit 1; fi
echo 'no_adb_transport PASS (actual production stub, zero socket dependencies)'
"$cxx_cmd" -std=c++17 -Wall -Wextra -Werror -Ifirmware-epaper/main tests/cloud_http_config_test.cpp -o "$task_dir/cloud-default"
"$task_dir/cloud-default"
"$cxx_cmd" -std=c++17 -Wall -Wextra -Werror -Ifirmware-epaper/main '-DDISPLAY_TLS_SERVER_NAME="tls.example.invalid"' tests/cloud_http_config_test.cpp -o "$task_dir/cloud-tls"
"$task_dir/cloud-tls"
"$cxx_cmd" -std=c++17 -Wall -Wextra -Werror -Ifirmware-epaper/main '-DDISPLAY_TLS_SERVER_NAME="tls.example.invalid"' '-DDISPLAY_HTTP_HOST="http.example.invalid"' '-DDISPLAY_ADB_PROXY_HOST="proxy.example.invalid"' -DDISPLAY_ADB_PROXY_PORT=8443 tests/cloud_http_config_test.cpp -o "$task_dir/cloud-overrides"
"$task_dir/cloud-overrides"
echo 'cloud_http_config PASS (3 configurations)'
"$python_cmd" tests/test_product_screens.py
"$python_cmd" tests/test_no_adb_source.py
"$python_cmd" tests/test_public_firmware_config.py
