# -*- coding: utf-8 -*-
# UI 决策模型 SFT (QLoRA PoC)：Qwen3.5-0.6B + sft_ui.jsonl
import json, torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

BASE = "/root/ui-models/qwen3-0.6b"
DATA = "/root/ui-models/sft_ui.jsonl"
OUT = "/root/ui-models/out-lora3"

rows = [json.loads(l) for l in open(DATA, encoding="utf-8") if l.strip()]
print("examples:", len(rows))

tok = AutoTokenizer.from_pretrained(BASE)
tok.pad_token = tok.eos_token

model = AutoModelForCausalLM.from_pretrained(
    BASE, torch_dtype=torch.bfloat16, device_map="cuda",
    load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_compute_dtype=torch.bfloat16)
model = prepare_model_for_kbit_training(model)
model = get_peft_model(model, LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    task_type="CAUSAL_LM"))
model.print_trainable_parameters()

def fmt(ex):
    msgs = ex["messages"]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)

ds = Dataset.from_list([{"text": fmt(r)} for r in rows])

cfg = SFTConfig(
    output_dir=OUT, per_device_train_batch_size=1, gradient_accumulation_steps=8,
    num_train_epochs=3, learning_rate=1e-4, logging_steps=10, save_strategy="no",
    max_seq_length=1280, bf16=True, report_to=[], dataset_text_field="text")
trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds, processing_class=tok)
trainer.train()
trainer.save_model(OUT)
# 合并导出
model = model.merge_and_unload()
model.save_pretrained(OUT + "-merged")
tok.save_pretrained(OUT + "-merged")
print("DONE", OUT + "-merged")
