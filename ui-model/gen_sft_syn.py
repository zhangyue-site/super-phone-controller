#!/usr/bin/env python3
# 合成语料生成器：用仿真环境产生带真值标签的训练样本
import json, random, sys
sys.path.insert(0, "/root/ui-models")

W, H = 588, 1280
VIS, ROW_H, TOP_Y = 8, 110, 120
SHOPS = ["瑞幸咖啡","美团外卖","京东自营","滴滴出行","盒马鲜生","麦当劳","肯德基","淘宝","拼多多","星巴克","喜茶","沃尔玛","山姆会员店","库迪咖啡","蜜雪冰城"]
CATS = ["餐饮美食","交通出行","日用百货","数码电器","服饰鞋帽"]

SYS = ("你是手机UI自动化决策引擎。输入=当前任务、屏幕OCR行(text/bounds,坐标系588x1280,bounds即目标区域,点它中心即可)、最近动作历史。"
       "你需要输出下一步动作,只输出一个JSON对象,格式:"
       '{"thought":"一句话理由","action":{"type":"click|scroll|input|back|done|need_help","bounds":[x1,y1,x2,y2],"text":"仅input需要"}}。'
       "规则:点击用目标文字行的bounds中心;滚动用列表区域;无法判断用need_help。")

def mk_sample(env_lines, act, thought, hist):
    user = json.dumps({"task": "在账单列表逐条核对并滚动浏览", "screen": env_lines, "history": hist[-3:]}, ensure_ascii=False)
    asst = json.dumps({"thought": thought, "action": act}, ensure_ascii=False)
    return {"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}, {"role": "assistant", "content": asst}]}

def list_lines(rows, top, jitter):
    rng = random.Random(jitter)
    lines = [{"text": "账单列表", "bounds": [0, 40, W, 90]}]
    vis = rows[top:top+VIS]
    for i, r in enumerate(vis):
        y1 = TOP_Y + i * ROW_H + rng.randint(-3, 3)
        lines.append({"text": f'{r["shop"]} {r["date"]} 支出¥{r["amt"]}', "bounds": [0, y1, W, y1 + ROW_H - 8]})
    lines.append({"text": "底部导航", "bounds": [0, H-90, W, H]})
    return lines

def detail_lines(r, seed):
    rng = random.Random(seed)
    return [
        {"text": "账单详情", "bounds": [0, 40, W, 90]},
        {"text": f'商家 {r["shop"]}', "bounds": [40, 200+rng.randint(-3,3), 400, 250]},
        {"text": f'金额 ¥{r["amt"]}', "bounds": [40, 300, 400, 350]},
        {"text": f'时间 {r["date"]} {rng.randint(10,21)}:{rng.randint(10,59)}', "bounds": [40, 400, 400, 450]},
        {"text": f'分类 {rng.choice(CATS)}', "bounds": [40, 500, 400, 550]},
        {"text": "保存并核对", "bounds": [W-200, 1000, W-40, 1080]},
        {"text": "底部导航", "bounds": [0, H-90, W, H]},
    ]

def main(n_target=2600, out_path="/opt/novel-distill-autodl/data/sft_ui_syn.jsonl"):
    rng = random.Random(7)
    samples = []
    while len(samples) < n_target:
        n_rows = rng.randint(6, 14)
        rows = [{"shop": rng.choice(SHOPS), "amt": f"{rng.uniform(3,500):.2f}", "date": f"10-{rng.randint(1,28):02d}", "done": False} for _ in range(n_rows)]
        done_n = rng.randint(0, n_rows-1)          # 任务进行到一半的随机快照
        for i in range(done_n): rows[i]["done"] = True
        undone = [r for r in rows if not r["done"]]
        top = rng.randint(0, max(0, len(undone)-VIS))
        hist = []
        in_detail = rng.random() < 0.3             # 三成样本在详情页
        if in_detail:
            cur = undone[0]
            lines = detail_lines(cur, len(samples))
            act = {"type": "click", "bounds": [W-200, 1000, W-40, 1080]}
            th = "明细核对无误，点击右下角保存按钮"
            samples.append(mk_sample(lines, act, th, hist))
        else:
            lines = list_lines(undone, top, len(samples))
            vis = undone[top:top+VIS]
            pick = rng.randrange(len(vis))
            r = vis[pick]
            act = {"type": "click", "bounds": lines[1+pick]["bounds"]}
            th = f'点击"{r["shop"]}"的账单行，打开明细核对'
            samples.append(mk_sample(lines, act, th, hist))
            # 追加同环境下的滚动样本
            if len(samples) < n_target and top + VIS < len(undone):
                hist2 = hist + [{"type": "click"}]
                act2 = {"type": "scroll", "bounds": [0, TOP_Y, W, H-100]}
                th2 = "当前屏幕可见行已处理，向下滚动查看更多账单"
                samples.append(mk_sample(list_lines(undone, top, len(samples)+1), act2, th2, hist2))
            # 全部完成时的done样本
            if len(samples) < n_target and done_n == n_rows-1 and top == 0:
                act3 = {"type": "done"}
                samples.append(mk_sample(list_lines(rows, 0, len(samples)+2), act3, "所有账单均已核对完毕，任务完成", hist))
    with open(out_path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print("synthetic:", len(samples), "->", out_path)

if __name__ == "__main__":
    main()
