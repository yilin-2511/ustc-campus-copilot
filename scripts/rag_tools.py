"""
RAG 知识库查询工具 — 供 Router Agent 调用
===========================================
封装 ChromaDB 查询，返回结构化结果供 LLM 合成回答。
SentenceTransformerEmbeddingFunction 内部有类级别模型缓存，
相同 model_name 只加载一次权重，后续查询直接复用。
独立运行测试: python scripts/rag_tools.py "保研需要什么条件"
"""
from __future__ import annotations
from pathlib import Path

# 全局关闭 tqdm 进度条（必须在加载模型前设置）
import os as _os
_os.environ.setdefault("TQDM_DISABLE", "1")

ROOT_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = str(ROOT_DIR / "chroma_db")
_MODEL_DIR = ROOT_DIR / "models" / "xrunda" / "m3e-base"
EMBED_MODEL = str(_MODEL_DIR) if _MODEL_DIR.exists() else "xrunda/m3e-base"
COLLECTION_NAME = "campus_knowledge"
TOP_K = 5
SIMILARITY_CUTOFF = 0.5

# 模块级单例 —— embedding function 只创建一次
_client = None
_collection = None


def _get_collection():
    """延迟初始化 ChromaDB 连接（模型只加载一次）"""
    global _client, _collection
    if _collection is None:
        import sys
        import chromadb
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )
        print("[RAG] Loading embedding model (m3e-base, first time only)...", flush=True)
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_collection(
            COLLECTION_NAME, embedding_function=ef
        )
        print("[RAG] Model loaded, ready.", flush=True)
    return _collection


def query_forum_knowledge(
    query: str, top_k: int = TOP_K, cutoff: float = SIMILARITY_CUTOFF
) -> str:
    """
    搜索南七茶馆论坛知识库，返回格式化的文本结果。

    Args:
        query: 用户问题或搜索关键词
        top_k: 返回结果数
        cutoff: 相似度阈值，低于此值的结果被过滤

    Returns:
        格式化文本，包含匹配的 Q&A 条目、相似度、来源链接。
        无结果时返回提示文本。
    """
    try:
        collection = _get_collection()
    except Exception as e:
        return f"[错误] 无法连接知识库: {e}"

    try:
        results = collection.query(query_texts=[query], n_results=top_k)
    except Exception as e:
        return f"[错误] 知识库查询失败: {e}"

    if not results["ids"] or not results["ids"][0]:
        return "知识库中未找到相关内容。建议换个方式提问，或访问 ustc.life 查找更多校园资源。"

    hits = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        similarity = 1 - distance
        if similarity < cutoff:
            continue
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        # 提取答案部分
        answer = doc.split("Answer: ")[-1] if "Answer: " in doc else ""
        answer = answer.split("📎")[0].strip()  # 去掉原文链接后缀
        hits.append({
            "question": meta.get("question", ""),
            "answer": answer[:500],
            "category": meta.get("category", ""),
            "similarity": similarity,
            "source_url": meta.get("source_url", ""),
            "key_points": meta.get("key_points", ""),
        })

    if not hits:
        return "知识库中未找到与你的问题高度相关的内容。以下建议可能对你有帮助：\n1. 换一种更具体的方式提问\n2. 访问 ustc.life 浏览更多校园平台\n3. 直接咨询辅导员或学长学姐"

    # 格式化输出
    lines = [f"共找到 {len(hits)} 条相关经验分享：\n"]
    for i, h in enumerate(hits, 1):
        bar = "🟢" if h["similarity"] > 0.65 else "🟡"
        lines.append(
            f"[{i}] {bar} 相似度 {h['similarity']:.0%} | {h['category']}"
        )
        lines.append(f"Q: {h['question']}")
        lines.append(f"A: {h['answer'][:350]}")
        lines.append(f"📎 原帖: {h['source_url']}")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 独立测试
# ============================================================
if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "保研需要什么条件"
    print(f"🔍 查询: {query}\n")
    result = query_forum_knowledge(query)
    print(result)
