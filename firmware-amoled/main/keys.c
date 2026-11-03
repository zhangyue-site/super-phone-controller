#include "keys.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs.h"
#include <stdint.h>

/* 三键：A/B/C。-1 = 未接。默认只启用 BOOT(GPIO0) 作为 A。
 * GPIO 可用 NVS(keys/cfg: 3×int8) 覆盖，无需重编固件。 */
static int keys_cfg[3] = {0, -1, -1};
#define KEY_COUNT 3

static int level[KEY_COUNT];
static int64_t pressed_at[KEY_COUNT];
static int64_t released_at[KEY_COUNT];
static int clicks[KEY_COUNT];
static bool long_fired[KEY_COUNT];
static bool ready = false;
static const char *TAG = "keys";

static void load_cfg(void) {
    nvs_handle_t h;
    if (nvs_open("keys", NVS_READONLY, &h) != ESP_OK) return;
    size_t size = sizeof(keys_cfg);
    int8_t buf[3];
    if (nvs_get_blob(h, "cfg", buf, &size) == ESP_OK && size == 3) {
        for (int i = 0; i < 3; ++i) keys_cfg[i] = buf[i];
        ESP_LOGI(TAG, "cfg=%d,%d,%d", keys_cfg[0], keys_cfg[1], keys_cfg[2]);
    }
    nvs_close(h);
}

void amoled_keys_start(void) {
    load_cfg();
    gpio_config_t cfg = {
        .pin_bit_mask = 0,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    for (int i = 0; i < KEY_COUNT; ++i)
        if (keys_cfg[i] >= 0) cfg.pin_bit_mask |= 1ULL << keys_cfg[i];
    if (!cfg.pin_bit_mask) return;
    if (gpio_config(&cfg) != ESP_OK) return;
    for (int i = 0; i < KEY_COUNT; ++i)
        if (keys_cfg[i] >= 0) level[i] = gpio_get_level(keys_cfg[i]);
    ready = true;
}

/* 返回位编码：0 无；ok 事件 = (key<<4)|code，code 1短按 2双击 3长按2s 4长按8s */
int amoled_keys_poll(void) {
    if (!ready) return 0;
    int64_t now = esp_timer_get_time();
    for (int i = 0; i < KEY_COUNT; ++i) {
        if (keys_cfg[i] < 0) continue;
        bool now_level = gpio_get_level(keys_cfg[i]);
        if (level[i] && !now_level) {              /* 按下（低有效） */
            pressed_at[i] = now;
            long_fired[i] = false;
            clicks[i] = (now - released_at[i] < 350000) ? clicks[i] + 1 : 1;
        } else if (!level[i] && now_level) {       /* 抬起 */
            released_at[i] = now;
        }
        if (!now_level && !long_fired[i]) {
            int64_t held = now - pressed_at[i];
            if (held >= 8000000) { long_fired[i] = true; clicks[i] = 0; return (i << 4) | 4; }
            if (held >= 2000000) { long_fired[i] = true; clicks[i] = 0; return (i << 4) | 3; }
        }
        if (now_level && clicks[i] > 0 && now - released_at[i] >= 350000) {
            int n = clicks[i];
            clicks[i] = 0;
            if (n == 1 && released_at[i] - pressed_at[i] < 2000000) return (i << 4) | 1;
            if (n >= 2) return (i << 4) | 2;
        }
        level[i] = now_level;
    }
    return 0;
}
