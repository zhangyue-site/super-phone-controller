idf_component_register(SRCS "main.cpp" "usb.cpp" "diagnostics.cpp" "usb_network.cpp" "voice.cpp" "adb_local.cpp" "touch.cpp" "sd_store.cpp" INCLUDE_DIRS "."
 REQUIRES fatfs sdmmc esp_driver_sdmmc esp_codec_dev esp_driver_i2s esp_driver_i2c lwip epaper driver usb esp_wifi esp_event esp_netif nvs_flash esp_http_client esp-tls mbedtls esp_timer esp_psram)
