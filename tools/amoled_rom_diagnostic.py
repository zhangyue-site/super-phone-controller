"""Physical ROM I/O only; retained evidence is decoded on cloud."""
import argparse,time,json,serial
from serial.tools import list_ports
from esptool.targets.esp32s3 import ESP32S3ROM
ap=argparse.ArgumentParser();ap.add_argument('--device',required=True);ap.add_argument('--output',required=True);ap.add_argument('--bytes',type=int,default=4112);a=ap.parse_args()
norm=lambda s:(s or '').replace(':','').upper()
end=time.monotonic()+40
while time.monotonic()<end:
 ps=[p for p in list_ports.comports() if p.vid==0x303a and p.pid==0x1001 and norm(p.serial_number)==norm(a.device)]
 if len(ps)==1:
  s=serial.Serial(port=None,baudrate=115200,timeout=.3,write_timeout=.5);s.dtr=False;s.rts=False;s.port=ps[0].device;s.open()
  try:
   e=ESP32S3ROM(s);e.connect(mode='usb-reset',attempts=1,warnings=False)
   assert bytes(e.read_mac()).hex().upper()==norm(a.device)
   words=[e.read_reg(0x50000000+i) for i in range(0,a.bytes,4)]
   with open(a.output,'w') as f:json.dump({'base':0x50000000,'words':words},f)
   print('diagnostic_complete',True);break
  except Exception as x:print(type(x).__name__)
  finally:s.close()
 time.sleep(.5)
else:raise SystemExit('ROM diagnostic timed out')
