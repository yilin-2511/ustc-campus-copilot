"""
构建 campus_platforms 微型 RAG
================================
数据源:
  1. platform_routing.json (44 官方平台)
  2. USTC 不完全入学指南 (erictianc.github.io)
  3. USTC 新手村攻略 (gitee.com/yssickjgd)
  4. qq_groups.json (90个QQ群)
输出: ChromaDB collection "campus_platforms"
用法: python scripts/build_platform_rag.py
"""
from __future__ import annotations
import os as _os
_os.environ.setdefault("TQDM_DISABLE", "1")

import json
import re
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ssl._create_default_https_context = ssl._create_unverified_context
HDR = {"User-Agent": "Mozilla/5.0"}


def fetch_text(url: str) -> str:
    """抓取网页文本"""
    req = urllib.request.Request(url, headers=HDR)
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.read().decode("utf-8", errors="replace")


def extract_guide_chapters(search_json_url: str) -> list[dict]:
    """从 mkdocs search_index.json 提取指南章节"""
    data = json.loads(fetch_text(search_json_url))
    pages: dict[str, dict] = {}
    for doc in data["docs"]:
        loc = doc["location"]
        base = loc.split("#")[0] if loc else ""
        if not base or len(base) < 3:
            continue
        if base not in pages:
            text = re.sub(r"<[^>]+>", "", doc.get("text", ""))[:250]
            text = re.sub(r"\s+", " ", text).strip()
            pages[base] = {"title": doc["title"], "text": text, "url": base}

    skip = {"目录", "序", "声明", "结语", "致谢", "更新日志", "编者", "SUMMARY"}
    entries = []
    for base, info in pages.items():
        if any(kw in info["title"] for kw in skip):
            continue
        if len(info["text"]) < 20:
            continue
        entries.append({
            "text": "新生指南: " + info["title"] + ". " + info["text"],
            "name": info["title"],
            "url": "https://erictianc.github.io/USTCGUIDE_mkdocs/" + base,
            "type": "guide",
            "source": "USTC不完全入学指南",
        })
    return entries


def extract_freshman_guide(readme_url: str) -> list[dict]:
    """从 USTC新手村攻略 README 提取章节"""
    md = fetch_text(readme_url)
    # Split by ## headers
    sections = re.split(r"\n## ", md)
    entries = []
    for sec in sections:
        title_line = sec.split("\n")[0].strip()
        # Clean title
        title = re.sub(r"^##\s*", "", title_line).strip()
        if not title or title in ("概要",):
            continue
        # Extract meaningful text (skip markdown formatting, keep content)
        body = sec[len(title_line):].strip()
        body_clean = re.sub(r"#{2,4}\s*", "", body)
        body_clean = re.sub(r"[-*]\s+", "", body_clean)
        body_clean = re.sub(r"\n+", " ", body_clean)[:300].strip()
        if len(body_clean) < 30:
            continue
        entries.append({
            "text": "新生攻略: " + title + ". " + body_clean,
            "name": title,
            "url": "https://gitee.com/yssickjgd/ustc_freshman",
            "type": "guide",
            "source": "USTC新手村攻略",
        })
    return entries


def main():
    entries = []

    # 1. 官方平台
    with open(ROOT / "data" / "platform_routing.json", "r", encoding="utf-8") as f:
        platforms = json.load(f)
    for p in platforms:
        entries.append({
            "text": "校园平台: " + p["name"] + ". " + p["description"] + " "
                    + "关键词: " + " ".join(p.get("keywords", [])),
            "name": p["name"],
            "url": p["url"],
            "type": "platform",
            "source": "科大官方/半官方平台",
        })
    print(f"  Platforms: {len(platforms)}")

    # 2. USTC 不完全入学指南
    guide_chapters = extract_guide_chapters(
        "https://erictianc.github.io/USTCGUIDE_mkdocs/search/search_index.json"
    )
    entries.extend(guide_chapters)
    print(f"  Guide chapters: {len(guide_chapters)}")

    # 3. USTC 新手村攻略
    freshman = extract_freshman_guide(
        "https://gitee.com/yssickjgd/ustc_freshman/raw/master/README.md"
    )
    entries.extend(freshman)
    print(f"  Freshman guide: {len(freshman)}")

    # 4. QQ 群
    qq_file = ROOT / "data" / "qq_groups.json"
    if qq_file.exists():
        with open(qq_file, "r", encoding="utf-8") as f:
            qq_groups = json.load(f)
        for g in qq_groups:
            entries.append({
                "text": "QQ群: " + g["name"] + ". 群号: " + g["number"]
                        + "（在QQ中搜索群号即可加入）. 分类: " + g.get("category", ""),
                "name": g["name"],
                "url": "tencent://groupwpa/?subcmd=all&param=groupUin%3D" + g["number"],
                "type": "qq_group",
                "source": "QQ群",
            })
        print(f"  QQ groups: {len(qq_groups)}")

    # 5. 校园地标（手动整理，防止 LLM 幻觉）
    landmarks_file = ROOT / "data" / "campus_landmarks.json"
    if landmarks_file.exists():
        with open(landmarks_file, "r", encoding="utf-8") as f:
            landmarks = json.load(f)
        for lm in landmarks:
            if not lm.get("name"):
                continue
            entries.append({
                "text": "校园地标: " + lm["name"] + "。位置: " + lm["location"]
                        + "。类别: " + lm.get("category", "") + "。"
                        + lm.get("note", ""),
                "name": lm["name"],
                "url": "",
                "type": "landmark",
                "source": "校园地标（手动整理）",
            })
        print(f"  Landmarks: {len([lm for lm in landmarks if lm.get('name')])}")

    print(f"\n  Total entries: {len(entries)}")

    # Build ChromaDB
    print("\n  Building ChromaDB collection...")
    import chromadb
    from chromadb.utils.embedding_functions import (
        SentenceTransformerEmbeddingFunction,
    )

    _model_dir = ROOT / "models" / "xrunda" / "m3e-base"
    embed_model = str(_model_dir) if _model_dir.exists() else "xrunda/m3e-base"
    ef = SentenceTransformerEmbeddingFunction(model_name=embed_model)
    if hasattr(ef, '_model') and ef._model is not None:
        ef._model.show_progress_bar = False
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))

    try:
        client.delete_collection("campus_platforms")
    except Exception:
        pass

    collection = client.create_collection(
        name="campus_platforms",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Batch insert
    texts = [e["text"] for e in entries]
    ids = [f"p{i:04d}" for i in range(len(entries))]
    metadatas = [
        {"name": e["name"], "url": e["url"], "type": e["type"], "source": e["source"]}
        for e in entries
    ]
    collection.add(documents=texts, metadatas=metadatas, ids=ids)

    print(f"  Collection: {collection.count()} entries")
    print("  Done!")


if __name__ == "__main__":
    main()
