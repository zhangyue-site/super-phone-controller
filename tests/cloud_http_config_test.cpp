#include "cloud_http_config.h"
#include <cassert>
#include <cstring>
struct Config {const char *common_name="must-be-cleared";bool skip_cert_common_name_check=true;};
int main(){
 Config cfg;controller::cloud_tls_configure(cfg);assert(!cfg.skip_cert_common_name_check);
#ifdef DISPLAY_TLS_SERVER_NAME
 assert(cfg.common_name&&std::strcmp(cfg.common_name,DISPLAY_TLS_SERVER_NAME)==0);
#else
 assert(cfg.common_name==nullptr);
#endif
#ifdef DISPLAY_HTTP_HOST
 assert(std::strcmp(controller::cloud_http_host(),DISPLAY_HTTP_HOST)==0);
#elif defined(DISPLAY_TLS_SERVER_NAME)
 assert(std::strcmp(controller::cloud_http_host(),DISPLAY_TLS_SERVER_NAME)==0);
#else
 assert(controller::cloud_http_host()==nullptr);
#endif
#ifdef DISPLAY_ADB_PROXY_HOST
 assert(std::strcmp(controller::cloud_legacy_proxy_host(),DISPLAY_ADB_PROXY_HOST)==0);
#else
 assert(controller::cloud_legacy_proxy_host()==nullptr);
#endif
 assert(!controller::cloud_legacy_proxy_host_valid(nullptr));assert(!controller::cloud_legacy_proxy_host_valid(""));
 assert(!controller::cloud_legacy_proxy_host_valid("-e"));assert(!controller::cloud_legacy_proxy_host_valid("host;bad"));assert(!controller::cloud_legacy_proxy_host_valid("host name"));
 assert(controller::cloud_legacy_proxy_host_valid("proxy.example.invalid"));assert(controller::cloud_legacy_proxy_host_valid("203.0.113.10"));
#ifdef DISPLAY_ADB_PROXY_PORT
 assert(controller::cloud_legacy_proxy_port()==DISPLAY_ADB_PROXY_PORT);
#else
 assert(controller::cloud_legacy_proxy_port()==443);
#endif
}
