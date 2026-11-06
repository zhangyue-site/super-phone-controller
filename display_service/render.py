"""200x200 monochrome view shared by firmware and PNG previews."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont


def render(rows, interaction, page=0, now=None, connected=True):
    """Render supplied facts only; connectivity is not a cloud/phone readiness proof.

    y >= 162 belongs to the firmware 1.6.8 footer overlay. ``now`` is rendering time,
    never the observation time; per-row age comes from the quota model.
    """
    font_path=os.environ.get('EPAPER_FONT','/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc')
    if not os.path.isfile(font_path):
        font_path='/System/Library/Fonts/Supplemental/Songti.ttc'
    font=ImageFont.truetype(font_path,14)
    small=ImageFont.truetype(font_path,9)
    title=ImageFont.truetype(font_path,22)
    im=Image.new('1',(200,200),1)
    d=ImageDraw.Draw(im)
    def text(x,y,value,f=font,width=184):
        value=str(value)
        if d.textlength(value,font=f)>width:
            while value and d.textlength(value+'…',font=f)>width:
                value=value[:-1]
            value+='…'
        d.text((x,y),value,font=f,fill=0,anchor='lt')
    def wrap(value,f,width):
        lines=[];line=''
        for char in str(value):
            if char=='\n' or d.textlength(line+char,font=f)>width:
                lines.append(line);line=''
                if char=='\n':continue
            line+=char
        if line:lines.append(line)
        return lines
    text(8,1,'额度与余额' if page==0 else '任务记录',title)
    d.line((8,29,191,29),fill=0)
    if page==0:
        text(8,31,'各渠道原单位 · 非账单',small)
        states={'ok':'','stale':'已过期','error':'获取失败','unavailable':'暂无数据'}
        for i,row in enumerate(rows[:5]):
            y=40+i*24
            label=str(row.get('label',''))
            value=row.get('value')
            # A missing amount is unknown, not zero. Preserve supplied units.
            value='--' if value is None or value=='' else str(value)
            width=d.textlength(value,font=font)
            if width<=100:
                text(8,y,label,font,width=max(30,174-width-8))
                text(192-width,y,value,font,width=width)
            else:
                # Preserve long amounts/units instead of hiding significant digits.
                # Use a second line and a measured font; no numeric conversion.
                text(8,y,label,small,width=184)
                fitted=font
                for size in range(15,7,-1):
                    fitted=ImageFont.truetype(font_path,size)
                    if d.textlength(value,font=fitted)<=184:break
                text(8,y+11,value,fitted,width=184)
            age=row.get('age')
            observed=(datetime.fromtimestamp(now-age,ZoneInfo('Asia/Shanghai')).strftime('%H:%M')
                      if now is not None and isinstance(age,(int,float)) and age>=0 else None)
            status=states.get(row.get('status'),'状态未知')
            # Long amounts keep all original digits; metadata remains on label line.
            if width<=100:
                detail=('更新 '+observed if observed else '更新时间未知')
                if status:detail+=' · '+status
                text(8,y+14,detail,small)
            else:
                detail=(observed or '--:--')+' '+(status or '更新')
                d.rectangle((8,y,191,y+10),fill=1)
                text(8,y,label+' · '+detail,small)
        # Firmware owns y >= 162; no dynamic footer is drawn here.
    else:
        state=interaction.get('state','idle')
        labels={'idle':'暂无任务','listening':'正在录音','thinking':'正在规划','running':'正在操作',
                'waiting':'等待确认','done':'结果已返回','error':'本轮未完成','stopped':'已停止'}
        text(8,34,labels.get(state,'状态待确认'),title)
        text(8,61,'手机：'+str(interaction['phone']) if interaction.get('phone') else '对象请在手机核对')
        task=interaction.get('task') or '请在控制手机发起任务'
        lines=wrap(task,font,184)
        for i,line in enumerate(lines[:3]):
            text(8,82+i*20,line+('…' if i==2 and len(lines)>3 else ''))
        # A returned result alone does not prove the target UI reached its goal.
        detail=('结果请在控制手机核对' if state=='done' else
                '请在控制手机查看原因' if state=='error' else
                '待执行步骤不会自动重放' if state=='stopped' else
                '步骤：'+str(interaction['step']) if interaction.get('step') is not None else
                '连接与许可请查看手机')
        text(8,143,detail,small)
        observed=interaction.get('updatedAt')
        stamp=(datetime.fromtimestamp(observed,ZoneInfo('Asia/Shanghai')).strftime('%m-%d %H:%M')
               if isinstance(observed,(int,float)) and observed>0 else '时间未知')
        text(8,153,'记录 '+stamp+' · 非在线证明',small)
    return im


def render_dialogue(reply,state,speech_error=False):
    """Large result text; the central bottom area matches the board STOP hit target."""
    font_path=os.environ.get('EPAPER_FONT','/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc')
    if not os.path.isfile(font_path):font_path='/System/Library/Fonts/STHeiti Medium.ttc'
    title=ImageFont.truetype(font_path,24);font=ImageFont.truetype(font_path,17)
    im=Image.new('1',(200,200),1);d=ImageDraw.Draw(im)
    label='播报不可用' if speech_error else '本轮结果' if state=='done' else '请核对手机' if state=='waiting' else '本轮未完成'
    d.text((8,5),label,font=title,fill=0)
    lines=[];line=''
    for c in reply:
        if c=='\n' or d.textlength(line+c,font=font)>180:
            lines.append(line);line=''
            if c=='\n':continue
        line+=c
    if line:lines.append(line)
    for i,line in enumerate(lines[:4]):d.text((8,39+i*21),line,font=font,fill=0)
    if len(lines)>4:d.text((170,103),'…',font=font,fill=0)
    d.rectangle((8,132,191,154),outline=0,width=2);d.text((47,134),'点此停止',font=font,fill=0)
    return im

def render_voice_ui(job):
    """Heard text + bounded plan, with the same visible STOP hit area as firmware."""
    path=os.environ.get('EPAPER_FONT','/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc')
    if not os.path.isfile(path):path='/System/Library/Fonts/STHeiti Medium.ttc'
    title=ImageFont.truetype(path,22);heard=ImageFont.truetype(path,13);body=ImageFont.truetype(path,14);button=ImageFont.truetype(path,17)
    im=Image.new('1',(200,200),1);d=ImageDraw.Draw(im)
    labels={'planning':'我听到了','plan':'准备这样做','running':'正在执行','verifying':'核对结果','done':'已完成','error':'本轮未完成','stopped':'已停止'}
    d.text((8,3),labels.get(job.state,'正在处理'),font=title,fill=0)
    def wrap(text,font,width):
        lines=[];line=''
        for c in text:
            if c=='\n' or d.textlength(line+c,font=font)>width:
                lines.append(line);line=''
                if c=='\n':continue
            line+=c
        if line:lines.append(line)
        return lines
    lines=wrap('你说：'+job.ui_heard,heard,184)
    for i,line in enumerate(lines[:2]):
        if i==1 and len(lines)>2:line=line[:-1]+'…'
        d.text((8,31+i*15),line,font=heard,fill=0)
    if getattr(job,'done',False):
        reply_lines=wrap(job.reply,body,184)
        for i,line in enumerate(reply_lines[:4]):
            if i==3 and len(reply_lines)>4:line=line[:-1]+'…'
            d.text((8,65+i*16),line,font=body,fill=0)
    elif job.ui_plan:
        for i,step in enumerate(job.ui_plan[:4]):
            text=str(i+1)+'. '+step
            while d.textlength(text,font=body)>184:text=text[:-2]+'…'
            d.text((8,65+i*16),text,font=body,fill=0)
    else:
        d.text((8,78),'正在理解，先不操作手机',font=body,fill=0)
        d.text((8,101),'稍后在这里显示计划',font=body,fill=0)
    d.rectangle((8,132,191,154),outline=0,width=2)
    d.text((47,133),'点此停止',font=button,fill=0)
    return im
