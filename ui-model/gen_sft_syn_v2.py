#!/usr/bin/env python3
# 合成语料生成器v2：整段回合出题(带history) + 无效动作恢复样本
import json, random

W, H = 588, 1280
SHOPS = ["瑞幸咖啡","美团外卖","京东自营","滴滴出行","盒马鲜生","麦当劳","肯德基","淘宝","拼多多","星巴克","喜茶","沃尔玛","山姆会员店","库迪咖啡","蜜雪冰城","支付宝转账","话费充值","网易云音乐"]
CATS = ["餐饮美食","交通出行","日用百货","数码电器","服饰鞋帽"]

SYS = ("你是手机UI自动化决策引擎。输入=当前任务、屏幕OCR行(text/bounds,坐标系588x1280,bounds即目标区域,点它中心即可)、最近动作历史。"
       "你需要输出下一步动作,只输出一个JSON对象,格式:"
       '{"thought":"一句话理由","action":{"type":"click|scroll|input|back|done|need_help","bounds":[x1,y1,x2,y2],"text":"仅input需要"}}。'
       "规则:点击用目标文字行的bounds中心;滚动用列表区域;无法判断用need_help。")

def mk(env_lines, act, thought, hist):
    user = json.dumps({"task": "在账单列表逐条核对并滚动浏览", "screen": env_lines, "history": hist[-3:]}, ensure_ascii=False)
    asst = json.dumps({"thought": thought, "action": act}, ensure_ascii=False)
    return {"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}, {"role": "assistant", "content": asst}]}

class Env:
    def __init__(self, rng):
        self.rng = rng
        self.TOP = rng.randint(110, 130)
        self.RH = rng.randint(100, 118)
        n = rng.randint(10, 16)
        self.rows = [{"shop": rng.choice(SHOPS), "amt": f"{rng.uniform(3,800):.2f}", "date": f"10-{rng.randint(1,28):02d}", "done": False} for _ in range(n)]
        self.state = "LIST"; self.top = 0
    def vis(self):
        return [r for r in self.rows if not r["done"]][self.top:self.top+8]
    def list_lines(self):
        lines = [{"text": "账单列表", "bounds": [0, 40, W, 90]}]
        for i, r in enumerate(self.vis()):
            y1 = self.TOP + i * self.RH
            lines.append({"text": f'{r["shop"]} {r["date"]} 支出¥{r["amt"]}', "bounds": [0, y1, W, y1 + self.RH - 8]})
        lines.append({"text": "首页 账单 我的", "bounds": [0, H-90, W, H]})
        return lines
    def detail_lines(self, r):
        rng = self.rng
        return [{"text": "账单详情", "bounds": [0, 40, W, 90]},
                {"text": f'商家 {r["shop"]}', "bounds": [40, 200, 400, 250]},
                {"text": f'金额 ¥{r["amt"]}', "bounds": [40, 300, 400, 350]},
                {"text": f'时间 {r["date"]}', "bounds": [40, 400, 400, 450]},
                {"text": f'分类 {rng.choice(CATS)}', "bounds": [40, 500, 400, 550]},
                {"text": "保存并核对", "bounds": [388, 1000, 548, 1080]},
                {"text": "首页 账单 我的", "bounds": [0, H-90, W, H]}]

SCROLL = [0, 120, W, 1000]

def gen_episode(rng, out, target_invalid_ratio=0.18):
    env = Env(rng)
    hist = []
    n_valid = 0
    while True:
        undone = [r for r in env.rows if not r["done"]]
        if not undone:
            out.append(mk(env.list_lines(), {"type": "done"}, "所有账单均已核对完毕，任务完成", hist)); break
        # 偶发无效动作恢复样本
        if hist and rng.random() < target_invalid_ratio:
            bad = rng.choice([
                ({"type": "click", "bounds": [0, H-90, W, H]}, "底部导航不是账单行，点击无效"),
                ({"type": "click", "bounds": [388, 1000, 548, 1080]}, "当前在列表页，保存按钮不存在"),
            ])
            # 选正确动作
            vis = env.vis()
            if not vis:
                correct = ({"type": "scroll", "bounds": SCROLL}, "上一步无效且当前无可见未核对行，向下滚动")
            else:
                pick = rng.randrange(len(vis))
                y1 = env.TOP + pick * env.RH
                correct = ({"type": "click", "bounds": [0, y1, W, y1 + env.RH - 8]}, "上一步无效，重新点击目标账单行")
            out.append(mk(env.list_lines(), correct[0], correct[1], hist))
            hist.append(correct[0])
            act = correct[0]
            if act["type"] == "click" and act["bounds"] != [388, 1000, 548, 1080]:
                env.state = "DETAIL"
            continue
        if env.state == "LIST":
            vis = env.vis()
            if not vis:
                out.append(mk(env.list_lines(), {"type": "scroll", "bounds": SCROLL}, "当前屏幕可见行已处理，向下滚动查看更多账单", hist))
                hist.append({"type": "scroll"}); env.top += 4
                if env.top > len(undone) - 1: env.top = max(0, len(undone) - 4)
                continue
            pick = rng.randrange(len(vis))
            y1 = env.TOP + pick * env.RH
            b = [0, y1, W, y1 + env.RH - 8]
            out.append(mk(env.list_lines(), {"type": "click", "bounds": b}, f'点击"{vis[pick]["shop"]}"的账单行，打开明细核对', hist))
            hist.append({"type": "click"}); env.state = "DETAIL"
            env.cur = vis[pick]; n_valid += 1
        else:  # DETAIL
            out.append(mk(env.detail_lines(env.cur), {"type": "click", "bounds": [388, 1000, 548, 1080]}, "明细核对无误，点击右下角保存按钮", hist))
            hist.append({"type": "click"}); env.cur["done"] = True; env.state = "LIST"; env.top = 0

def main(n_target=3000, out_path="/opt/novel-distill-autodl/data/sft_ui_syn2.jsonl"):
    rng = random.Random(11)
    out = []
    while len(out) < n_target:
        gen_episode(rng, out)
    out = out[:n_target]
    with open(out_path, "w", encoding="utf-8") as f:
        for s in out:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print("synthetic-v2:", len(out), "->", out_path)

if __name__ == "__main__":
    main()
