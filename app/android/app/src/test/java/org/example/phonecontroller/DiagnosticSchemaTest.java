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
  System.out.println("Diagnostic schema rejects secrets and arbitrary text: passed");
 }
}
