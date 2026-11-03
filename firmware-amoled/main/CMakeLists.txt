idf_component_register(SRCS power.c main.c usb.c identity.c relay.c ota_engine.c ota_ble.c wifi.c wifi_policy.c direct.c direct_policy.c audio.c audio_policy.c plugin.c ui_font.c tcp_console.c INCLUDE_DIRS . REQUIRES esp_driver_i2c usb esp_driver_gpio esp_timer nvs_flash json esp_app_format esp_hw_support app_update bt mbedtls esp_wifi esp_netif esp_event esp_http_client lwip esp_codec_dev)
target_compile_definitions(${COMPONENT_LIB} PRIVATE LV_LVGL_H_INCLUDE_SIMPLE)

target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=esp_panic_handler")
