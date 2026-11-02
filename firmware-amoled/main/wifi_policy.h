#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
bool pc_wifi_config_valid(const char *ssid,const char *password,const char *endpoint);
bool pc_wifi_maintenance_allowed(bool usb,bool armed,bool ota,bool ble);
bool pc_wifi_manifest(const char *,size_t,uint32_t *,char sha[65],char version[32]);
