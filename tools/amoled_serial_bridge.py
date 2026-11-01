"""Loopback-only transport for cloud tests of one explicit USB controller.
The bridge forwards bytes only; protocol tests and artifacts stay on the cloud.
"""
import argparse,json,selectors,socket,signal
import serial
from serial.tools import list_ports
ap=argparse.ArgumentParser();ap.add_argument('--device',required=True);ap.add_argument('--port',type=int,default=19424);a=ap.parse_args()
def norm(s):return (s or '').upper().replace(':','')
def stop(signum,frame):raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',a.port));server.listen(1)
print('Loopback bridge ready for explicit target',a.device,flush=True)
while True:
 conn,_=server.accept();s=None
 try:
  ps=[p for p in list_ports.comports() if p.vid==0x303a and p.pid==0x4005 and norm(p.serial_number)==norm(a.device)]
  if len(ps)!=1:
   conn.sendall(b'{"bridge_error":"target unavailable"}\n');continue
  s=serial.Serial(port=None,baudrate=115200,timeout=0,write_timeout=3);s.dtr=False;s.rts=False;s.port=ps[0].device;s.open();s.reset_input_buffer()
  conn.sendall((json.dumps({'bridge_target':a.device,'port':ps[0].device,'pid':ps[0].pid})+'\n').encode())
  with selectors.DefaultSelector() as sel:
   sel.register(conn,selectors.EVENT_READ,'socket');sel.register(s.fileno(),selectors.EVENT_READ,'serial')
   done=False
   while not done:
    for key,_ in sel.select(timeout=2):
     if key.data=='socket':
      data=conn.recv(8192)
      if not data:done=True;break
      s.write(data)
     else:
      data=s.read(max(1,min(s.in_waiting,8192)))
      if data:conn.sendall(data)
 except (OSError,serial.SerialException) as e:print(type(e).__name__,flush=True)
 finally:
  if s is not None:s.close()
  conn.close()
