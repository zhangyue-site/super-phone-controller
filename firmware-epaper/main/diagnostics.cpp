#include "diagnostics.h"
#include "log_ring.h"
#include "usb.h"
#include <stdio.h>
#include <stdarg.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

static controller::LogRing<4096> logs;
static portMUX_TYPE log_mux=portMUX_INITIALIZER_UNLOCKED;
static int capture(const char *format,va_list args){
 char line[384];int total=vsnprintf(line,sizeof(line),format,args);
 if(total>0){
  size_t size=(size_t)total<sizeof(line)?(size_t)total:sizeof(line)-1;
  taskENTER_CRITICAL(&log_mux);logs.append(line,size);taskEXIT_CRITICAL(&log_mux);
 }
 return total;
}
void controller_logs_start(){esp_log_set_vprintf(capture);}
void controller_logs_dump(){
 static char snapshot[4097];
 taskENTER_CRITICAL(&log_mux);logs.snapshot(snapshot,sizeof(snapshot));taskEXIT_CRITICAL(&log_mux);
 controller_usb_write("--- LOGS BEGIN ---\r\n");
 controller_usb_write(snapshot);
 controller_usb_write("\r\n--- LOGS END ---\r\n");
}
