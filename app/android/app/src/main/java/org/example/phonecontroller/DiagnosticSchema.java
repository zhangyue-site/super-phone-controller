package org.example.phonecontroller;
import java.util.*;
/** Strict output schema: neither unknown keys nor arbitrary string values survive. */
public final class DiagnosticSchema {
 private static final Set<String> EVENTS=new HashSet<>(Arrays.asList("target_release","relay_attached","relay_action","relay_ack","relay_close","relay_disconnect","control_grant","control_refresh","control_http_failure","usb_expect","usb_attach","usb_revoke","capture_stop","capture_pause","capture_destroy","capture_task_removed","capture_frame_stats"));
 private static final Set<String> PHASES=new HashSet<>(Arrays.asList("attach","poll","maintenance","mode","write","read","ack","detach","shutdown","challenge","authorize","renew","pair-redeem","pair-renew","pair-issue","pair-revoke","screen-renew","command","usb","capture","frame","status","unknown"));
 private static final Set<String> REASONS=new HashSet<>(Arrays.asList("usb_unavailable","capture_inactive","error","explicit","opcode_stop","owner_shutdown","already_pending","already_at_mode","device_invalid","mode_begin","mode_attach_accepted","mode_attach_mismatch","mode_timeout","physical_detach","unexpected_attach","board_replaced","user_stop","flutter_stop","system_stop","geometry_change","task_removed","destroy","cloud_auth","surface_error","renew_begin","renew_ok","renew_fail","grant_ok","http_error","disconnect_done","none"));
 private static final Set<String> ERRORS=new HashSet<>(Arrays.asList("TimeoutException","StateError","FormatException","ControlHttpFailure","PlatformException","ClientException","Unknown","None"));
 public static Map<String,Object> sanitize(Map<?,?> raw){
  Map<String,Object> out=new LinkedHashMap<>();
  if(!EVENTS.contains(raw.get("event")))return out;
  out.put("event",raw.get("event"));
  for(String key:Arrays.asList("phase","reason","error_type")){
   Object value=raw.get(key);Set<String> allowed=key.equals("phase")?PHASES:key.equals("reason")?REASONS:ERRORS;
   if(allowed.contains(value))out.put(key,value);
  }
  for(String key:Arrays.asList("op","seq","last_op","last_seq","http_status","generation","pid","expected_pid","remaining_ms","source_frames","eligible_frames","old_frames","jpeg_reused","upload_ok","upload_wait","upload_error","source_age_ms","eligible_age_ms","upload_ms","refresh_begin","refresh_ok","refresh_cancel","refresh_error","source_callbacks","callback_age_ms","deferred_callbacks","status_errors","status_age_ms")){
   Object value=raw.get(key);if(!(value instanceof Integer||value instanceof Long))continue;
   long number=((Number)value).longValue();
   if(key.equals("http_status")&&(number<100||number>599))continue;
   if(number>=-600000L&&number<=0xffffffffL)out.put(key,number);
  }
  Object state=raw.get("capture_state");if(Arrays.asList("idle","thinking","running","planning","plan","verifying","capturing","done","error","stopped","unknown").contains(state))out.put("capture_state",state);
  for(String key:Arrays.asList("mode_pending","active","running","sampling_enabled","demand","cloud_paused","status_worker_alive","frame_worker_busy","keyguard_locked","interactive","has_status_barrier"))if(raw.get(key) instanceof Boolean)out.put(key,raw.get(key));
  return out;
 }
}
