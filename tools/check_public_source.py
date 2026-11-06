"""Reject private operational data in the public snapshot (not a history eraser)."""
from pathlib import Path
import re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def check():
 bad=[]
 names=subprocess.check_output(["git","-C",str(ROOT),"ls-files","-z"]).decode().split("\0")
 for name in filter(None,names):
  p=ROOT/name
  if not p.is_file():continue
  raw=p.read_bytes()
  if name.startswith(("private-","docs/handoff")) or p.suffix in (".jks",".keystore",".apk",".mp4"):bad.append((name,"private artifact"))
  if b"\0" in raw:continue
  if re.search(rb"/Users/[A-Za-z][A-Za-z0-9_.-]+",raw):bad.append((name,"personal home path"))
  if re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",raw):bad.append((name,"private key"))
  text=raw.decode(errors="replace")
  for value in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",text):
   if value.endswith((".png",".jpg",".invalid")):continue
   if name.startswith(("tests/","integrations/")) and value.endswith("@im.wechat"):continue
   bad.append((name,"email contact"))
 for name,kind in sorted(set(bad)):print(name+": "+kind)
 return not bad
if __name__=="__main__":
 ok=check()
 print("public-source privacy check: "+("PASS" if ok else "FAIL"))
 sys.exit(0 if ok else 1)
