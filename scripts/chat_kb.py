"""
校园 Copilot 知识库交互式查询（含 LLM query 重写）
用法: python scripts/chat_kb.py
"""
import os, sys, json
from pathlib import Path
os.chdir(Path(__file__).resolve().parent.parent)
sys.path.insert(0, "scripts")

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# 加载嵌入模型
_MODEL_DIR = Path("models/xrunda/m3e-base")
EMBED_MODEL = str(_MODEL_DIR) if _MODEL_DIR.exists() else "xrunda/m3e-base"
embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

client = chromadb.PersistentClient(path="chroma_db")
collection = client.get_collection("campus_knowledge", embedding_function=embedding_fn)

# LLM query 重写（从环境变量读取 API Key）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.llm.ustc.edu.cn/v1")
REWRITE_MODEL = os.environ.get("ROUTER_MODEL", "deepseek-v4-pro")
from openai import OpenAI
llm = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_BASE)

def rewrite_query(query):
    """用 LLM 扩展查询词，消歧短词和黑话"""
    try:
        r = llm.chat.completions.create(
            model=REWRITE_MODEL,
            messages=[{"role": "system", "content": f"你是中科大校园知识库的查询助手。知识库包含{collection.count()}条问答，来自科大论坛\"南七茶馆\"，涵盖：保研/升学、选课/课程、生活/校园、心理/成长、求职/实习、技术/教程、学分/政策等主题。用户会使用缩写（计科=计算机科学）、黑话（暑研=暑期科研实习、妮可=科大、卷=竞争激烈）、口语化表达。你的任务是把用户输入扩展成完整、具体的关键词检索查询，补充同义词和相关概念。必须比原文更长更详细。只输出扩展结果。"},
                      {"role": "user", "content": f"用户问: {query}\n扩展查询:"}],
            temperature=0, max_tokens=80)
        rewritten = r.choices[0].message.content
        if rewritten:
            return rewritten.strip()
    except:
        pass
    return None

print(f"\n校园 Copilot 知识库 — {collection.count()} 条知识")
print("输入问题开始检索，输入 q 退出\n")

while True:
    query = input("🔍 你有什么问题？> ").strip()
    if not query:
        continue
    if query.lower() in ("q", "quit", "exit"):
        print("再见 👋")
        break

    # LLM 重写查询（消除歧义和黑话）
    rewritten = rewrite_query(query)
    if rewritten:
        print(f"   🖊️ {rewritten}")
        query = rewritten

    results = collection.query(query_texts=[query], n_results=3)

    print(f"\n找到 {len(results['ids'][0])} 条相关结果:\n")
    for i in range(len(results["ids"][0])):
        dist = results["distances"][0][i]
        sim = 1 - dist
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]

        bar = "🟢" if sim > 0.65 else "🟡" if sim > 0.50 else "🔴"
        print(f"{bar} [{i+1}] 相似度 {sim:.1%}")
        print(f"   Q: {meta.get('question','')}")
        print(f"   📂 {meta.get('category','')} | {meta.get('source_url','')}")

        ans = doc.split("Answer: ")[-1] if "Answer: " in doc else ""
        ans = ans.split("📎")[0].strip()[:250]
        print(f"   A: {ans}")
        print()
    print("💡 知识库可能未完全涵盖你的问题。如果回答不够准确，可以点击原帖链接查看完整讨论，或换一种方式提问。")
