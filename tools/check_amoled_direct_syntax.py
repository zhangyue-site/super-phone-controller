"""Host syntax check of the complete direct worker (not an ESP-IDF firmware build)."""
from pathlib import Path
import argparse,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--cjson-dir",required=True);args=ap.parse_args()
source=(root/"firmware-amoled/main/direct.c").read_text()
source="\n".join(line for line in source.splitlines() if not line.startswith('#include "'))
shim=r"""
#include "cJSON.h"
#include "direct_policy.h"
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NO_MEM 1
#define pdPASS 1
#define pdMS_TO_TICKS(n) (n)
#define HTTP_METHOD_POST 1
#define portMAX_DELAY 1
typedef void *SemaphoreHandle_t;
extern SemaphoreHandle_t xSemaphoreCreateMutex(void);
extern int xSemaphoreTake(void *,unsigned),xSemaphoreGive(void *);
typedef void *esp_http_client_handle_t;
typedef struct {
 const char *url;int timeout_ms,buffer_size;void *crt_bundle_attach;
 bool disable_auto_redirect,keep_alive_enable;
} esp_http_client_config_t;
extern void *esp_crt_bundle_attach;
extern int64_t esp_timer_get_time(void);
extern bool amoled_relay_direct_owned(void),amoled_relay_direct_acquire(void),amoled_relay_connected(void);
extern void amoled_relay_direct_release(void);
extern bool amoled_wifi_connected(void),amoled_wifi_endpoint(char *,size_t);
extern bool amoled_usb_armed(void),amoled_usb_ready(void),amoled_identity_ready(void),amoled_ota_busy(void),amoled_ota_ready(void);
extern void amoled_usb_gate(bool);
extern bool amoled_usb_execute(uint8_t,const uint16_t[5],bool (*)(uint32_t),uint32_t);
extern void esp_fill_random(void *,size_t),amoled_hex(const uint8_t *,size_t,char *);
extern esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *);
extern esp_err_t amoled_identity_http_auth(void *);
extern void esp_http_client_set_method(void *,int),esp_http_client_set_header(void *,const char *,const char *);
extern int esp_http_client_open(void *,int),esp_http_client_write(void *,const char *,int),esp_http_client_read(void *,char *,int);
extern int64_t esp_http_client_fetch_headers(void *);
extern int esp_http_client_get_status_code(void *);
extern bool esp_http_client_is_chunked_response(void *),esp_http_client_is_complete_data_received(void *);
extern void esp_http_client_close(void *),esp_http_client_cleanup(void *);
extern void vTaskDelay(unsigned);
extern int xTaskCreate(void (*)(void *),const char *,unsigned,void *,unsigned,void *);
"""
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/"direct.c";p.write_text(shim+source)
 subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-parameter","-fsyntax-only","-I",args.cjson_dir,"-I",str(root/"firmware-amoled/main"),str(p)],check=True)
print("Complete direct worker host syntax check passed; ESP-IDF compile remains pending")

