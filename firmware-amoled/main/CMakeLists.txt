idf_component_register(SRCS main.c usb.c ui_font.c INCLUDE_DIRS . REQUIRES nvs_flash json esp_app_format esp_hw_support app_update)
target_compile_definitions(${COMPONENT_LIB} PRIVATE LV_LVGL_H_INCLUDE_SIMPLE)
