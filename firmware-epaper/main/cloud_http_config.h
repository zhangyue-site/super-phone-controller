#pragma once
// Include after the private device_config.h. No deployment identity is stored here.
namespace controller {
inline const char* cloud_tls_server_name(){
#ifdef DISPLAY_TLS_SERVER_NAME
 return DISPLAY_TLS_SERVER_NAME;
#else
 return nullptr; // ESP-IDF verifies the hostname from DISPLAY_ENDPOINT.
#endif
}
inline const char* cloud_http_host(){
#ifdef DISPLAY_HTTP_HOST
 return DISPLAY_HTTP_HOST;
#elif defined(DISPLAY_TLS_SERVER_NAME)
 return DISPLAY_TLS_SERVER_NAME;
#else
 return nullptr; // Let the HTTP client derive Host from the URL.
#endif
}
template<class Config> inline void cloud_tls_configure(Config& config){
 config.common_name=cloud_tls_server_name();
 config.skip_cert_common_name_check=false;
}
inline const char* cloud_legacy_proxy_host(){
#ifdef DISPLAY_ADB_PROXY_HOST
 return DISPLAY_ADB_PROXY_HOST;
#else
 return nullptr; // Explicit maintenance builds need explicit transport setup too.
#endif
}
inline bool cloud_legacy_proxy_host_valid(const char *host){
 if(!host||!*host||*host=='-')return false;
 for(const char *p=host;*p;++p)if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='.'||*p=='-'||*p==':'))return false;
 return true;
}
inline unsigned cloud_legacy_proxy_port(){
#ifdef DISPLAY_ADB_PROXY_PORT
 static_assert(DISPLAY_ADB_PROXY_PORT>0&&DISPLAY_ADB_PROXY_PORT<=65535,"invalid legacy proxy port");
 return DISPLAY_ADB_PROXY_PORT;
#else
 return 443;
#endif
}
}
