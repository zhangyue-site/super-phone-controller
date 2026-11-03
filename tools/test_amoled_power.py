#!/usr/bin/env python3
"""Compile the real PMIC module with a fake IDF I2C bus; no hardware writes."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p / 'bsp').mkdir()
    (p / 'driver').mkdir()
    (p / 'esp_err.h').write_text('''#pragma once
#include <stddef.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE 1
#define ESP_ERR_NOT_SUPPORTED 2
#define ESP_ERR_INVALID_RESPONSE 3
const char *esp_err_to_name(int);
''')
    (p / 'esp_log.h').write_text('#define ESP_LOGE(...) ((void)0)\n#define ESP_LOGI(...) ((void)0)\n')
    (p / 'driver/i2c_master.h').write_text('''#pragma once
#include "esp_err.h"
#include <stdint.h>
typedef void *i2c_master_bus_handle_t;
typedef void *i2c_master_dev_handle_t;
typedef struct {int dev_addr_length, device_address, scl_speed_hz;} i2c_device_config_t;
#define I2C_ADDR_BIT_LEN_7 0
int i2c_master_bus_add_device(void *, const i2c_device_config_t *, void **);
int i2c_master_bus_rm_device(void *);
int i2c_master_transmit_receive(void *, const uint8_t *, size_t, uint8_t *, size_t, int);
int i2c_master_transmit(void *, const uint8_t *, size_t, int);
''')
    (p / 'bsp/esp-bsp.h').write_text('#include "driver/i2c_master.h"\nint bsp_i2c_init(void);\nvoid *bsp_i2c_get_handle(void);\n')
    binary = p / 'test'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-I'+str(p), '-I'+str(ROOT/'firmware-amoled/main'), str(ROOT/'tests/amoled_power_test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
