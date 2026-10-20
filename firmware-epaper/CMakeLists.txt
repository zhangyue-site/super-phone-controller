cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# OTA 服务端比较版本靠的是 esp_app_desc_t.version，它来自 CMake 变量 PROJECT_VER。
#
# 坑一：project() 的 VERSION 参数只接受数字点分形式，"2026.10.21-ci12" 会让它
#        解析失败并静默回落默认值 "1"，固件里版本永远是 1、设备永远不升级。
# 坑二：PROJECT_VER 一旦被 project() 解析成数字版本就会被覆盖，所以必须在
#        project() 之后重新设回去，且用 FORCE 避免缓存里的旧值生效。
if(NOT DEFINED PROJECT_VER OR PROJECT_VER STREQUAL "")
    set(PROJECT_VER "0.0.1")
endif()
set(_pc_full_version "${PROJECT_VER}")

string(REGEX MATCH "^[0-9]+(\\.[0-9]+)*" _pc_numeric_version "${_pc_full_version}")
if(_pc_numeric_version STREQUAL "")
    set(_pc_numeric_version "0.0.1")
endif()

project(phone_controller_epaper VERSION ${_pc_numeric_version})

# 恢复成调用方给的完整版本串，写进固件描述符。
set(PROJECT_VER "${_pc_full_version}" CACHE STRING "Firmware version" FORCE)
message(STATUS "PhoneCtl firmware version: ${PROJECT_VER}")
