"""Compile the actual console functions with a host socket/LVGL harness."""
from pathlib import Path
import subprocess
import tempfile
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
source = (root / 'firmware-amoled/main/tcp_console.c').read_text()

def function(name):
    start = source.index('static ', source.index(name) - 32)
    # Find declaration start independent of return type length.
    start = source.rfind('\n', 0, source.index(name)) + 1
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <time.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <pthread.h>
static int64_t esp_timer_get_time(void) {struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1000000LL+t.tv_nsec/1000;}
'''
snapshot = r'''
typedef struct {struct {unsigned w,h,stride;} header;void *data;} lv_draw_buf_t;
typedef int lv_obj_t;
#define LV_COLOR_FORMAT_RGB565 0
#define ESP_OK 0
static bool locked, fail_snapshot, freed;
static int sends;
static unsigned char pixels[16];
static lv_draw_buf_t buf={{2,2,4},pixels};
static int esp_lv_adapter_lock(int ms){(void)ms;assert(!locked);locked=true;return 0;}
/* Pinned BSP 2.0.1 forwards esp_err_t as bool without conversion. */
static bool bsp_display_lock(int ms){return esp_lv_adapter_lock(ms);}
static void esp_lv_adapter_unlock(void){assert(locked);locked=false;}
static void bsp_display_unlock(void){esp_lv_adapter_unlock();}
static lv_obj_t *lv_screen_active(void){assert(locked);return NULL;}
static lv_draw_buf_t *lv_snapshot_take(lv_obj_t *s,int f){(void)s;(void)f;assert(locked);return fail_snapshot?NULL:&buf;}
static void lv_draw_buf_destroy(lv_draw_buf_t *b){assert(b==&buf);freed=true;}
static int send_all(int fd,const char *p,size_t n){(void)fd;(void)p;(void)n;assert(!locked && "network send must not hold UI lock");sends++;return -1;}
static void send_text(int fd,const char *p){send_all(fd,p,strlen(p));}
'''
snapshot_main = r'''
int main(void){snapshot_reply(0);assert(!locked);assert(freed);assert(sends>0);fail_snapshot=true;freed=false;snapshot_reply(0);assert(!locked);assert(!freed);return 0;}
'''
transport_main = r'''
static void *partial(void *p){int fd=*(int*)p;write(fd,"A",1);usleep(1800000);close(fd);return NULL;}
int main(void){int f[2];assert(!socketpair(AF_UNIX,SOCK_STREAM,0,f));pthread_t t;pthread_create(&t,NULL,partial,&f[1]);char line[8];int64_t start=esp_timer_get_time();bool ok=read_line_deadline(f[0],line,sizeof line,1);int64_t elapsed=esp_timer_get_time()-start;assert(!ok);assert(elapsed<1400000 && "partial line exceeded whole-line deadline");close(f[0]);pthread_join(t,NULL);
assert(!socketpair(AF_UNIX,SOCK_STREAM,0,f));int small=1024;setsockopt(f[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof small);struct timeval tv={5,0};setsockopt(f[0],SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof tv);char *data=calloc(1,4*1024*1024);start=esp_timer_get_time();int ret=send_all(f[0],data,4*1024*1024);elapsed=esp_timer_get_time()-start;assert(ret<0);assert(elapsed<4000000 && "non-reading client exceeded send deadline");free(data);close(f[0]);close(f[1]);return 0;}
'''
cases = {
    'snapshot-unlocks-before-io': prefix + snapshot + function('snapshot_reply(') + snapshot_main,
    'socket-whole-operation-deadlines': prefix + function('send_all(') +
       (function('read_line(') if 'static int read_line(' in source else '') +
       function('read_line_deadline(') + transport_main,
}
failures = []
with tempfile.TemporaryDirectory() as td:
    for name, code in cases.items():
        c = Path(td)/(name+'.c'); binary = Path(td)/name;c.write_text(code)
        subprocess.run(['cc','-std=gnu11','-pthread','-Wall','-Wextra','-Wno-unused-function',str(c),'-o',str(binary)],check=True)
        result = subprocess.run([str(binary)],timeout=12)
        print(name, 'PASS' if result.returncode == 0 else 'FAIL', flush=True)
        if result.returncode: failures.append(name)
if failures: raise SystemExit('Failed: '+', '.join(failures))
