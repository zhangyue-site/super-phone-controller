#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
esp_err_t amoled_identity_init(void);
const char *amoled_identity_device(void);
const char *amoled_identity_serial(void);
const char *amoled_identity_boot(void);
bool amoled_identity_ready(void);
esp_err_t amoled_identity_provision(const char *token);
bool amoled_identity_hmac(const void *data,size_t length,uint8_t out[32]);
bool amoled_hmac(const uint8_t *key,size_t key_length,const void *data,size_t length,uint8_t out[32]);
void amoled_hex(const uint8_t *data,size_t length,char *out);
bool amoled_unhex(const char *text,size_t length,uint8_t *out);
bool amoled_control_console(const char *line);
