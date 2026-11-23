"""Convert existing dsh-pet idle WebP frames to fixed transformable LVGL ARGB8888 flash images."""
from pathlib import Path
import argparse,json,hashlib
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('idle_dir',type=Path);p.add_argument('output_dir',type=Path);a=p.parse_args()
a.output_dir.mkdir(parents=True,exist_ok=True);frames=[];provenance=[]
for n in range(8):
 source=a.idle_dir/f'f{n*3:03}.webp';im=Image.open(source).convert('RGBA').crop((170,45,370,285)).resize((200,240),Image.Resampling.LANCZOS)
 im.putalpha(im.getchannel('A').point(lambda v:0 if v<16 else v));im.save(a.output_dir/f'idle-{n}.png')
 q=im.quantize(colors=128,method=Image.Quantize.FASTOCTREE);palette=q.getpalette('RGBA');palette += [0]*(1024-len(palette));data=bytearray()
 for i in range(256):
  rr,gg,bb,aa=palette[4*i:4*i+4];data.extend((bb,gg,rr,aa))
 palette_bgra=bytes(data);data=bytearray()
 for index in q.tobytes():data.extend(palette_bgra[index*4:index*4+4])
 frames.append(bytes(data));provenance.append({'file':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
(a.output_dir/'pet_assets.h').write_text('#pragma once\n#include "lvgl.h"\nextern const lv_image_dsc_t companion_pet[8];\n')
s='#include "pet_assets.h"\n'
for i,data in enumerate(frames):s+=f'static const uint8_t frame_{i}[]={{'+','.join(map(str,data))+'};\n'
s+='const lv_image_dsc_t companion_pet[8]={\n'
for i,data in enumerate(frames):s+='{.header={.magic=LV_IMAGE_HEADER_MAGIC,.cf=LV_COLOR_FORMAT_ARGB8888,.w=200,.h=240,.stride=800},.data_size='+str(len(data))+',.data=frame_'+str(i)+'},\n'
s+='};\n';(a.output_dir/'pet_assets.c').write_text(s)
(a.output_dir/'frames.json').write_text(json.dumps(provenance,indent=2))
print('8 frames; max 4 fps; flash bytes',sum(map(len,frames)))
