#include "power.h"
#include <stdbool.h>
#include <stdint.h>
#include "bsp/esp-bsp.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

/* Waveshare component 2.0.1 (bfeb6e6d5737178cdde78b630c8118074da0a657)
 * exposes the shared new-driver I2C bus, but no PMIC object/API.
 * Register definitions and bit operations verified against vendor XPowersLib:
 * examples/esp-idf/01_AXP2101/components/XPowersLib/src/
 * REG/AXP2101Constants.h and XPowersAXP2101.tpp, shutdown(),
 * enableLongPressShutdown(), setLongPressPowerOFF().
 * Do not construct XPowersLib: its init also changes TS measurement settings. */
enum {
    AXP_ADDRESS = 0x34, AXP_IC_TYPE = 0x03, AXP_CHIP_ID = 0x4a,
    AXP_COMMON_CONFIG = 0x10, AXP_PWROFF_EN = 0x22,
    AXP_LONG_PRESS_ENABLE = 1u << 1, AXP_LONG_PRESS_RESTART = 1u << 0,
    AXP_SHUTDOWN = 1u << 0, I2C_TIMEOUT_MS = 200,
};
static const char *TAG = "amoled_power";
static i2c_master_dev_handle_t pmic;
static bool ready;

static esp_err_t read_reg(uint8_t reg, uint8_t *value)
{
    return i2c_master_transmit_receive(pmic, &reg, 1, value, 1, I2C_TIMEOUT_MS);
}
static esp_err_t write_reg(uint8_t reg, uint8_t value)
{
    const uint8_t command[] = {reg, value};
    return i2c_master_transmit(pmic, command, sizeof(command), I2C_TIMEOUT_MS);
}

esp_err_t amoled_power_init(void)
{
    if (ready) return ESP_OK;
    esp_err_t err = bsp_i2c_init();
    if (err != ESP_OK) return err;
    i2c_master_bus_handle_t bus = bsp_i2c_get_handle();
    if (!bus) return ESP_ERR_INVALID_STATE;
    const i2c_device_config_t config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = AXP_ADDRESS,
        .scl_speed_hz = 100000,
    };
    err = i2c_master_bus_add_device(bus, &config, &pmic);
    if (err != ESP_OK) return err;
    uint8_t id = 0, before = 0, after = 0;
    err = read_reg(AXP_IC_TYPE, &id);
    if (err == ESP_OK && id != AXP_CHIP_ID) {
        ESP_LOGE(TAG, "Unexpected PMIC ID 0x%02x", id);
        err = ESP_ERR_NOT_SUPPORTED;
    }
    if (err == ESP_OK) err = read_reg(AXP_PWROFF_EN, &before);
    const uint8_t wanted = (before | AXP_LONG_PRESS_ENABLE) & ~AXP_LONG_PRESS_RESTART;
    if (err == ESP_OK && wanted != before) err = write_reg(AXP_PWROFF_EN, wanted);
    if (err == ESP_OK) err = read_reg(AXP_PWROFF_EN, &after);
    if (err == ESP_OK && after != wanted) err = ESP_ERR_INVALID_RESPONSE;
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "PMIC initialization failed: %s", esp_err_to_name(err));
        i2c_master_bus_rm_device(pmic);
        pmic = NULL;
        return err;
    }
    ready = true;
    ESP_LOGI(TAG, "AXP2101 verified; PWR long press power-off enabled (0x%02x -> 0x%02x); duration preserved", before, after);
    return ESP_OK;
}

esp_err_t amoled_power_shutdown(void)
{
    if (!ready) return ESP_ERR_INVALID_STATE;
    uint8_t value;
    esp_err_t err = read_reg(AXP_COMMON_CONFIG, &value);
    if (err == ESP_OK) err = write_reg(AXP_COMMON_CONFIG, value | AXP_SHUTDOWN);
    if (err != ESP_OK) ESP_LOGE(TAG, "PMIC shutdown command failed: %s", esp_err_to_name(err));
    return err;
}
