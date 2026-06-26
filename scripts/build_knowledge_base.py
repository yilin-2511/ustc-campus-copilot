"""
校园 Copilot 知识库构建脚本
================================

读取南七茶馆 Q&A JSON → 向量化 Embedding → ChromaDB 持久化

核心设计：
  每条知识条目 = 一条 Document
  text = "Question: ... \nAnswer: ..."  (两者一起 Embedding)
  metadata = { category, source_url, question, key_points, entry_id }

使用方式：
  python scripts/build_knowledge_base.py                          # 构建知识库
  python scripts/build_knowledge_base.py --rebuild                # 清空重建
  python scripts/build_knowledge_base.py --query "保研需要什么条件"  # 测试检索

输入：data/raw/n7teahouse/n7_qa_knowledge.json（或 n7_qa_{分类}.json）
输出：chroma_db/（ChromaDB 持久化目录）
"""

from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path
from typing import Optional

# ============================================================
# 配置
# ============================================================

CHROMA_DIR = Path(__file__).resolve().parent.parent / "chroma_db"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# 嵌入模型 — m3e-base（中文检索专用，768维）
# 已从 ModelScope 下载到 models/ 目录
import os as _os
_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "xrunda" / "m3e-base"
EMBED_MODEL = str(_MODEL_DIR) if _MODEL_DIR.exists() else "xrunda/m3e-base"

# 检索参数
TOP_K = 5
SIMILARITY_CUTOFF = 0.5
DEFAULT_COLLECTION = "campus_knowledge"  # 默认集合名

# 去重参数
DEDUP_SIMILARITY_THRESHOLD = 0.88  # 余弦相似度超过此值视为重复

# Q&A 数据目录
QA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "n7teahouse"


# ============================================================
# 构建知识库
# ============================================================

def load_qa_entries() -> list[dict]:
    """加载所有 Q&A JSON 文件"""
    # 优先加载汇总文件，失败则加载分类文件
    summary_file = QA_DIR / "n7_qa_knowledge.json"
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        print(f"  从 {summary_file.name} 加载 {len(entries)} 条")
        return entries

    # 从分类文件加载
    entries = []
    for f in sorted(QA_DIR.glob("n7_qa_*.json")):
        if "summary" in f.name or "test" in f.name or "raw" in f.name or "candidates" in f.name:
            continue
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            items = data.get("entries", [])
            entries.extend(items)
            print(f"  从 {f.name} 加载 {len(items)} 条")

    return entries


def build_chunks(entries: list[dict]) -> tuple[list[str], list[dict], list[str]]:
    """
    将 Q&A 条目转换为：
      - texts: 要 Embedding 的文本列表
      - metadatas: 对应的 metadata
      - ids: 唯一 ID 列表
    """
    texts = []
    metadatas = []
    ids = []

    for entry in entries:
        entry_id = entry.get("id", "")
        question = entry.get("question", "")
        answer = entry.get("answer", "")
        category = entry.get("category", "其他")
        key_points = entry.get("key_points", [])
        source = entry.get("source", {})
        quality = entry.get("quality", {})

        if not answer:
            continue

        # 【核心】问题和答案一起作为 Embedding 文本
        # 这样用户问类似问题时能同时匹配到问题和答案中的语义
        text = f"Question: {question}\nAnswer: {answer}"

        # 附加上关键要点作为补充语义
        if key_points:
            text += f"\nKey Points: {'; '.join(key_points)}"

        texts.append(text)
        metadatas.append({
            "entry_id": entry_id,
            "question": question,
            "category": category,
            "source_url": source.get("url", ""),
            "source_tag": source.get("tag", ""),
            "key_points": "; ".join(key_points[:5]),
            "reply_count": quality.get("original_reply_count", 0),
            "quality_score": quality.get("top_reply_score", 0),
        })
        ids.append(entry_id)

    return texts, metadatas, ids


def build_knowledge_base(rebuild: bool = False, collection_name: str = DEFAULT_COLLECTION):
    """读取 Q&A JSON → Embedding → 写入 ChromaDB"""
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    print("=" * 50)
    print("校园 Copilot 知识库构建")
    print("=" * 50)

    # 1. 加载数据
    print("\n📂 加载 Q&A 数据...")
    entries = load_qa_entries()
    if not entries:
        print("  ✗ 未找到知识条目，请先运行 scrape_n7teahouse.py")
        return

    # 2. 构建 chunks
    print("\n📝 构建向量文本...")
    texts, metadatas, ids = build_chunks(entries)
    model_name = EMBED_MODEL.split("\\")[-1] if "\\" in EMBED_MODEL else EMBED_MODEL
    print(f"  {len(texts)} 条文本 → 使用模型: {model_name}")

    # 3. 初始化向量数据库
    print("\n🗄️ 连接 ChromaDB...")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if rebuild:
        try:
            client.delete_collection(collection_name)
            print(f"  ✓ 已清空 {collection_name}")
        except Exception:
            pass

    # 使用 BGE-small-zh-v1.5 中文嵌入模型
    print("  ⏳ 加载中文嵌入模型...")
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},  # 余弦距离
    )

    # 4. 去重 + 写入数据
    print("\n💾 写入向量库...")

    existing_count = collection.count()

    # 第一步：ID 去重（已有同 ID 直接跳过）
    if existing_count > 0:
        existing_ids = set(collection.get()["ids"])
        id_dedup_data = [
            (text, meta, id_) for text, meta, id_
            in zip(texts, metadatas, ids)
            if id_ not in existing_ids
        ]
    else:
        existing_ids = set()
        id_dedup_data = list(zip(texts, metadatas, ids))

    id_skipped = len(texts) - len(id_dedup_data)

    # 第二步：语义去重（与已有条目相似度 > 阈值的跳过）
    final_texts = []
    final_metadatas = []
    final_ids = []
    dup_count = 0

    if existing_count == 0:
        # 新建知识库，无需语义去重
        final_texts = list(texts)
        final_metadatas = list(metadatas)
        final_ids = list(ids)
    elif id_dedup_data:
        dedup_texts, dedup_metas, dedup_ids = zip(*id_dedup_data)
        # 批量查询：每个新文本在已有库中找最相似的
        results = collection.query(
            query_texts=list(dedup_texts),
            n_results=1,
        )
        for i, (text, meta, id_) in enumerate(id_dedup_data):
            top_distance = results["distances"][i][0] if results["distances"][i] else 1.0
            top_similarity = 1 - top_distance
            if top_similarity >= DEDUP_SIMILARITY_THRESHOLD:
                dup_id = results["ids"][i][0] if results["ids"][i] else "?"
                print(f"  ⊘ {id_} 语义重复 → 已有 {dup_id} (相似度 {top_similarity:.1%})")
                dup_count += 1
            else:
                final_texts.append(text)
                final_metadatas.append(meta)
                final_ids.append(id_)
    # else: existing_count > 0 但 id_dedup_data 为空 → 无需写入

    # 统计
    if existing_count > 0:
        print(f"  已有 {existing_count} 条，ID重复跳过 {id_skipped} 条，语义重复跳过 {dup_count} 条")
    if final_texts:
        print(f"  新增 {len(final_texts)} 条")
    else:
        print(f"  无新数据需要写入")

    if final_texts:
        collection.add(
            documents=final_texts,
            metadatas=final_metadatas,
            ids=final_ids,
        )

    print(f"\n✅ 构建完成！")
    print(f"  知识库路径: {CHROMA_DIR}")
    print(f"  集合名: campus_knowledge")
    print(f"  总条目: {collection.count()}")
    print(f"  嵌入模型: {EMBED_MODEL}")
    print(f"  分类分布:")

    # 统计分类
    all_metas = collection.get()["metadatas"]
    categories = {}
    for m in all_metas:
        cat = m.get("category", "其他")
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count} 条")


# ============================================================
# 检索测试
# ============================================================

def query_knowledge_base(query: str, top_k: int = TOP_K, collection_name: str = DEFAULT_COLLECTION):
    """测试检索效果"""
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    print(f"\n🔍 检索: \"{query}\"  [{collection_name}]")
    print("=" * 50)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

    try:
        collection = client.get_collection(
            name=collection_name,
            embedding_function=embedding_fn,
        )
    except Exception as e:
        print(f"  ✗ 未找到知识库，请先运行 build: {e}")
        return

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    if not results["ids"][0]:
        print("  未找到相关结果")
        return

    print(f"\n  找到 {len(results['ids'][0])} 条相关结果:\n")

    for i in range(len(results["ids"][0])):
        entry_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        similarity = 1 - distance
        meta = results["metadatas"][0][i]

        print(f"--- [{i+1}] 相似度: {similarity:.2%} ---")
        print(f"  Q: {meta.get('question', '')}")
        print(f"  分类: {meta.get('category', '')}")
        if meta.get("key_points"):
            print(f"  要点: {meta.get('key_points', '')}")
        print(f"  来源: {meta.get('source_url', '')}")
        print(f"  ID: {entry_id}")
        print()

        # 完整文本
        doc = results["documents"][0][i]
        print(f"  全文预览: {doc[:300]}...")
        print()


def list_knowledge_base(collection_name: str = DEFAULT_COLLECTION):
    """列出知识库统计信息"""
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        print("  ✗ 未找到知识库")
        return

    count = collection.count()
    print(f"\n📊 知识库统计")
    print(f"  总条目: {count}")
    print(f"  路径: {CHROMA_DIR}")
    print(f"  集合: campus_knowledge")

    if count > 0:
        metas = collection.get()["metadatas"]
        categories = {}
        for m in metas:
            cat = m.get("category", "其他")
            categories[cat] = categories.get(cat, 0) + 1
        print(f"  分类分布:")
        for cat, c in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {c} 条")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="校园 Copilot 知识库构建")
    parser.add_argument("--rebuild", action="store_true", help="清空旧知识库重建")
    parser.add_argument("--query", type=str, help="测试检索（输入你的问题）")
    parser.add_argument("--list", action="store_true", help="查看知识库统计")
    parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION, help="集合名称")
    args = parser.parse_args()

    if args.list:
        list_knowledge_base(args.collection)
    elif args.query:
        query_knowledge_base(args.query, collection_name=args.collection)
    else:
        build_knowledge_base(rebuild=args.rebuild, collection_name=args.collection)


if __name__ == "__main__":
    main()
