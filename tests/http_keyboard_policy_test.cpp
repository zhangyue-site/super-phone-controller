#include "http_keyboard_policy.h"
#include <cassert>
#include <string>
#include <limits>
int main(){using namespace controller;
 assert(keyboard_command_id("0123456789abcdef0123456789abcdef"));assert(!keyboard_command_id("012"));assert(!keyboard_command_id("0123456789abcdef0123456789abcdeg"));assert(!keyboard_command_id("0123456789abcdef0123456789abcdef0"));
 assert(keyboard_json_zero_escape(R"(a\u0000)"));assert(!keyboard_json_zero_escape(R"(a\\u0000)"));
 assert(keyboard_http_byte(255));assert(!keyboard_http_byte(256));assert(!keyboard_http_byte(-1));assert(!keyboard_http_byte(2.5));assert(!keyboard_http_byte(std::numeric_limits<double>::quiet_NaN()));
 std::string text(256,'a'),actual;unsigned calls=0,status=0;bool alive=true;
 auto live=[&](){return alive;};auto check=[&](){++status;return true;};
 assert(keyboard_http_run(text.data(),text.size(),[&](const uint8_t *p,size_t n){assert(n==8);++calls;actual.append((const char*)p,n);return true;},live,check));
 assert(calls==32&&status==32&&actual==text);
 calls=0;assert(!keyboard_http_run(text.data(),text.size(),[&](const uint8_t*,size_t){return ++calls<2;},live,check));assert(calls==2); // Partial input is never internally retried.
 calls=0;alive=true;assert(!keyboard_http_run("123456789",9,[&](const uint8_t*,size_t){++calls;alive=false;return true;},live,check));assert(calls==1); // STOP after first fragment prevents second.
 alive=true;calls=0;assert(!keyboard_http_run("abc",3,[&](const uint8_t*,size_t){++calls;return true;},live,[](){return false;}));assert(calls==0);
 assert(!keyboard_http_text("a\nb",3));assert(!keyboard_http_text("\0",1));assert(!keyboard_http_text(text.data(),257));assert(!keyboard_http_text("",0));
 actual.clear();assert(keyboard_http_run("123456789",9,[&](const uint8_t *p,size_t n){assert(n==8||n==1);actual.append((const char*)p,n);return true;},live,check));assert(actual=="123456789");
}
