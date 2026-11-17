package org.example.phonecontroller;
import java.util.*;
public final class DiagnosticSchemaTest {
 static void check(boolean v){if(!v)throw new AssertionError();}
 public static void main(String[]args){
  Map<String,Object> raw=new HashMap<>();raw.put("event","relay_close");raw.put("phase","poll");raw.put("reason","error");raw.put("error_type","ControlHttpFailure");raw.put("http_status",403);
  for(String key:Arrays.asList("ticket","nonce","packet","body","message","uri","serial","wall_ms"))raw.put(key,"SENSITIVE-TEST-VALUE");
  Map<String,Object> safe=DiagnosticSchema.sanitize(raw);
  check(safe.size()==5);check(!safe.toString().contains("SENSITIVE"));check(safe.get("http_status").equals(403L));
  raw.put("phase","SENSITIVE-TEST-VALUE");raw.put("reason","not-a-fixed-reason");raw.put("http_status",999);raw.put("generation","not-a-number");safe=DiagnosticSchema.sanitize(raw);
  check(!safe.containsKey("phase")&&!safe.containsKey("reason")&&!safe.containsKey("http_status")&&!safe.containsKey("generation"));
  raw.put("event","arbitrary-user-text");check(DiagnosticSchema.sanitize(raw).isEmpty());
  raw.clear();raw.put("event","capture_task_removed");raw.put("phase","capture");raw.put("reason","task_removed");raw.put("active",true);raw.put("running",true);raw.put("intent","SENSITIVE-INTENT");
  safe=DiagnosticSchema.sanitize(raw);check(safe.size()==5);check(safe.get("reason").equals("task_removed"));check(!safe.toString().contains("SENSITIVE"));
  raw.clear();raw.put("event","capture_frame_stats");raw.put("source_frames",12L);raw.put("eligible_frames",7L);raw.put("old_frames",5L);raw.put("upload_ok",3L);raw.put("upload_wait",2L);raw.put("upload_error",1L);raw.put("source_age_ms",1200L);raw.put("eligible_age_ms",-1L);raw.put("upload_ms",210L);raw.put("refresh_begin",2L);raw.put("refresh_ok",1L);raw.put("refresh_cancel",1L);raw.put("refresh_error",0L);raw.put("sampling_enabled",false);raw.put("demand",true);raw.put("node_text","SENSITIVE");
  safe=DiagnosticSchema.sanitize(raw);check(safe.size()==16);check(safe.get("source_frames").equals(12L));check(!safe.toString().contains("SENSITIVE"));
  raw.clear();raw.put("event","local_stability");raw.put("phase","frame");raw.put("reason","request_end");raw.put("observed_frames",15L);raw.put("rejected_frames",1L);raw.put("gap_resets",1L);raw.put("change_resets",1L);raw.put("max_gap_ms",300L);raw.put("best_count",10);raw.put("best_stable_ms",720L);raw.put("watch_ms",8000L);raw.put("reports_sent",4);raw.put("reports_ready",1);raw.put("reports_dropped",2);raw.put("ready",true);raw.put("burst_enabled",true);
  for(String key:Arrays.asList("id","label","bounds","barrier","scope"))raw.put(key,"SENSITIVE-TEST-VALUE");
  safe=DiagnosticSchema.sanitize(raw);check(safe.size()==16);check(safe.get("best_count").equals(10L)&&safe.get("ready").equals(true));check(!safe.toString().contains("SENSITIVE"));
  for(String reason:Arrays.asList("request_begin","request_end","watch_cleared","status_barrier_mismatch","request_barrier_mismatch","request_geometry_mismatch","request_frames_mismatch","request_region_invalid","burst_already_attempted","burst_unauthorized","burst_reader_swap","burst_budget_exhausted")){raw.put("reason",reason);check(reason.equals(DiagnosticSchema.sanitize(raw).get("reason")));}
  raw.put("reason","req-0123456789abcdef");check(!DiagnosticSchema.sanitize(raw).containsKey("reason"));
  System.out.println("Diagnostic schema rejects secrets and arbitrary text: passed");
 }
}
