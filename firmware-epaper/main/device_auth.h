#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
bool controller_device_sign(const char *domain,const uint8_t nonce[32],uint8_t proof[32]);
#ifdef __cplusplus
}
#endif
