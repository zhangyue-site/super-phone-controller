package org.example.phonecontroller;
import java.util.*;
public class DiagnosticBurstTest {
 public static void main(String[] args){
 Map<String,Object> m=new LinkedHashMap<>();m.put("event","source_burst");m.put("phase","frame");m.put("reason","restored");m.put("switches",12);m.put("acquired_candidates",10);m.put("ticket","must-not-survive");m.put("scope","must-not-survive");
 Map<String,Object> safe=DiagnosticSchema.sanitize(m);
 if(safe.size()!=5||!safe.get("event").equals("source_burst")||!safe.get("switches").equals(12L))throw new AssertionError();
 m.put("reason","arbitrary-secret");m.put("switches","secret");safe=DiagnosticSchema.sanitize(m);
 if(safe.containsKey("reason")||safe.containsKey("switches")||safe.containsKey("ticket")||safe.containsKey("scope"))throw new AssertionError();
 System.out.println("PASS: burst counters survive; unknown secrets and unapproved values remain excluded");
 }
}
