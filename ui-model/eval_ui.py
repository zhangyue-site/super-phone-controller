# -*- coding: utf-8 -*-
# 新模型定位质量快评：取最后6条样本，比较预测与真值
import json, torch
from transformers import AutoTokenizer, AutoModelForCausalLM

BASE = "/root/ui-models/out-lora3-merged"
DATA = "/root/ui-models/sft_ui.jsonl"
rows = [json.loads(l) for l in open(DATA, encoding="utf-8") if l.strip()]
test = rows[-6:]

tok = AutoTokenizer.from_pretrained(BASE)
model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")

def center(b): return ((b[0]+b[2])//2, (b[1]+b[3])//2)

ok_type = ok_pos = 0
for i, r in enumerate(test):
    msgs = r["messages"][:2]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = tok(prompt, return_tensors="pt").to("cuda")
    out = model.generate(**ids, max_new_tokens=160, do_sample=False, temperature=None, top_p=None, pad_token_id=tok.eos_token_id)
    txt = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    gt = json.loads(r["messages"][2]["content"])
    try:
        pred = json.loads(txt[txt.index("{"):txt.rindex("}")+1])
    except Exception:
        print(i, "PARSE_FAIL:", txt[:120].replace("\n", " ")); continue
    pa, ga = pred.get("action", {}), gt["action"]
    tsame = pa.get("type") == ga.get("type")
    d = -1
    if tsame and isinstance(pa.get("bounds"), list) and len(pa["bounds"]) >= 4 and isinstance(ga.get("bounds"), list) and len(ga["bounds"]) >= 4:
        px, py = center(pa["bounds"]); gx, gy = center(ga["bounds"])
        d = int(((px-gx)**2 + (py-gy)**2) ** 0.5)
        ok_pos += d <= 60
    ok_type += tsame
    print(i, "type", pa.get("type"), "/", ga.get("type"), "| dist", d, "|", (pred.get("thought") or "")[:30])
print(f"SUMMARY type {ok_type}/6 pos<=60px {ok_pos}/6")
