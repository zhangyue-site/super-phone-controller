"""Reject ROM collisions for every exported application USB operation."""
import re,sys
from pathlib import Path
header=Path(__file__).resolve().parents[1]/'firmware-amoled/main/usb.h'
expected=set(re.findall(r'\b(amoled_usb_\w+)\(',header.read_text()))
symbols={}
for line in Path(sys.argv[1]).read_text().splitlines():
 fields=line.split()
 if len(fields)==3:
  try:symbols[fields[2]]=(int(fields[0],16),fields[1])
  except ValueError:pass
assert expected
for name in expected:
 address,kind=symbols[name]
 assert kind in ('T','t') and (0x40370000<=address<0x40400000 or 0x42000000<=address<0x44000000),(name,hex(address),kind)
for name in ('usb_read','usb_write'):
 # These ESP32-S3 ROM names may exist as absolute symbols, never app code.
 assert name not in symbols or symbols[name][1]=='A',(name,symbols.get(name))
print('Verified application USB symbols:',len(expected))
