#pragma once
#include <stdbool.h>

/* 物理按键：可扩展三键；默认只启用 BOOT(GPIO0)。
 * 事件由主循环轮询（无 ISR），返回：
 *   0 无、1 短按、2 双击、3 长按2秒、4 长按8秒 */
void amoled_keys_start(void);
int amoled_keys_poll(void);
