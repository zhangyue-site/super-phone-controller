package org.example.phonecontroller;
public final class TaskWakePolicyTest {
 public static void main(String[] args) {
  TaskWakePolicy p=new TaskWakePolicy();String task="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  assert p.request("capture-a",task,"queued",true,false,true);
  assert !p.request("capture-a",task,"running",true,false,true);
  assert !p.request("capture-a","bad","running",true,false,true);
  assert !p.request("capture-a","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","done",true,false,true);
  assert !p.request("capture-a","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","running",false,false,true);
  assert !p.request("capture-a","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","running",true,true,false);
  assert p.request("capture-a","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","running",true,true,true);
  System.out.println("TaskWakePolicy: 7 assertions passed");
 }
}
