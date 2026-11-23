#include "display_idle.h"
void amoled_display_idle_init(amoled_display_idle_t *s,uint32_t now){
 atomic_init(&s->last_activity_ms,now);atomic_init(&s->brightness,100);atomic_init(&s->touch_held,false);atomic_init(&s->off_latched,false);s->discard_touch=false;
}
void amoled_display_idle_activity(amoled_display_idle_t *s,uint32_t now){atomic_store(&s->last_activity_ms,now);atomic_store(&s->off_latched,false);}
int amoled_display_idle_target(const amoled_display_idle_t *s,uint32_t now,bool keep_visible){
 if(keep_visible||atomic_load(&s->touch_held))return 100;
 if(atomic_load(&s->off_latched))return 0;
 uint32_t idle=now-atomic_load(&s->last_activity_ms);
 /* A concurrent touch can be one tick newer than the caller's time sample. */
 if(idle>INT32_MAX)idle=0;
 return idle>=300000?0:idle>=60000?30:100;
}
void amoled_display_idle_applied(amoled_display_idle_t *s,int brightness){atomic_store(&s->brightness,brightness);if(brightness==0)atomic_store(&s->off_latched,true);}
bool amoled_display_idle_touch(amoled_display_idle_t *s,bool pressed,uint32_t now){
 bool was_held=atomic_exchange(&s->touch_held,pressed);
 if(pressed){
  if(atomic_load(&s->brightness)<100)s->discard_touch=true;
  amoled_display_idle_activity(s,now);
 }
 if(!pressed&&was_held)amoled_display_idle_activity(s,now);
 bool discard=s->discard_touch;
 if(!pressed)s->discard_touch=false;
 return discard;
}
