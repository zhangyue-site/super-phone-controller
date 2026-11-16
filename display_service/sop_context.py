"""Non-coordinate appearance summaries for verified page preconditions."""
import io
from PIL import Image

def describe(raw):
 with Image.open(io.BytesIO(raw)) as im:
  w,h=im.size;body=im.convert("RGB").crop((0,int(h*.045),w,int(h*.95)))
  small=body.convert("L").resize((17,16));values=list(small.getdata());bits=0
  for y in range(16):
   for x in range(16):bits=(bits<<1)|int(values[y*17+x]>values[y*17+x+1])
  hist=[]
  for channel in body.resize((64,96)).split():
   bins=channel.histogram();hist.extend([sum(bins[i:i+32])/6144 for i in range(0,256,32)])
 return dict(v=1,width=w,height=h,hash=format(bits,"064x"),hist=[round(v,5) for v in hist])

def valid(d):
 return isinstance(d,dict) and set(d)=={"v","width","height","hash","hist"} and d["v"]==1 and type(d["width"])is int and type(d["height"])is int and 0<d["width"]<=4096 and 0<d["height"]<=4096 and isinstance(d["hash"],str) and len(d["hash"])==64 and all(c in "0123456789abcdef" for c in d["hash"]) and isinstance(d["hist"],list) and len(d["hist"])==24 and all(type(v)in (int,float) and 0<=v<=1 for v in d["hist"])

def same(a,b):
 if not valid(a) or not valid(b) or (a["width"],a["height"])!=(b["width"],b["height"]):return False
 return (int(a["hash"],16)^int(b["hash"],16)).bit_count()<=3 and max(abs(x-y) for x,y in zip(a["hist"],b["hist"]))<=.015
