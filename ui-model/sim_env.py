# -*- coding: utf-8 -*-
# 虚拟手机仿真器：闭环测试 UI 决策模型（列表→详情→保存→滚动→done）
import json, random, re, sys
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

W, H = 588, 1280
MODEL = "/root/ui-models/out-lora3-merged"
VIS = 8          # 列表可见行数
ROW_H = 110      # 行高
TOP_Y = 120      # 列表起始 y

SYS = ("你是手机UI自动化决策引擎。输入=当前任务、屏幕OCR行(text/bounds,坐标系588x1280,bounds即目标区域,点它中心即可)、最近动作历史。"
       "你需要输出下一步动作,只输出一个JSON对象,格式:"
       '{"thought":"一句话理由","action":{"type":"click|scroll|input|back|done|need_help","bounds":[x1,y1,x2,y2],"text":"仅input需要"}}。'
       "规则:点击用目标文字行的bounds中心;滚动用列表区域;无法判断用need_help。")

class BillEnv:
    def __init__(self, n_rows=10, seed=0):
        rng = random.Random(seed)
        shops = ["瑞幸咖啡","美团外卖","京东自营","滴滴出行","盒马鲜生","麦当劳","肯德基","淘宝","拼多多","星巴克","喜茶","沃尔玛"]
        self.rows = [{"shop": rng.choice(shops), "amt": f"{rng.uniform(5,300):.2f}",
                      "date": f"10-{rng.randint(1,28):02d}", "done": False, "clicked": False}
                     for _ in range(n_rows)]
        self.top = 0
        self.state = "LIST"
        self.cur = None
        self.invalid = 0
        self.steps = 0

    def visible(self):
        return [r for r in self.rows if not r["done"]][self.top:self.top+VIS]

    def screen(self):
        lines = [{"text": "账单列表", "bounds": [0, 40, W, 90]}]
        for i, r in enumerate(self.visible()):
            y1 = TOP_Y + i * ROW_H
            lines.append({"text": f'{r["shop"]} {r["date"]} 支出¥{r["amt"]}',
                          "bounds": [0, y1, W, y1 + ROW_H - 8]})
        lines.append({"text": "底部导航", "bounds": [0, H - 90, W, H]})
        return lines

    def detail_screen(self):
        r = self.cur
        return [
            {"text": "账单详情", "bounds": [0, 40, W, 90]},
            {"text": f'商家 {r["shop"]}', "bounds": [40, 200, 400, 250]},
            {"text": f'金额 ¥{r["amt"]}', "bounds": [40, 300, 400, 350]},
            {"text": f'时间 {r["date"]} 12:3{random.Random(self.steps).randint(0,9)}', "bounds": [40, 400, 400, 450]},
            {"text": "分类 餐饮美食", "bounds": [40, 500, 400, 550]},
            {"text": "保存并核对", "bounds": [W - 200, 1000, W - 40, 1080]},
            {"text": "底部导航", "bounds": [0, H - 90, W, H]},
        ]

    def center_in(self, b, line):
        cx, cy = (b[0]+b[2])//2, (b[1]+b[3])//2
        return line["bounds"][0] <= cx <= line["bounds"][2] and line["bounds"][1] <= cy <= line["bounds"][3]

    def step(self, act):
        self.steps += 1
        t = act.get("type"); b = act.get("bounds") or []
        ok = False
        if self.state == "LIST":
            vis = self.visible()
            if t == "click":
                hit = next((r for r, L in zip(vis, vis) for L2 in [None]), None)
                target = None
                for i, L in enumerate([{"text": "", "bounds": [0, TOP_Y + i*ROW_H, W, TOP_Y + (i+1)*ROW_H - 8]} for i in range(len(vis))]):
                    if b and len(b) >= 4 and self.center_in(b, L):
                        target = vis[i]; break
                if target is not None:
                    self.cur = target; self.state = "DETAIL"; ok = True
            elif t == "scroll":
                undone = [r for r in self.rows if not r["done"]]
                if self.top + VIS < len(undone):
                    self.top = min(self.top + 4, max(0, len(undone) - VIS)); ok = True
            elif t == "done":
                ok = all(r["done"] for r in self.rows)
        else:  # DETAIL
            if t == "click" and b and len(b) >= 4:
                L = {"bounds": [W-200, 1000, W-40, 1080]}
                if self.center_in(b, L):
                    self.cur["done"] = True; self.state = "LIST"; ok = True
                    undone = [r for r in self.rows if not r["done"]]
                    self.top = min(self.top, max(0, len(undone) - VIS)) if undone else 0
            elif t == "back":
                self.state = "LIST"; ok = True
        if not ok:
            self.invalid += 1
        return ok

def center(b): return ((b[0]+b[2])//2, (b[1]+b[3])//2)

def main():
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16, device_map="cuda")
    model.eval()

    all_ep = []
    for seed in [1, 2, 3]:
        env = BillEnv(10, seed)
        hist, log = [], []
        budget = 120
        while env.steps < budget and not all(r["done"] for r in env.rows):
            lines = env.detail_screen() if env.state == "DETAIL" else env.screen()
            user = json.dumps({"task": "在账单列表逐条核对并滚动浏览", "screen": lines, "history": hist[-3:]}, ensure_ascii=False)
            prompt = tok.apply_chat_template([{"role":"system","content":SYS},{"role":"user","content":user}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
            ids = tok(prompt, return_tensors="pt").to("cuda")
            out = model.generate(**ids, max_new_tokens=300, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.eos_token_id)
            txt = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
            try:
                act = json.loads(txt[txt.index("{"):txt.rindex("}")+1])["action"]
            except Exception:
                act = {"type": "need_help"}
            ok = env.step(act)
            hist.append(act); log.append((env.state, act.get("type"), ok))
        done_n = sum(1 for r in env.rows if r["done"])
        all_ep.append({"seed": seed, "done": done_n, "total": len(env.rows), "steps": env.steps,
                       "invalid": env.invalid, "budget_exceeded": env.steps >= budget})
        print(f"EP seed={seed} 完成 {done_n}/{len(env.rows)} 步数 {env.steps} 无效动作 {env.invalid} 超时 {env.steps>=budget}")

    n = len(all_ep)
    print("SUMMARY episodes", n,
          "| rows_done", sum(e['done'] for e in all_ep), "/", sum(e['total'] for e in all_ep),
          "| success_eps", sum(1 for e in all_ep if e['done']==e['total']),
          "| avg_steps", round(sum(e['steps'] for e in all_ep)/n, 1),
          "| avg_invalid", round(sum(e['invalid'] for e in all_ep)/n, 1))

if __name__ == "__main__":
    main()
