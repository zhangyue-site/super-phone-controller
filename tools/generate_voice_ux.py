from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import re
root=Path(__file__).resolve().parents[1];preview=root/'previews/voice-ux';preview.mkdir(parents=True,exist_ok=True)
font='/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
if not Path(font).exists():font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
def text(im,y,label,size=16,x=100):
 d=ImageDraw.Draw(im);f=ImageFont.truetype(font,size);w=d.textlength(label,font=f);assert w<=184,(label,w);d.text((x-w/2,y),label,font=f,fill=0)
def footer(im):
 d=ImageDraw.Draw(im);d.line((8,162,191,162),fill=0);d.line((100,162,100,186),fill=0);text(im,165,'首页',12,x=50);text(im,165,'停止',12,x=150)
def emit(name,frames):
 for i,im in enumerate(frames):footer(im);im.save(preview/f'{name}-{i}.png')
 return 'static const unsigned char '+name+f'[{len(frames)}][5000]={{'+','.join('{'+','.join(map(str,im.tobytes()))+'}' for im in frames)+'};'
homes=[]
for title in ('等待联网','已经联网','语音就绪','已停止'):
 im=Image.new('1',(200,200),1);d=ImageDraw.Draw(im);text(im,2,title,25);text(im,31,'松手识别 · 先看计划',12)
 for box,label in [((8,45,191,99),'按住说话'),((8,105,191,154),'控制手机')]:d.rectangle(box,outline=0,width=2);text(im,box[1]+8,label,26)
 homes.append(im)
rows=[('按住说话','松手后开始识别','长按A键 / 按住屏幕'),('正在录音','松手后开始识别','最长10秒'),('正在识别','已收好这段录音','识别后先显示计划'),('本轮完成','请核对手机与结果','按住A键可再说'),('准备录音','麦克风正在启动','显示录音后再说话'),('没有听清','请靠近麦克风重说','按住说话 · 松手识别'),('尚未联网','连接WiFi后再试','这次没有录到说话'),('正在连接','还没开始录音','连接好后请重新按住'),('可以说话','按住录音 松手识别','先看识别内容与计划'),('连接失败','检查网络后再说','这次没有录到说话'),('正在处理','识别后先显示计划','点停止可取消'),('正在播报','回答完成后可再说','点停止可取消'),('这次没录上','请按住至少半秒','看到录音计时再说话'),('连接中断','未能确认本轮结果','检查网络后再说')]
voices=[]
for i,(title,hint,detail) in enumerate(rows):
 im=Image.new('1',(200,200),1);text(im,14,title,28)
 if i==1:
  text(im,56,'秒',14,x=135);text(im,86,hint,16);text(im,110,detail,13);text(im,132,'声音',13,x=25)
 else:text(im,74,hint,17);text(im,116,detail,14)
 voices.append(im)
p=root/'firmware-epaper/main/interaction_screens.h';s=p.read_text()
for name,frames in [('interaction_home',homes),('interaction_voice',voices)]:
 pattern=r'static const unsigned char '+name+r'\[\d+\]\[5000\]=\{.*?\};';s,count=re.subn(pattern,lambda _:emit(name,frames),s,flags=re.S);assert count==1,name
p.write_text(s);print('generated 4 home + 13 voice screens; other controls preserved')
