#pragma once
void controller_storage_start();
void controller_storage_status();
void controller_storage_dump();
void controller_diagnostic_state(char *out,unsigned size);
void controller_storage_events_dump();

#include <stddef.h>
size_t controller_storage_tail(bool events,char *out,size_t capacity);
