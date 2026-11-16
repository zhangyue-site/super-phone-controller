"""Local current-frame slider facts only; no input, model or permission."""
import io,copy,statistics
from PIL import Image
def measure(raw,bounds,width,height):
 try:
  with Image.open(io.BytesIO(raw)) as source:
   if source.size!=(width,height):return None
   im=source.convert("RGB")
   l,t,r,b=bounds;dx,dy=r-l,b-t
   vertical=dy>=2*dx
   if not vertical and dx<2*dy:return None
   n=dy if vertical else dx;cross=dx if vertical else dy
   if n<30 or cross<6:return None
   fractions=(.2,.35,.5,.65,.8)
   profile=[]
   for a in range(n):
    pixels=[im.getpixel((l+min(dx-1,int(cross*f)),t+a) if vertical else(l+a,t+min(dy-1,int(cross*f))))for f in fractions]
    profile.append(tuple(statistics.median(p[c]for p in pixels)for c in range(3)))
   window=max(2,n//50);scores={}
   for i in range(max(window,int(n*.1)),min(n-window,int(n*.9))):
    left=[sum(profile[j][c]for j in range(i-window,i))/window for c in range(3)]
    right=[sum(profile[j][c]for j in range(i,i+window))/window for c in range(3)]
    scores[i]=sum(abs(a-b)for a,b in zip(left,right))
   peak=max(scores.values(),default=0)
   if peak<100:return None
   candidates=[i for i,s in scores.items()if s>=peak*.9]
   if not candidates or max(candidates)-min(candidates)>n*.1:return None
   boundary=statistics.median(candidates)
   value=100*(1-boundary/n)if vertical else 100*boundary/n
   return dict(observed_percent=round(value,1),observed_source="current_jpeg_pixel_boundary",axis="vertical"if vertical else"horizontal")
 except (OSError,ValueError,TypeError,IndexError,KeyError):return None
def annotate(raw,hint,out):
 out=copy.deepcopy(out)
 for row in out.get("widgets",[]):
  row.pop("observed_percent",None);row.pop("observed_source",None)
  if row.get("role")=="brightness_slider":
   facts=measure(raw,row["bounds"],hint["width"],hint["height"])
   if facts:row.update(facts)
 return out
