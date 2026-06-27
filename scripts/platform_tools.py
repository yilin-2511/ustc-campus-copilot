"""
校园平台路由工具 — 供 Router Agent 调用
========================================
基于 ChromaDB 语义搜索，从 170 条数据源中匹配最佳平台/指南/QQ群。
数据源: 44 官方平台 + 29 入学指南章节 + 5 新手攻略 + 90 QQ群

独立运行测试: python scripts/platform_tools.py "怎么查成绩"
"""
from __future__ import annotations
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = str(ROOT_DIR / "chroma_db")
_MODEL_DIR = ROOT_DIR / "models" / "xrunda" / "m3e-base"
EMBED_MODEL = str(_MODEL_DIR) if _MODEL_DIR.exists() else "xrunda/m3e-base"
COLLECTION_NAME = "campus_platforms"

# 模块级单例
_collection = None


def _get_collection():
    """延迟初始化 ChromaDB 连接"""
    global _collection
    if _collection is None:
        import chromadb
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = client.get_collection(COLLECTION_NAME, embedding_function=ef)
    return _collection


def navigate_to_platform(question: str, n_results: int = 3) -> str:
    """
    语义搜索最匹配的平台/指南/QQ群。

    Args:
        question: 用户问题
        n_results: 返回结果数

    Returns:
        格式化的推荐文本，包含名称、URL、类型和来源。
        无匹配时返回 ustc.life 兜底建议。
    """
    try:
        collection = _get_collection()
    except Exception as e:
        return (
            "平台路由服务暂不可用（{}）。\n"
            "建议直接访问 USTC 导航 https://ustc.life/ 查找所需平台。".format(e)
        )

    try:
        results = collection.query(query_texts=[question], n_results=n_results)
    except Exception as e:
        return "平台查询失败: {}".format(e)

    if not results["ids"] or not results["ids"][0]:
        return (
            "未找到与你问题匹配的校园平台或指南。\n"
            "建议访问 USTC 导航 https://ustc.life/ 浏览全部校园平台。"
        )

    hits = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        similarity = 1 - distance
        if similarity < 0.4:  # 相似度太低的不展示
            continue
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        hits.append({
            "name": meta.get("name", ""),
            "url": meta.get("url", ""),
            "type": meta.get("type", ""),
            "source": meta.get("source", ""),
            "similarity": similarity,
        })

    if not hits:
        return (
            "未找到与你问题高度匹配的校园平台或指南。\n"
            "建议访问 USTC 导航 https://ustc.life/ 浏览全部校园平台。"
        )

    # 格式化输出
    type_labels = {
        "platform": "官方平台",
        "guide": "新生指南",
        "qq_group": "QQ群",
    }
    lines = ["找到 {} 个相关结果:\n".format(len(hits))]
    for i, h in enumerate(hits, 1):
        label = type_labels.get(h["type"], h["type"])
        bar = "🟢" if h["similarity"] > 0.65 else "🟡"
        lines.append(
            "[{}] {} {} | {} | 来源: {}".format(
                i, bar, h["name"], label, h["source"]
            )
        )
        lines.append("    URL: {}".format(h["url"]))
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 独立测试
# ============================================================
if __name__ == "__main__":
    import sys

    test_queries = (
        sys.argv[1:]
        if len(sys.argv) > 1
        else [
            "怎么查成绩",
            "教室设备坏了去哪里报修",
            "中区宿舍怎么样",
            "保研失败了怎么办",
            "期末复习有什么技巧",
        ]
    )

    for q in test_queries:
        print("\n🔍 问题: {}".format(q))
        print("-" * 50)
        result = navigate_to_platform(q)
        print(result)
