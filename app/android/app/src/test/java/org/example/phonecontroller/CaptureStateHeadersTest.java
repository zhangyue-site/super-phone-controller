package org.example.phonecontroller;
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.nio.file.Path;
import java.util.Map;

/** Pure JVM contract: optional observations never change a status POST into input. */
public final class CaptureStateHeadersTest {
 private static void check(boolean value){if(!value)throw new AssertionError();}
 private static final class Connection extends HttpURLConnection {
  final ByteArrayOutputStream body=new ByteArrayOutputStream();
  int length=-1;boolean outputRequested;
  Connection() throws Exception {super(new URL("https://controller.test/app-screen/status"));}
  @Override public void setFixedLengthStreamingMode(int value){check(!outputRequested);length=value;}
  @Override public OutputStream getOutputStream(){check(!outputRequested);outputRequested=true;return body;}
  @Override public void connect(){}
  @Override public void disconnect(){}
  @Override public boolean usingProxy(){return false;}
 }
 private static CaptureStateHeaders.Reader reader(boolean interactive,boolean locked){
  return new CaptureStateHeaders.Reader(){
   public boolean interactive(){return interactive;}
   public boolean keyguardLocked(){return locked;}
  };
 }
 private static void emptyPost(Connection c) throws Exception {
  check(c.getRequestMethod().equals("POST"));check(c.getDoOutput());
  check(c.length==0&&c.outputRequested&&c.body.size()==0);
  check(c.getRequestProperty("Authorization").equals("Bearer test-only"));
 }
 public static void main(String[] args) throws Exception {
  for(boolean interactive:new boolean[]{false,true})for(boolean locked:new boolean[]{false,true}){
   Connection c=new Connection();c.setRequestProperty("Authorization","Bearer test-only");
   CaptureStateHeaders.send(c,reader(interactive,locked),new byte[0]);emptyPost(c);
   check(c.getRequestProperty("X-Screen-Interactive").equals(interactive?"1":"0"));
   check(c.getRequestProperty("X-Screen-Keyguard-Locked").equals(locked?"1":"0"));
   check(c.getRequestProperties().size()==4);
  }
  check(CaptureStateHeaders.headers(null,true).isEmpty());
  check(CaptureStateHeaders.headers(false,null).isEmpty());
  check(CaptureStateHeaders.headers(null,null).isEmpty());
  for(int failure:new int[]{0,1}){
   final int failAt=failure;Connection c=new Connection();c.setRequestProperty("Authorization","Bearer test-only");
   CaptureStateHeaders.send(c,new CaptureStateHeaders.Reader(){
    public boolean interactive(){if(failAt==0)throw new SecurityException("unavailable");return true;}
    public boolean keyguardLocked(){throw new IllegalStateException("unavailable");}
   },new byte[0]);
   emptyPost(c);check(c.getRequestProperty("X-Screen-Interactive")==null);
   check(c.getRequestProperty("X-Screen-Keyguard-Locked")==null);
   check(c.getRequestProperties().size()==2);
  }
  byte[] json="{\"results\":[\"文字\"]}".getBytes(StandardCharsets.UTF_8);
  Connection post=new Connection();
  CaptureStateHeaders.send(post,reader(true,false),json);
  check(post.getRequestProperty("Content-Type").equals("application/json"));
  check(post.length==json.length&&Arrays.equals(post.body.toByteArray(),json));
  Map<String,String> first=CaptureStateHeaders.sample(reader(true,false));
  Map<String,String> second=CaptureStateHeaders.sample(reader(false,true));
  check(first.get("X-Screen-Interactive").equals("1"));
  check(second.get("X-Screen-Interactive").equals("0"));
  check(second.get("X-Screen-Keyguard-Locked").equals("1"));
  String service=Files.readString(Path.of(args.length==0?"android/app/src/main/kotlin/org/example/phonecontroller/ScreenShareService.kt":args[0]));
  String poll=service.substring(service.indexOf(" private val poll=object: Runnable"),service.indexOf(" @Volatile private var supportsAccessibilityFrames"));
  check(poll.contains("CaptureStateHeaders.send(c,captureStateHeadersReader(),body)"));
  String readerFactory=service.substring(service.indexOf(" private fun captureStateHeadersReader()"),service.indexOf(" private fun recordSnapshot()"));
  check(readerFactory.contains("val service=this"));
  check(readerFactory.contains("override fun interactive()=service.interactive()"));
  check(readerFactory.contains("override fun keyguardLocked()=service.locked()"));
  check(service.indexOf("CaptureStateHeaders.send(")==service.lastIndexOf("CaptureStateHeaders.send("));
  check(!poll.contains("hid_pointer")&&!poll.contains("dispatchGesture")&&!poll.contains("injectInputEvent"));
  System.out.println("Capture status headers: fresh boolean values, omission on read failure, authenticated empty and JSON POST, status-only native wiring, no input: passed");
 }
}
