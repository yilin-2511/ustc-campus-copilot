"""续跑 Phase 3 — 从断点继续，不删 checkpoint"""
import os, json, sys
os.environ["DEEPSEEK_API_KEY"] = "sk-l5k0LeqnoqudJtEhp4kNCw"
os.environ["DEEPSEEK_API_BASE"] = "https://api.llm.ustc.edu.cn/v1"
from pathlib import Path
os.chdir(Path(__file__).resolve().parent.parent)
sys.path.insert(0, "scripts")
from scrape_n7teahouse import synthesize_answers

# 检查断点
ckpt = Path("data/raw/n7teahouse/n7_qa_checkpoint.json")
if ckpt.exists():
    c = json.load(open(ckpt, encoding="utf-8"))
    print(f"从断点续跑: 已有 {len(c['entries'])} 条, 从第 {c['next_idx']+1} 条继续\n")
else:
    print("无断点，从头开始\n")

data = json.load(open("data/raw/n7teahouse/n7_candidates.json", encoding="utf-8"))
print(f"全量 {len(data['candidates'])} 条, qwen3.5, 2 并发, 10条/批\n")
synthesize_answers(data["candidates"], model="qwen3.5")
