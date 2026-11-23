#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
typedef struct {
 atomic_uint last_activity_ms;
 atomic_int brightness;
 atomic_bool touch_held;
 atomic_bool off_latched;
 /* Owned exclusively by the LVGL touch-read callback. */
 bool discard_touch;
} amoled_display_idle_t;
void amoled_display_idle_init(amoled_display_idle_t *s,uint32_t now);
void amoled_display_idle_activity(amoled_display_idle_t *s,uint32_t now);
int amoled_display_idle_target(const amoled_display_idle_t *s,uint32_t now,bool keep_visible);
void amoled_display_idle_applied(amoled_display_idle_t *s,int brightness);
/* true means discard this raw sample, including the release after wake. */
bool amoled_display_idle_touch(amoled_display_idle_t *s,bool pressed,uint32_t now);
