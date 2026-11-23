#pragma once
#include "lvgl.h"
void amoled_companion_ui_create(lv_obj_t *root,lv_event_cb_t action,bool disabled);
void amoled_companion_ui_destroy(void);
void amoled_companion_ui_tick(void);
void amoled_companion_ui_set_starting(bool starting);
