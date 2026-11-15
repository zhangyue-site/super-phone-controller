#!/usr/bin/env python3
# 仿真保真度校验：真实审计动作的坐标/语义 vs 仿真器规则
import json, os, glob
from collections import Counter

AUD = "/opt/phone-controller-integration-20261029/state/bill-operator/audit"
W, H, HIDMAX = 588, 1280, 32767.0

def pt(x, y): return x/HIDMAX*W, y/HIDMAX*H

zones = Counter(); drags = []; clicks_total = 0; save_clicks = []; row_clicks = []
for d in sorted(os.listdir(AUD)):
    base = os.path.join(AUD, d)
    for pf in glob.glob(os.path.join(base, "action-*-pending.json")):
        try: p = json.load(open(pf))
        except Exception: continue
        cmd = p.get("command") or {}
        purpose = (p.get("purpose") or "") + (p.get("label") or "")
        if cmd.get("op") == "hid_pointer" and cmd.get("kind") == "click":
            clicks_total += 1
            x, y = pt(cmd["x"], cmd["y"])
            if y < 0.12*H and x < 0.2*W: zones["back区"] += 1
            elif y > 0.9*H: zones["底部导航区"] += 1
            elif y < 0.09*H: zones["标题区"] += 1
            elif 0.72*H < y and x > 0.6*W:
                zones["右下保存区"] += 1
                if any(k in purpose.lower() for k in ["save","confirm","verify","核对","保存"]): save_clicks.append((round(x),round(y)))
            elif 0.09*H <= y <= 0.78*H:
                zones["列表行区"] += 1
                row_clicks.append((round(x),round(y),purpose[:24]))
            else: zones["其他"] += 1
        elif cmd.get("op") == "hid_pointer" and cmd.get("kind") in ("drag","swipe"):
            y1,_ = pt(0, cmd["y"]); y2,_ = pt(0, cmd.get("y2", cmd["y"]))
            drags.append(round(abs(y2-y1)))

print("真实click总数:", clicks_total)
for k, v in zones.most_common(): print(f"  {k}: {v} ({100*v/max(1,clicks_total):.0f}%)")
# 仿真器规则对照
print("\n仿真规则对照:")
print("  列表行区 y 120-1000 (仿真: TOP_Y=120, 8行x110=880 -> 120-1000):", f"{100*zones['列表行区']/max(1,clicks_total):.0f}% 的真实点击落在仿真行区")
print("  右下保存区 (仿真: [388-548, 1000-1080]):", f"{100*zones['右下保存区']/max(1,clicks_total):.0f}%")
if save_clicks:
    ys = [y for _, y in save_clicks]
    print("  保存类点击 y 范围:", min(ys), "-", max(ys), "仿真保存钮 y: 1000-1080 中心1040")
if drags:
    drags.sort()
    print("  真实拖拽纵向位移: p50", drags[len(drags)//2], "px; 仿真滚动步长=4行x110=440px")
if row_clicks:
    ys = sorted(y for _, y, _ in row_clicks)
    print("  行点击 y 范围:", ys[0], "-", ys[-1], " 仿真行区: 120-1000")
