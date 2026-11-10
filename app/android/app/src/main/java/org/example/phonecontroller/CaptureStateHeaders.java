package org.example.phonecontroller;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Optional observations only; absent readings must never imply an unlocked screen. */
public final class CaptureStateHeaders {
 private CaptureStateHeaders(){}
 public interface Reader {
  boolean interactive();
  boolean keyguardLocked();
 }
 public static Map<String,String> headers(Boolean interactive,Boolean keyguardLocked){
  if(interactive==null||keyguardLocked==null)return Collections.emptyMap();
  Map<String,String> result=new LinkedHashMap<>();
  result.put("X-Screen-Interactive",interactive?"1":"0");
  result.put("X-Screen-Keyguard-Locked",keyguardLocked?"1":"0");
  return Collections.unmodifiableMap(result);
 }
 public static Map<String,String> sample(Reader reader){
  try{return headers(reader.interactive(),reader.keyguardLocked());}
  catch(RuntimeException unavailable){return Collections.emptyMap();}
 }
 /** Caller configures the existing URL, authorization and transport timeouts. */
 public static void send(HttpURLConnection connection,Reader reader) throws IOException {
  connection.setRequestMethod("POST");connection.setDoOutput(true);
  for(Map.Entry<String,String> header:sample(reader).entrySet()){
   connection.setRequestProperty(header.getKey(),header.getValue());
  }
  connection.setFixedLengthStreamingMode(0);
  connection.getOutputStream().close();
 }
}
