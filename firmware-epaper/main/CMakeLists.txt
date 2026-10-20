idf_component_register(SRCS "main.cpp" "usb.cpp" INCLUDE_DIRS "."
 REQUIRES epaper driver esp_wifi esp_event esp_netif nvs_flash esp_http_client esp-tls mbedtls esp_timer esp_psram)
