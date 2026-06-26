"""全量 Phase 3"""
import os, json, sys
os.environ["DEEPSEEK_API_KEY"] = "sk-l5k0LeqnoqudJtEhp4kNCw"
os.environ["DEEPSEEK_API_BASE"] = "https://api.llm.ustc.edu.cn/v1"
from pathlib import Path
os.chdir(Path(__file__).resolve().parent.parent)
sys.path.insert(0, "scripts")
from scrape_n7teahouse import synthesize_answers

# 清理旧 checkpoint
ckpt = Path("data/raw/n7teahouse/n7_qa_checkpoint.json")
if ckpt.exists():
    ckpt.unlink()
    print("已删除旧 checkpoint")

data = json.load(open("data/raw/n7teahouse/n7_candidates.json", encoding="utf-8"))
print(f"全量 {len(data['candidates'])} 条, qwen3.6-chat, 2 并发, 10条/批\n")
synthesize_answers(data["candidates"], model="qwen3.6-chat")
