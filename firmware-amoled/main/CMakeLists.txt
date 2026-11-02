idf_component_register(SRCS main.c usb.c identity.c relay.c ota_engine.c ota_ble.c wifi.c wifi_policy.c ui_font.c INCLUDE_DIRS . REQUIRES usb esp_driver_gpio esp_timer nvs_flash json esp_app_format esp_hw_support app_update bt mbedtls esp_wifi esp_netif esp_event esp_http_client lwip)
target_compile_definitions(${COMPONENT_LIB} PRIVATE LV_LVGL_H_INCLUDE_SIMPLE)

target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=esp_panic_handler")
