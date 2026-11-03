#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../firmware-amoled/main/power.c"
static uint8_t registers[256];
static int fault_read, fault_write, mismatch, added, removed, writes;
const char *esp_err_to_name(int err) { (void)err; return "mock"; }
int bsp_i2c_init(void) { return 0; }
void *bsp_i2c_get_handle(void) { return (void *)1; }
int i2c_master_bus_add_device(void *bus, const i2c_device_config_t *cfg, void **out) {
    assert(bus && cfg->device_address == 0x34 && cfg->scl_speed_hz == 100000);
    *out = (void *)2; added++; return 0;
}
int i2c_master_bus_rm_device(void *dev) { assert(dev); removed++; return 0; }
int i2c_master_transmit_receive(void *dev, const uint8_t *reg, size_t n, uint8_t *out, size_t m, int timeout) {
    assert(dev && n == 1 && m == 1 && timeout == 200);
    if (fault_read) return 77;
    *out = registers[*reg];
    if (mismatch && *reg == 0x22 && writes) *out ^= 2;
    return 0;
}
int i2c_master_transmit(void *dev, const uint8_t *data, size_t n, int timeout) {
    assert(dev && n == 2 && timeout == 200);
    if (fault_write) return 78;
    assert(data[0] == 0x22 || data[0] == 0x10);
    registers[data[0]] = data[1]; writes++; return 0;
}
static void reset(void) {
    memset(registers, 0, sizeof registers); registers[3] = 0x4a;
    pmic = NULL; ready = false;
    fault_read = fault_write = mismatch = added = removed = writes = 0;
}
int main(void) {
    reset(); assert(amoled_power_shutdown() == ESP_ERR_INVALID_STATE);
    registers[3] = 0; assert(amoled_power_init() == ESP_ERR_NOT_SUPPORTED); assert(!writes && removed == 1);
    reset(); fault_read = 1; assert(amoled_power_init() == 77); assert(!writes && removed == 1);
    reset(); fault_write = 1; assert(amoled_power_init() == 78); assert(removed == 1);
    reset(); mismatch = 1; assert(amoled_power_init() == ESP_ERR_INVALID_RESPONSE); assert(removed == 1);
    for (int before = 0; before < 256; before++) {
        reset(); registers[0x22] = before;
        assert(amoled_power_init() == 0);
        assert(registers[0x22] == ((before | 2) & ~1));
        assert(writes == (registers[0x22] != before));
        assert(amoled_power_init() == 0 && added == 1);
        registers[0x10] = 0xa4;
        assert(amoled_power_shutdown() == 0 && registers[0x10] == 0xa5);
        fault_read = 1; assert(amoled_power_shutdown() == 77);
        fault_read = 0; fault_write = 1; assert(amoled_power_shutdown() == 78);
    }
    puts("AMOLED power: 256 register preservation cases, failures, readback and shutdown passed");
}
