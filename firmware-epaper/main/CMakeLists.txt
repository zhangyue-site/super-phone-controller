idf_component_register(SRCS "main.cpp" "usb.cpp" "diagnostics.cpp" "usb_network.cpp" "voice.cpp" "adb_local.cpp" "touch.cpp" "sd_store.cpp" "ble_ota.cpp" INCLUDE_DIRS "."
 REQUIRES fatfs sdmmc esp_driver_sdmmc esp_codec_dev esp_driver_i2s esp_driver_i2c lwip epaper driver usb esp_wifi esp_event esp_netif nvs_flash esp_http_client esp-tls bt esp_timer esp_psram
 REQUIRES esp_driver_gpio esp_driver_uart esp_driver_usb_serial_jtag esp_driver_spi)

# ESP-IDF 6.0 split the monolithic `driver` component; upstream
# esp_codec_dev still includes driver/gpio.h without declaring it.
# Propagate the split components so the dependency resolves.
target_link_libraries(${COMPONENT_LIB} INTERFACE
    idf::esp_driver_gpio
    idf::esp_driver_uart)
