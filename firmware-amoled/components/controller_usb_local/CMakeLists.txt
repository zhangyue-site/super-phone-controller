# Default builds keep this component empty (inert, no usb-local symbols reach the ELF);
# the usb-local variant build passes -D CONTROLLER_USB_LOCAL_VARIANT=1 (sdkconfig is NOT
# available at component-CMake time, kconfig runs after component scan).
if(CONTROLLER_USB_LOCAL_VARIANT)
    set(_usb_local_srcs SRCS "usb_network.cpp" "adb_local.cpp")
else()
    set(_usb_local_srcs)
endif()
idf_component_register(
    ${_usb_local_srcs}
    INCLUDE_DIRS "."
    REQUIRES lwip esp_wifi esp_event esp_netif nvs_flash usb mbedtls esp_tinyusb esp_timer log esp_hw_support heap freertos)

# Private board identity stays out of git via .gitignore (device_adb_keys.h).
# Compile-time gate: the stack only initializes when both
# CONFIG_CONTROLLER_USB_LOCAL and CONFIG_TINYUSB_NET_MODE_NCM are set
# (sdkconfig.usb-local.defaults build variant). Default build = inert object code.
