"""Read cached and wire USB descriptors of an explicitly identified controller.
No interface claiming, detaching, reset, or flash writes are performed.
"""
import ctypes as C
import argparse,json,time
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--library',required=True);ap.add_argument('--device',required=True);ap.add_argument('--seconds',type=int,default=15);ap.add_argument('--output',required=True);a=ap.parse_args()
class Desc(C.Structure):
 _pack_=1
 _fields_=[('length',C.c_uint8),('type',C.c_uint8),('usb',C.c_uint16),('device_class',C.c_uint8),('subclass',C.c_uint8),('protocol',C.c_uint8),('packet',C.c_uint8),('vid',C.c_uint16),('pid',C.c_uint16),('version',C.c_uint16),('manufacturer',C.c_uint8),('product',C.c_uint8),('serial',C.c_uint8),('configs',C.c_uint8)]
lib=C.CDLL(a.library)
lib.libusb_init.argtypes=[C.POINTER(C.c_void_p)];lib.libusb_init.restype=C.c_int
lib.libusb_exit.argtypes=[C.c_void_p]
lib.libusb_get_device_list.argtypes=[C.c_void_p,C.POINTER(C.POINTER(C.c_void_p))];lib.libusb_get_device_list.restype=C.c_ssize_t
lib.libusb_free_device_list.argtypes=[C.POINTER(C.c_void_p),C.c_int]
lib.libusb_get_device_descriptor.argtypes=[C.c_void_p,C.POINTER(Desc)];lib.libusb_get_device_descriptor.restype=C.c_int
lib.libusb_open.argtypes=[C.c_void_p,C.POINTER(C.c_void_p)];lib.libusb_open.restype=C.c_int
lib.libusb_close.argtypes=[C.c_void_p]
lib.libusb_get_string_descriptor_ascii.argtypes=[C.c_void_p,C.c_uint8,C.POINTER(C.c_ubyte),C.c_int];lib.libusb_get_string_descriptor_ascii.restype=C.c_int
lib.libusb_control_transfer.argtypes=[C.c_void_p,C.c_uint8,C.c_uint8,C.c_uint16,C.c_uint16,C.POINTER(C.c_ubyte),C.c_uint16,C.c_uint];lib.libusb_control_transfer.restype=C.c_int
ctx=C.c_void_p();assert lib.libusb_init(C.byref(ctx))==0
end=time.monotonic()+a.seconds;events=[];seen=set()
try:
 while time.monotonic()<end:
  devices=C.POINTER(C.c_void_p)();count=lib.libusb_get_device_list(ctx,C.byref(devices))
  if count<0:
   events.append({"list_error":count});break
  try:
   for i in range(count):
    desc=Desc()
    if lib.libusb_get_device_descriptor(devices[i],C.byref(desc)) or desc.vid!=0x303a:continue
    handle=C.c_void_p();err=lib.libusb_open(devices[i],C.byref(handle))
    if err:
     e={'cached_pid':desc.pid,'open_error':err}
    else:
     try:
      buf=(C.c_ubyte*256)();n=lib.libusb_get_string_descriptor_ascii(handle,desc.serial,buf,256)
      serial=bytes(buf[:max(0,n)]).decode(errors='replace')
      if serial.upper().replace(':','')!=a.device.upper().replace(':',''):continue
      wire=(C.c_ubyte*18)();n=lib.libusb_control_transfer(handle,0x80,6,0x0100,0,wire,18,150)
      e={'serial':serial,'cached_vid':desc.vid,'cached_pid':desc.pid,'wire_read':n}
      if n==18:
       w=Desc.from_buffer_copy(bytes(wire));e.update(wire_vid=w.vid,wire_pid=w.pid,wire_class=w.device_class)
     finally:lib.libusb_close(handle)
    key=json.dumps(e,sort_keys=True)
    if key not in seen:seen.add(key);events.append(e);print(e,flush=True)
  finally:
   if devices:lib.libusb_free_device_list(devices,1)
  time.sleep(.05)
finally:lib.libusb_exit(ctx)
Path(a.output).write_text(json.dumps({'target':a.device,'events':events,'read_only':True},indent=2));print('probe complete',len(events),flush=True)
