#pragma once
bool controller_ota_busy();
int controller_ota_stage();
int controller_ota_progress();
void controller_ota_start();
void controller_ota_cancel();
void controller_ota_confirm();
const char *controller_ota_endpoint();

void controller_ota_changed();

void controller_ota_input_heartbeat();
void controller_ota_screen_heartbeat(bool painted);
void controller_ota_health_start();

// UI reason only; does not alter OTA commit/cancel stages.
bool controller_ota_network_unavailable();
