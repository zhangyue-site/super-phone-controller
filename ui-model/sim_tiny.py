import json, sys
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
src = open("/root/ui-models/sim_env.py").read().split("def main()")[0]
ns = {}
exec(src, ns)
BillEnv, SYS = ns["BillEnv"], ns["SYS"]
MODEL="/root/ui-models/out-lora3-merged"
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16, device_map="cuda")
model.eval()
env = BillEnv(6, 1)
hist=[]
for step in range(12):
    lines = env.detail_screen() if env.state=="DETAIL" else env.screen()
    user = json.dumps({"task":"在账单列表逐条核对并滚动浏览","screen":lines,"history":hist[-3:]},ensure_ascii=False)
    prompt = tok.apply_chat_template([{"role":"system","content":SYS},{"role":"user","content":user}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
    ids = tok(prompt,return_tensors="pt").to("cuda")
    out = model.generate(**ids,max_new_tokens=300,do_sample=False,temperature=None,top_p=None,pad_token_id=tok.eos_token_id)
    txt = tok.decode(out[0][ids["input_ids"].shape[1]:],skip_special_tokens=True)
    ok_json = True
    try:
        act = json.loads(txt[txt.index("{"):txt.rindex("}")+1])["action"]
    except Exception as e:
        act = {"type":"parse_fail"}; ok_json=False
    ok = env.step(act)
    print(f"step{step} state={env.state} act={json.dumps(act,ensure_ascii=False)[:130]} ok={ok} json={ok_json}", flush=True)
    hist.append(act)
