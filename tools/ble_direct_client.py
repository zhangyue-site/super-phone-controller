#!/usr/bin/env python3
"""Owner-maintenance BLE HID client; no device token is exported or stored locally."""
import argparse,asyncio,hashlib,hmac,json,re,shlex,struct,subprocess,time,sys
from bleak import BleakClient,BleakScanner
LOCAL='6f6f7461-2d6f-7461-0000-000000000008'
INFO='6f6f7461-2d6f-7461-0000-000000000004'
SIGNER_CODE=r'''
import ast,hashlib,hmac,json,re,sys
from pathlib import Path
v=json.load(sys.stdin)
assert re.fullmatch('[0-9a-f]{32}',v['nonce']) and v['device']=='epaper-01'
s=Path('/srv/phone-controller/tools/ble_direct_client.py').read_text()
m=re.search(r'^\s*#define\s+DISPLAY_TOKEN\s+("(?:[^"\\]|\\.)*")',s,re.M);assert m
key=ast.literal_eval(m.group(1)).encode()
print(hmac.new(key,('PCBLE1\n'+v['device']+'\n'+v['nonce']).encode(),hashlib.sha256).hexdigest())
'''
def derive(signer,device,nonce):
 r=subprocess.run(['ssh',signer,'python3 -c '+shlex.quote(SIGNER_CODE)],input=json.dumps({'device':device,'nonce':nonce}),text=True,capture_output=True,timeout=15)
 value=r.stdout.strip()
 if r.returncode or not re.fullmatch('[0-9a-f]{64}',value):raise RuntimeError('Session signer failed; no credential printed')
 return bytes.fromhex(value)
def packet(op,seq,key,args=(0,0,0,0,0)):
 body=struct.pack('<BBI5H',1,op,seq,*args)
 return body+hmac.new(key,body,hashlib.sha256).digest()
class Link:
 def __init__(self,client,signer):self.c=client;self.signer=signer;self.seq=0
 async def start(self):
  info=json.loads(bytes(await self.c.read_gatt_char(INFO)));raw=json.loads(bytes(await self.c.read_gatt_char(LOCAL)))
  if info.get('device')!='epaper-01' or not re.fullmatch('[0-9a-f]{32}',raw.get('nonce','')):raise RuntimeError('Unexpected board identity')
  self.nonce=raw['nonce'];self.key=derive(self.signer,info['device'],self.nonce);await self.read()
  print(json.dumps({'connected':True,'device':info['device'],'version':info['version'],'protocol':'local-hid-v1'}),flush=True)
 async def read(self):
  d=json.loads(bytes(await self.c.read_gatt_char(LOCAL)))
  if d.get('nonce')!=self.nonce:raise RuntimeError('Session changed; reconnect required')
  message='PCBLE1-ACK\n%s\n%d\n%d\n%d\n%d\n%d\n%d'%(d['nonce'],d['seq'],d['op'],d['result'],d['hid'],d['busy'],d['ready'])
  if not hmac.compare_digest(d.get('proof',''),hmac.new(self.key,message.encode(),hashlib.sha256).hexdigest()):raise RuntimeError('Invalid board receipt signature')
  return {k:v for k,v in d.items() if k not in ('proof','nonce')}
 async def send(self,op,args=(0,0,0,0,0)):
  # Validate locally before consuming a sequence or issuing an ATT write.
  if type(op)!=int or op not in range(1,8) or not isinstance(args,(tuple,list)) or len(args)!=5 or any(type(v)!=int for v in args):raise ValueError('Invalid local HID command')
  if op==3:
   valid=all(0<=v<=32767 for v in args[:2]) and tuple(args[2:])==(0,0,0)
  elif op==4:valid=all(0<=v<=32767 for v in args[:4]) and 100<=args[4]<=1200
  else:valid=tuple(args)==(0,0,0,0,0)
  if not valid or self.seq>=0xffffffff:raise ValueError('Invalid local HID parameters or exhausted session')
  self.seq+=1;wire=packet(op,self.seq,self.key,args)
  await self.c.write_gatt_char(LOCAL,wire,response=True)
  until=time.monotonic()+10
  while time.monotonic()<until:
   d=await self.read()
   if d['seq']==self.seq:
    if d['op']!=op:raise RuntimeError('Receipt operation mismatch; action is not retried')
    if not d['busy'] and d['result'] not in (1,2):return d,wire
   await asyncio.sleep(.1)
  raise RuntimeError('No execution receipt; action is not retried')
 async def command(self,op,args=(0,0,0,0,0)):
  d,_=await self.send(op,args)
  expected={1:3,2:3,3:3,4:3,5:5,6:7,7:8}[op]
  if d['result']!=expected:raise RuntimeError('Board rejected or cancelled command (result=%s); action is not retried'%d['result'])
  if op in (6,7):return await self.hid(1 if op==6 else 0)
  return d
 async def reject(self,wire):
  before=await self.read()
  try:await self.c.write_gatt_char(LOCAL,wire,response=True)
  except Exception:pass
  else:raise AssertionError('Invalid request unexpectedly accepted')
  after=await self.read();assert after['seq']==before['seq'];return True
 async def hid(self,value):
  until=time.monotonic()+10
  while time.monotonic()<until:
   d=await self.read()
   if d['hid']==value and d['ready']:return d
   await asyncio.sleep(.2)
  raise AssertionError('USB mode did not settle')
async def main(a):
 device=await BleakScanner.find_device_by_address(a.address,timeout=12)
 if device is None:raise RuntimeError('Target board not found')
 async with BleakClient(device,timeout=15) as c:
  if not any(ch.uuid==LOCAL for s in c.services for ch in s.characteristics):raise RuntimeError('Firmware lacks local BLE control')
  link=Link(c,a.signer);await link.start()
  if a.op=='selftest':
   initial=await link.read();assert initial['hid']==0,'Safe selftest requires HID initially off'
   wrong=packet(1,1,b'wrong-key');await link.reject(wrong);print('PASS wrong signature rejected',flush=True)
   await link.reject(packet(3,1,link.key,(65535,1,0,0,0)));print('PASS malformed coordinate rejected',flush=True)
   denied,wire=await link.send(1);assert denied['result']==4 and denied['hid']==0;print('PASS unarmed action denied',flush=True)
   await link.reject(wire);print('PASS replay rejected',flush=True)
   armed,_=await link.send(6);assert armed['result']==7;await link.hid(1);print('PASS authenticated HID arm; no input action sent',flush=True)
   disarmed,_=await link.send(7);assert disarmed['result']==8;await link.hid(0);print('PASS authenticated HID disarm',flush=True)
   stopped,_=await link.send(5);assert stopped['result']==5;await link.reject(packet(6,link.seq+1,link.key));print('PASS STOP revokes session',flush=True)
  elif a.op=='shell':
   print('READY: one JSON command per line; EOF disconnects and releases HID',flush=True)
   while True:
    line=await asyncio.to_thread(sys.stdin.readline)
    if not line:break
    command=json.loads(line);name=command['op']
    if name=='info':print(json.dumps(await link.read()),flush=True);continue
    op={'home':1,'back':2,'click':3,'drag':4,'stop':5,'arm':6,'disarm':7}[name]
    values=command.get('coords',[0,0,0,0,0])
    if not isinstance(values,list) or len(values)!=5 or any(type(v)!=int or not 0<=v<=65535 for v in values):raise ValueError('Invalid coordinates')
    d=await link.command(op,tuple(values));print(json.dumps(d),flush=True)
    if name=='stop':break
  elif a.op=='info':print(json.dumps(await link.read()),flush=True)
  else:
   op={'home':1,'back':2,'click':3,'drag':4,'stop':5,'arm':6,'disarm':7}[a.op]
   if a.op in ('home','back','click','drag'):
    await link.command(6)
   d=await link.command(op,tuple(a.coords) if a.coords else (0,0,0,0,0));print(json.dumps(d),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('op',choices=['shell','info','selftest','arm','disarm','home','back','click','drag','stop']);p.add_argument('--address',required=True);p.add_argument('--signer',required=True);p.add_argument('--coords',type=int,nargs=5);a=p.parse_args();asyncio.run(main(a))
