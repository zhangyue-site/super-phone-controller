#pragma once
#include <stdbool.h>
/* Lazy read-only worker; no grants, claims or command execution. */
void amoled_companion_monitor_enable(bool enabled);

/* 0=inactive, 1=syncing, 2=last fetch succeeded, 3=unavailable. */
unsigned amoled_companion_monitor_state(void);
