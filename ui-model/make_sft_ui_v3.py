#!/usr/bin/env python3
# v3: 解析原始 hid_pointer 命令(x/y 0-32767 -> 588x1280),扩语料
import json, os, glob

AUD = "/opt/phone-controller-integration-20261029/state/bill-operator/audit"
OUT = "/opt/novel-distill-autodl/data/sft_ui.jsonl"
W, H, HIDMAX = 588, 1280, 32767.0

SYS = ("你是手机UI自动化决策引擎。输入=当前任务、屏幕OCR行(text/bounds,坐标系588x1280,bounds即目标区域,点它中心即可)、最近动作历史。"
       "你需要输出下一步动作,只输出一个JSON对象,格式:"
       '{"thought":"一句话理由","action":{"type":"click|scroll|input|back|done|need_help","bounds":[x1,y1,x2,y2],"text":"仅input需要"}}。'
       "规则:点击用目标文字行的bounds中心;滚动用列表区域;无法判断用need_help。")

def pt(x, y):
    sx = max(2, min(W-2, int(x/HIDMAX*W))); sy = max(2, min(H-2, int(y/HIDMAX*H)))
    return sx, sy

def conv(cmd):
    op = cmd.get("op")
    if op == "hid_pointer":
        k = cmd.get("kind")
        if k == "click":
            sx, sy = pt(cmd["x"], cmd["y"])
            return {"type":"click","bounds":[max(0,sx-18),max(0,sy-18),min(W,sx+18),min(H,sy+18)]}
        if k in ("drag","swipe"):
            x1,y1 = pt(cmd["x"],cmd["y"]); x2,y2 = pt(cmd.get("x2",cmd["x"]),cmd.get("y2",cmd["y"]))
            return {"type":"scroll","bounds":[min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2)]}
        if k == "back": return {"type":"back"}
    if op == "hid_text":
        return {"type":"input","text":cmd.get("text",""),"bounds":None}
    return None

PUR = {"open_observed_source_consumption":"打开该消费记录查看明细","visible_search":"在搜索框输入内容"}

n=skip=0
with open(OUT,"w",encoding="utf-8") as out:
    for d in sorted(os.listdir(AUD)):
        base=os.path.join(AUD,d)
        pend=sorted(glob.glob(os.path.join(base,"action-*-pending.json")))
        if pend:
            hist=[]
            for pf in pend:
                idx=os.path.basename(pf).split("-")[1]
                try: p=json.load(open(pf))
                except Exception: skip+=1; continue
                act=conv(p.get("command") or {})
                of=os.path.join(base,f"{idx}-ocr.json")
                if not act or not os.path.exists(of): skip+=1; continue
                try: lines=(json.load(open(of)).get("lines")) or []
                except Exception: skip+=1; continue
                if len(lines)<5: skip+=1; continue
                if act["type"]=="input":
                    cand=[L for L in lines if L.get("center") and L["center"][1]<H*0.4 and ("搜索" in L["text"] or "search" in L["text"].lower())]
                    if not cand: skip+=1; continue
                    b=cand[0].get("bounds") or [0,0,W,120]
                    act["bounds"]=b
                lbl=p.get("purpose") or p.get("label") or ""
                ls2=[L for L in lines if L.get("bounds")][:24]; screen=[{"text":L["text"],"bounds":L["bounds"]} for L in ls2]; lines=ls2
                user=json.dumps({"task":"在账单列表逐条核对并滚动浏览","screen":screen,"history":hist[-3:]},ensure_ascii=False)
                asst=json.dumps({"thought":PUR.get(lbl,lbl.replace("_"," ")) or "按任务推进","action":act},ensure_ascii=False)
                out.write(json.dumps({"messages":[{"role":"system","content":SYS},{"role":"user","content":user},{"role":"assistant","content":asst}]},ensure_ascii=False)+"\n")
                hist.append(act); n+=1
            continue
        of=os.path.join(base,"source-navigation-ocr.json"); af=os.path.join(base,"source-navigation-action.json")
        if os.path.exists(of) and os.path.exists(af):
            try:
                a=json.load(open(af)); tgt=a.get("target",a); lines=(json.load(open(of)).get("lines")) or []
                b=tgt.get("bounds")
                if b and len(lines)>=5:
                    act={"type":"click","bounds":b}
                    ls2=[L for L in lines if L.get("bounds")][:24]; screen=[{"text":L["text"],"bounds":L["bounds"]} for L in ls2]; lines=ls2
                    user=json.dumps({"task":"导航到支付宝/微信账单列表","screen":screen,"history":[]},ensure_ascii=False)
                    asst=json.dumps({"thought":f"目标:{tgt.get('label','')}" if tgt.get('label') else "按任务推进","action":act},ensure_ascii=False)
                    out.write(json.dumps({"messages":[{"role":"system","content":SYS},{"role":"user","content":user},{"role":"assistant","content":asst}]},ensure_ascii=False)+"\n")
                    n+=1; continue
            except Exception: pass
        skip+=1
print("examples:",n,"skipped:",skip,"->",OUT)
