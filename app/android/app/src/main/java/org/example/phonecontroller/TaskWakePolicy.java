package org.example.phonecontroller;
/** Only a fresh authenticated task and a live capture may request one wake. */
public final class TaskWakePolicy {
 private String attempted="";
 public synchronized boolean request(String scope,String id,String state,boolean capture,boolean interactive,boolean locked) {
  if(!capture || scope==null || scope.isEmpty() || id==null || !id.matches("[0-9a-f]{32}") || !("queued".equals(state)||"running".equals(state)) || interactive&&!locked)return false;
  String key=scope+":"+id;
  if(key.equals(attempted))return false;
  attempted=key;return true;
 }
}
