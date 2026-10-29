#!/usr/bin/env python3
"""Generate five static 200x200 1bpp power states; no countdown repaint loop."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import sys
font='/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
states=[('松开关机',['继续按住30秒重启','升级完成后才会执行']),('正在停止任务',['等待升级安全结束','请勿拔电']),('等待升级完成',['正在提交固件','暂不关机或重启']),('已停止运行',['USB供电时保留维护','再按电源键重新启动']),('暂时无法执行',['升级未能安全结束','保留维护，请稍后重试'])]
frames=[]
for title,lines in states:
 im=Image.new('1',(200,200),1);d=ImageDraw.Draw(im)
 for text,y,size in [(title,38,22),(lines[0],94,16),(lines[1],126,15)]:
  f=ImageFont.truetype(font,size);box=d.textbbox((0,0),text,font=f);d.text(((200-(box[2]-box[0]))//2,y),text,font=f,fill=0)
 frames.append(im.tobytes())
out=Path(sys.argv[1]);out.write_text('#pragma once\n#include <stdint.h>\nstatic const uint8_t power_screens[5][5000]={\n'+',\n'.join('{'+','.join(str(v) for v in b)+'}' for b in frames)+'\n};\n')
