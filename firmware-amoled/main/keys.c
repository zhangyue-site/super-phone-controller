#include "keys.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include <stdint.h>

/* 默认只接 BOOT(GPIO0)。以后若确认真它按键 GPIO，可在 keys_cfg 里加条目。 */
static const int keys_cfg[] = {0, -1, -1};
#define KEY_COUNT (sizeof(keys_cfg) / sizeof(keys_cfg[0]))

static bool level[KEY_COUNT];
static int64_t pressed_at[KEY_COUNT];
static int64_t released_at[KEY_COUNT];
static int clicks[KEY_COUNT];
static bool long_fired[KEY_COUNT];
static bool ready = false;

void amoled_keys_start(void) {
    gpio_config_t cfg = {
        .pin_bit_mask = 0,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    for (unsigned i = 0; i < KEY_COUNT; ++i) {
        if (keys_cfg[i] >= 0) cfg.pin_bit_mask |= 1ULL << keys_cfg[i];
    }
    if (!cfg.pin_bit_mask) return;
    if (gpio_config(&cfg) != ESP_OK) return;
    for (unsigned i = 0; i < KEY_COUNT; ++i) {
        if (keys_cfg[i] >= 0) level[i] = gpio_get_level(keys_cfg[i]);
    }
    ready = true;
}

int amoled_keys_poll(void) {
    if (!ready) return 0;
    int64_t now = esp_timer_get_time();
    for (unsigned i = 0; i < KEY_COUNT; ++i) {
        if (keys_cfg[i] < 0) continue;
        bool now_level = gpio_get_level(keys_cfg[i]);
        if (level[i] && !now_level) {                 /* 按下（低有效） */
            pressed_at[i] = now;
            long_fired[i] = false;
            clicks[i] = (now - released_at[i] < 350000) ? clicks[i] + 1 : 1;
        } else if (!level[i] && now_level) {          /* 抬起 */
            released_at[i] = now;
            if (!long_fired[i] && now - pressed_at[i] >= 200000 && now - pressed_at[i] < 2000000) {
                /* 短按：等双击窗口在下面统一上报 */
            }
        }
        /* 长按判定 */
        if (!now_level && !long_fired[i]) {
            int64_t held = now - pressed_at[i];
            if (held >= 8000000) { long_fired[i] = true; clicks[i] = 0; return 4; }
            if (held >= 2000000) { long_fired[i] = true; clicks[i] = 0; return 3; }
        }
        /* 双击/单击收敛：抬键 350ms 后结算 */
        if (now_level && clicks[i] > 0 && now - released_at[i] >= 350000) {
            int n = clicks[i];
            clicks[i] = 0;
            if (n == 1 && released_at[i] - pressed_at[i] < 2000000) return 1;
            if (n >= 2) return 2;
        }
        level[i] = now_level;
    }
    return 0;
}
