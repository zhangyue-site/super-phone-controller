#!/usr/bin/env python3
"""Product slice for 200x200 e-paper. Single geometry source for C++ and previews.
No runtime fonts, no transport/permission policy changes. All output is 1-bit.
"""
from pathlib import Path
import json, re
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'firmware-epaper/main'
OUT=ROOT.parent/'display-preview'
VERSION=re.search(r'set\(PROJECT_VER\s+"([0-9]+\.[0-9]+\.[0-9]+)"\)',(ROOT/'firmware-epaper/CMakeLists.txt').read_text()).group(1)
FONT='/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc'
# Keep existing hit areas exactly; consent and footer are safety-sensitive.
LAYOUT={'width':200,'height':200,'title_end':45,'top_begin':45,'top_end':100,'bottom_begin':105,'bottom_end':155,'consent_begin':65,'consent_end':125,'footer_begin':162,'footer_end':188,'footer_split':100,'sound_top_begin':54,'sound_top_end':100,'sound_bottom_begin':108,'sound_bottom_end':154}
HOMES=[('待连接','请连接被控手机USB'),('需要允许操作','点手机控制 · 两步确认'),('已允许操作','云端与画面请在手机核对'),('手机中转已连接','画面与操作结果请看手机'),('操作已停止','本地操作许可已撤销'),('连接已中断','请重新检查手机与控制板'),('操作未完成','请在手机检查结果'),('网络待连接','本地许可有效 · 检查网络')]
OTA=[('控制板升级',f'当前版本 {VERSION}','检查 Wi-Fi 升级','返回首页'),('正在检查版本','请保持供电','等待服务器回复',''),('正在传输固件','请保持供电','停止可取消传输',''),('正在重启','镜像校验已通过','启动结果待手机核验',''),('无需升级','当前已是目标版本','返回继续使用',''),('升级未完成','保留原有效固件','请在手机查看原因','')]
BLE=[('蓝牙维护','在手机选择升级文件','请保持供电'),('蓝牙传输中','请保持手机靠近','停止可取消传输'),('正在校验固件','正在完成安全写入','请勿拔电'),('即将重启','镜像校验已通过','启动结果待手机核验'),('升级未完成','保留原有效固件','请在手机查看原因')]
POWER=[('松手关机','继续按住至30秒重启','正在升级时等待安全退出'),('正在停止任务','等待升级安全退出','请保持供电'),('等待安全写入','正在提交固件','暂不关机或重启'),('已待机','按电源键恢复','USB供电时仍保留维护'),('未能安全关闭','请稍后重试','仍可使用手机维护')]

def text(im,value,y,size=20,height=None):
 if not value:return
 d=ImageDraw.Draw(im);font=ImageFont.truetype(FONT,size)
 box=d.textbbox((0,0),value,font=font);w,h=box[2]-box[0],box[3]-box[1]
 assert w<=188,(value,w)
 if height is not None:assert h<=height,(value,h,height)
 d.text(((200-w)//2-box[0],y-box[1]),value,font=font,fill=0)

def blank():return Image.new('1',(200,200),1)
def button(im,label,sub,y0,y1):
 ImageDraw.Draw(im).rounded_rectangle((6,y0+1,193,y1-2),radius=5,outline=0,width=2)
 text(im,label,y0+9,22)
 if sub:text(im,sub,y0+35,12)
def footer(im,left='首页'):
 d=ImageDraw.Draw(im);y=LAYOUT['footer_begin'];d.line((0,y,199,y),fill=0,width=1);d.line((99,y,99,187),fill=0,width=1)
 for label,x in [(left,50),('停止操作',150)]:
  font=ImageFont.truetype(FONT,13 if len(label)>4 else 17);box=d.textbbox((0,0),label,font=font);w=box[2]-box[0]
  d.text((x-w//2-box[0],168-box[1]),label,font=font,fill=0)
def arrays(name,frames):return f'static const unsigned char {name}[{len(frames)}][5000]={{'+','.join('{'+','.join(map(str,f.tobytes()))+'}' for f in frames)+'};\n'
def generate():
 OUT.mkdir(exist_ok=True)
 groups={}
 homes=[]
 for title,hint in HOMES:
  im=blank();text(im,title,5,24);text(im,hint,32,12)
  button(im,'语音对话','点此进入说话',LAYOUT['top_begin'],LAYOUT['top_end'])
  button(im,'手机控制','点标题调声音 · 翻页看更多',LAYOUT['bottom_begin'],LAYOUT['bottom_end'])
  footer(im);homes.append(im)
 groups['product_home']=homes
 modes=[]
 for enabled in (False,True):
  for step in (0,1):
   im=blank();text(im,('确认停止操作' if enabled else '确认允许操作') if step else ('停止手机操作' if enabled else '允许手机操作'),8,23)
   text(im,'请确认USB连被控手机' if step else '也可短按BOOT操作',43,16)
   label=('确认停止' if enabled else '确认允许') if step else '点按下一步'
   button(im,label,'',LAYOUT['consent_begin'],LAYOUT['consent_end'])
   text(im,'15秒内完成确认',137,15);footer(im);modes.append(im)
 groups['product_mode']=modes
 for name,states in [('product_ota',OTA),('product_ble',BLE),('product_power',POWER)]:
  frames=[]
  for i,values in enumerate(states):
   im=blank();text(im,values[0],9,23)
   if name=='product_ota' and i==0:
    text(im,values[1],36,13);button(im,values[2],'',45,100);button(im,values[3],'',105,155)
   else:
    text(im,values[1],65,18);text(im,values[2],101,16)
   footer(im,'电源状态' if name=='product_power' else '升级中' if (name=='product_ota' and i in (1,2,3)) or (name=='product_ble' and i in (1,2,3)) else '首页');frames.append(im)
  groups[name]=frames
 offline=blank();text(offline,'网络未连接',9,23);text(offline,'请连接控制板Wi-Fi',65,18);text(offline,'手机中转请在手机发任务',101,15);footer(offline)
 groups['product_offline']=[offline]
 ota_offline=blank();text(ota_offline,'Wi-Fi未连接',9,23);text(ota_offline,'请在手机用蓝牙升级',65,18);text(ota_offline,'原有效固件保持不变',101,16);footer(ota_offline)
 groups['product_ota_offline']=[ota_offline]
 manuals=[]
 for i,labels in enumerate((('返回桌面','返回上页'),('向左移动','向右移动'),('向上移动','向下移动'),('点击当前位置','停止操作'))):
  im=blank();text(im,f'手机控制 {i+1}/4',5,23);text(im,'翻页切换 · 结果请看手机',32,12)
  button(im,labels[0],'',LAYOUT['top_begin'],LAYOUT['top_end']);button(im,labels[1],'',LAYOUT['bottom_begin'],LAYOUT['bottom_end']);footer(im);manuals.append(im)
 groups['product_manual']=manuals
 sounds=[]
 for muted in (False,True):
  for volume in range(0,101,20):
   im=blank();text(im,'声音设置',5,23);text(im,f'音量 {volume}% · '+('已静音' if muted else '当前无声' if volume==0 else '可播放'),34,14)
   d=ImageDraw.Draw(im)
   for label,x0,x1,y0,y1 in [('调低',6,96,LAYOUT['sound_top_begin'],LAYOUT['sound_top_end']),('调高',103,193,LAYOUT['sound_top_begin'],LAYOUT['sound_top_end']),('取消静音' if muted else '静音',6,96,LAYOUT['sound_bottom_begin'],LAYOUT['sound_bottom_end']),('试听',103,193,LAYOUT['sound_bottom_begin'],LAYOUT['sound_bottom_end'])]:
    d.rounded_rectangle((x0,y0+1,x1,y1-2),radius=5,outline=0,width=2);font=ImageFont.truetype(FONT,19);box=d.textbbox((0,0),label,font=font);w=box[2]-box[0];assert w<=86;d.text(((x0+x1-w)//2-box[0],y0+12-box[1]),label,font=font,fill=0)
   footer(im);sounds.append(im)
 groups['product_sound']=sounds
 voices=[]
 voice_states=[('语音对话','按住录音 · 松手识别','先看计划，再执行'),('正在录音','松手结束录音','最长10秒 · 至少半秒'),('正在识别','已收到这段录音','识别后先显示计划'),('本轮已结束','请核对手机与结果','返回语音页可继续说话'),('准备录音','麦克风正在启动','看到录音后再说话'),('本轮未完成','请靠近麦克风重说','也可在手机查看原因'),('网络未连接','请连接控制板Wi-Fi','手机中转请在手机发任务'),('正在检查连接','还未开始录音','检查完成后重新按住'),('可以开始说话','按住录音 · 松手识别','操作手机仍需本地许可'),('连接检查失败','请检查网络后重试','这次尚未开始录音'),('正在处理任务','请在手机查看进展','停止可取消后续操作'),('正在播报','回答结束后可再说','停止可中断播报'),('录音时间太短','请按住至少半秒','看到录音计时再说话'),('连接已中断','本轮结果尚未确认','请检查网络后再试')]
 for i,(title,hint,detail) in enumerate(voice_states):
  im=blank();text(im,title,8,23)
  if i==0:
   button(im,'按住说话','松手结束录音',45,155);text(im,detail,126,15)
  elif i==1:
   text(im,'秒',62,17);text(im,hint,93,18);text(im,detail,117,14)
   # Counter/level use bounded integer buckets in the renderer.
  else:text(im,hint,69,18);text(im,detail,112,15)
  footer(im);voices.append(im)
 groups['product_voice']=voices
 preparations=[]
 for title,hint,detail in [('正在检查网络','还未开始录音','请保持Wi-Fi连接'),('连接检查未通过','请在手机查看原因','返回后可再次说话'),('可以开始说话','语音连接已检查','操作手机仍需本地许可')]:
  im=blank();text(im,title,8,23);text(im,hint,69,18);text(im,detail,112,15);footer(im);preparations.append(im)
 groups['product_prepare']=preparations
 networks=[]
 for title,hint,detail in [('网络与连接','USB尚未连接','可在手机选择蓝牙中转'),('控制板Wi-Fi','网络连接已建立','云端与画面请看手机'),('手机蓝牙中转','中转连接已建立','共享状态请在手机查看'),('本地USB维护','USB连接已建立','不代表手机或云端就绪'),('网络待连接','请连接控制板Wi-Fi','或在手机启用蓝牙中转')]:
  im=blank();text(im,title,8,23);text(im,hint,69,18);text(im,detail,112,15);footer(im);networks.append(im)
 groups['product_network']=networks
 loading=[]
 for title in ('额度与余额','任务记录'):
  im=blank();text(im,title,8,23);text(im,'正在等待云端数据',69,18);text(im,'请检查控制板Wi-Fi',112,15);footer(im);loading.append(im)
 groups['product_loading']=loading
 content='// Generated by tools/generate_product_screens.py; do not edit pixel arrays.\n#pragma once\n'
 for name,frames in groups.items():
  content+=arrays(name,frames)
  for i,im in enumerate(frames):im.save(OUT/f'{name}-{i}.png')
 # Main renderer can apply this identical footer to all retained legacy pages.
 footers=[]
 for value in ('首页','首页·需连接','首页·待联网','首页·需许可','首页·未完成','首页·已停止'):
  footer_im=blank();footer(footer_im,value);footers.append(footer_im.tobytes()[162*25:188*25])
 content+='static const unsigned char product_footer[6][650]={'+','.join('{'+','.join(map(str,raw))+'}' for raw in footers)+'};\n'
 content+='static const unsigned char product_cache_title[2][775]={'+','.join('{'+','.join(map(str,im.tobytes()[:775]))+'}' for im in loading)+'};\n'
 (MAIN/'product_screens.h').write_text(content)
 layout_header='// Generated with the image geometry by generate_product_screens.py.\n#pragma once\nnamespace controller { namespace product_layout {\n'+''.join(f'constexpr int {k}={v};\n' for k,v in LAYOUT.items())+'}}\n'
 (MAIN/'product_ui_layout.h').write_text(layout_header)
 (OUT/'layout.json').write_text(json.dumps(LAYOUT,indent=2)+'\n')
 # Contact sheet for visual verification, preserving individual 200x200 originals.
 cells=[(name,i,im) for name,frames in groups.items() for i,im in enumerate(frames)]
 sheet=Image.new('RGB',(800,((len(cells)+3)//4)*225),'#dddddd');draw=ImageDraw.Draw(sheet)
 for n,(name,i,im) in enumerate(cells):
  x=(n%4)*200;y=(n//4)*225;sheet.paste(im.convert('RGB'),(x,y));draw.text((x+4,y+202),f'{name}-{i}',fill='black')
 sheet.save(OUT/'product-contact-sheet.png')
 details=[('product_manual',i) for i in range(4)]+[('product_sound',i) for i in (0,5,6,11)]+[('product_voice',i) for i in (0,1,2,3,4,5,6,10,11,13)]+[('product_network',i) for i in range(5)]+[('product_prepare',i) for i in range(3)]+[('product_loading',i) for i in range(2)]
 detail_sheet=Image.new('RGB',(800,((len(details)+3)//4)*225),'#dddddd');draw=ImageDraw.Draw(detail_sheet)
 for n,(name,i) in enumerate(details):
  x=n%4*200;y=n//4*225;detail_sheet.paste(groups[name][i].convert('RGB'),(x,y));draw.text((x+4,y+202),f'{name}-{i}',fill='black')
 detail_sheet.save(OUT/'product-detail-sheet.png')
 # Final framebuffer examples: same footer and numeric overlay as main.cpp.
 runtime=[('product_voice',i) for i in (0,1,2,10,11)]+[('product_network',1),('product_prepare',0),('product_ota_offline',0)]
 runtime_sheet=Image.new('RGB',(800,450),'#dddddd');rd=ImageDraw.Draw(runtime_sheet)
 for n,(name,i) in enumerate(runtime):
  im=groups[name][i].copy()
  if name not in ('product_ota_offline',):footer(im,'首页·需许可')
  if name=='product_voice' and i==1:
   d=ImageDraw.Draw(im);segments=(0x3f,0x06,0x5b,0x4f,0x66,0x6d,0x7d,0x07,0x7f,0x6f)
   for x,value in ((62,0),(76,5)):
    for q in range(7):
     if not segments[value]&(1<<q):continue
     xx,yy,w,h=x,54,10,2
     if q==1:xx+=9;yy+=1;w,h=2,10
     elif q==2:xx+=9;yy+=11;w,h=2,10
     elif q==3:yy+=20
     elif q==4:yy+=11;w,h=2,10
     elif q==5:yy+=1;w,h=2,10
     elif q==6:yy+=10
     d.rectangle((xx,yy,xx+w-1,yy+h-1),fill=0)
   d.rectangle((48,136,191,148),outline=0);d.rectangle((49,137,49+142*1200//2000,147),fill=0)
  x=n%4*200;y=n//4*225;runtime_sheet.paste(im.convert('RGB'),(x,y));caption=ImageFont.truetype(FONT,11);rd.text((x+3,y+202),'合成预览·非实机 '+str(n+1),font=caption,fill='black');im.save(OUT/f'runtime-{name}-{i}.png')
 runtime_sheet.save(OUT/'product-runtime-preview.png')

 return groups
if __name__=='__main__':generate()
