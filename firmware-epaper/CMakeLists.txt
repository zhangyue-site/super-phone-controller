cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# 版本号来自 CI/本地构建传入的 PROJECT_VER。ESP-IDF 会把它写进
# esp_app_desc_t，OTA 服务端从固件头部读出这个字段做版本比较。
# 不传的话默认 "1"，会导致设备永远认为"已是最新"。
if(NOT DEFINED PROJECT_VER)
    set(PROJECT_VER "1")
endif()

project(phone_controller_epaper VERSION ${PROJECT_VER})
