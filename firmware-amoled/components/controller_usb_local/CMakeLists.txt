idf_component_register(
    SRCS "usb_network.cpp" "adb_local.cpp"
    INCLUDE_DIRS "."
    REQUIRES lwip esp_wifi esp_event esp_netif nvs_flash usb mbedtls esp_tinyusb)

# Private board identity stays out of git via .gitignore (device_adb_keys.h).
# Compile-time gate: the stack only initializes when both
# CONFIG_CONTROLLER_USB_LOCAL and CONFIG_TINYUSB_NET_MODE_NCM are set
# (sdkconfig.usb-local.defaults build variant). Default build = inert object code.
