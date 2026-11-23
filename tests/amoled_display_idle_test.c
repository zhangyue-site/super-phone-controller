#include <assert.h>
#include <limits.h>
#include "display_idle.h"
int main(void) {
 amoled_display_idle_t s;
 amoled_display_idle_init(&s,1000);
 assert(amoled_display_idle_target(&s,60999,false)==100);
 assert(amoled_display_idle_target(&s,61000,false)==30);
 assert(amoled_display_idle_target(&s,300999,false)==30);
 assert(amoled_display_idle_target(&s,301000,false)==0);
 assert(amoled_display_idle_target(&s,301000,true)==100);
 /* A touch while dark is swallowed through the full press/release, even
  * after the display task has restored brightness. No hidden button click. */
 amoled_display_idle_applied(&s,0);
 assert(amoled_display_idle_touch(&s,true,400000));
 assert(amoled_display_idle_target(&s,400001,false)==100);
 amoled_display_idle_applied(&s,100);
 assert(amoled_display_idle_touch(&s,true,400100));
 assert(amoled_display_idle_touch(&s,false,400101));
 assert(!amoled_display_idle_touch(&s,true,400200));
 assert(!amoled_display_idle_touch(&s,false,400201));
 /* Dim-screen wake is also consumed, including long holds. */
 amoled_display_idle_applied(&s,30);
 assert(amoled_display_idle_touch(&s,true,500000));
 amoled_display_idle_applied(&s,100);
 assert(amoled_display_idle_touch(&s,true,510000));
 assert(amoled_display_idle_touch(&s,false,510001));
 amoled_display_idle_activity(&s,600000);
 assert(amoled_display_idle_target(&s,659999,false)==100);
 /* Millisecond wrap-around must not cause immediate sleep or stick awake. */
 amoled_display_idle_init(&s,UINT_MAX-10000);
 assert(amoled_display_idle_target(&s,49998,false)==100);
 assert(amoled_display_idle_target(&s,49999,false)==30);
 assert(amoled_display_idle_target(&s,289999,false)==0);
 /* A timestamp sampled just before a concurrent new touch must not wrap
  * into a false 49-day idle period. */
 amoled_display_idle_init(&s,1000);
 amoled_display_idle_activity(&s,1001);
 assert(amoled_display_idle_target(&s,1000,false)==100);
 /* Never dim during an already-forwarded press or lose its release. */
 assert(!amoled_display_idle_touch(&s,true,2000));
 assert(amoled_display_idle_target(&s,400000,false)==100);
 assert(!amoled_display_idle_touch(&s,false,400001));
 assert(amoled_display_idle_target(&s,400002,false)==100);
 /* Failed wake keeps all later touches blocked until brightness succeeds. */
 amoled_display_idle_applied(&s,0);
 assert(amoled_display_idle_touch(&s,true,500000));
 assert(amoled_display_idle_touch(&s,false,500001));
 assert(amoled_display_idle_touch(&s,true,500002));
 amoled_display_idle_applied(&s,100);
 assert(amoled_display_idle_touch(&s,false,500003));
 assert(!amoled_display_idle_touch(&s,true,500004));
 assert(!amoled_display_idle_touch(&s,false,500005));
 /* Once dark, remain dark even across weeks and timer wrap; only actual
  * interaction/OTA visibility may wake the panel. */
 amoled_display_idle_init(&s,0);
 amoled_display_idle_applied(&s,0);
 assert(amoled_display_idle_target(&s,UINT_MAX-2,false)==0);
 assert(amoled_display_idle_target(&s,5,false)==0);
 amoled_display_idle_activity(&s,6);
 assert(amoled_display_idle_target(&s,6,false)==100);
 return 0;
}
