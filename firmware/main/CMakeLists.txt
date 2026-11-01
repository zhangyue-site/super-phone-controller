idf_component_register(SRCS "main.c" "led.c" "link.c" "wifi.c" "ota_guard.c" "usb_ota.c" "ota.cpp"
                       INCLUDE_DIRS "."
                       REQUIRES driver esp_timer esp_wifi nvs_flash esp_event esp_netif
                                app_update esp_partition mbedtls esp_http_client)
