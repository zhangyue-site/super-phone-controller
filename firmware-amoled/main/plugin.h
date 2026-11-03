#pragma once
#include <stdbool.h>
#include <stddef.h>
bool amoled_plugin_prepare(const char *entry,const char *parameters_json);
bool amoled_plugin_confirm(void);
void amoled_plugin_cancel(void);
unsigned amoled_plugin_stage(void);
bool amoled_plugin_text(char *,size_t);
