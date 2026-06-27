"""
南七茶馆数据采集 — Q&A 知识提取版
=====================================

核心理念：从论坛求助帖中提取"问题 → 精华回答"知识对，而非归档原始帖子。
直接喂给 RAG 知识库，让用户无需翻帖子即可获得实用建议。

流程：
  ① 只抓知识型标签（求助&答疑、生涯规划、保研/考研、课程/学术、校园生活、校园攻略、信息发布、技术、已解决）
  ② 按回复数 + 点赞信号筛选"有解答价值"的帖子
  ③ 提取高赞/被引用回复 → LLM 合成一段完整、可操作的答案
  ④ 输出结构化 Q&A JSON，按主题分类

使用方式：
  python scrape_n7teahouse.py                    # 完整采集（含 LLM 合成）
  python scrape_n7teahouse.py --no-synthesis      # 仅抓取+筛选，不做 LLM 合成
  python scrape_n7teahouse.py --synthesis-only    # 基于已有数据，仅做 LLM 合成

环境变量：
  DEEPSEEK_API_KEY    DeepSeek API Key（比赛提供）
  DEEPSEEK_API_BASE   DeepSeek API Base URL（校内地址）
  SYNTHESIS_MODEL     模型名（默认 deepseek-v4）
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path
from json_repair import repair_json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper import fetch_json, save_json, load_json, DATA_RAW

# ============================================================
# 配置
# ============================================================

API_BASE = "https://ustcforum.com/api/discussions"
PAGE_SIZE = 50
REQUEST_DELAY = 1.0          # 列表请求间隔（秒）
DETAIL_DELAY = 1.5           # 详情请求间隔（秒）
DETAIL_WORKERS = 5            # 详情请求并发数

# ---- 只抓知识型标签 ----
KNOWLEDGE_TAGS = [
    ("help",        "求助&答疑"),
    ("career",      "生涯规划"),
    ("graduate",    "保研/考研"),
    ("academic",    "课程/学术"),
    ("campus",      "校园生活"),
    ("guide",       "校园攻略"),
    ("information", "信息发布"),
    ("technology",  "技术"),
    ("solved",      "已解决"),
]

# ---- 筛选阈值 ----
MIN_REPLIES = 3              # 帖子至少 3 条回复才有讨论价值
MIN_LIKES_FOR_VALUE = 1      # 单条回复至少 1 赞就算"有用"
MAX_REPLIES_PER_POST = 6     # 每条帖子最多保留的回复数（取 top-N）

# ---- LLM 合成 ----
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "qwen3.6-chat")
MAX_SYNTHESIS_CHARS = 8000   # 单次合成最大输入字符数
SYNTHESIS_WORKERS = 4         # LLM 合成并发数

# ---- 输出 ----
OUTPUT_SUBDIR = "n7teahouse"


# ============================================================
# Phase 1: 帖子列表采集
# ============================================================

def scrape_tag_posts(tag_slug: str, tag_name: str, max_pages: int = 50) -> list[dict]:
    """分页抓取标签下所有帖子（仅标题和元数据）"""
    posts = []
    for page in range(max_pages):
        offset = page * PAGE_SIZE
        url = f"{API_BASE}?filter[tag]={tag_slug}&page[limit]={PAGE_SIZE}&page[offset]={offset}"
        print(f"  [{tag_name}] 第 {page+1} 页 ...", end=" ")

        try:
            data = fetch_json(url)
            items = data.get("data", [])
            if not items:
                print("无更多数据")
                break

            for p in items:
                attrs = p["attributes"]
                posts.append({
                    "id": p["id"],
                    "title": attrs.get("title", ""),
                    "slug": attrs.get("slug", ""),
                    "comment_count": attrs.get("commentCount", 0),
                    "participant_count": attrs.get("participantCount", 0),
                    "created_at": attrs.get("createdAt", ""),
                    "last_posted_at": attrs.get("lastPostedAt", ""),
                    "view_count": attrs.get("viewCount", 0),
                    "tag_slug": tag_slug,
                    "tag_name": tag_name,
                })

            print(f"{len(items)} 条 (累计 {len(posts)})")
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"错误: {e}")
            break

    return posts


def scrape_all_tags(max_pages: int = 50) -> dict[str, list[dict]]:
    """抓取所有知识标签的帖子（按帖子 ID 去重）"""
    print("=" * 60)
    print("Phase 1: 采集帖子列表")
    print("=" * 60)

    all_posts = {}
    seen_ids = set()  # 已见过的帖子 ID（用于去重）
    total = 0
    duplicates = 0

    for tag_slug, tag_name in KNOWLEDGE_TAGS:
        print(f"\n📂 [{tag_name}] (slug={tag_slug})")
        posts = scrape_tag_posts(tag_slug, tag_name, max_pages)

        # 去重：只保留未见过的新帖子
        unique_posts = []
        for p in posts:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                unique_posts.append(p)
            else:
                duplicates += 1

        all_posts[tag_slug] = unique_posts
        total += len(unique_posts)
        print(f"  → {tag_name}: {len(unique_posts)} 条新帖子 (跳过 {len(posts) - len(unique_posts)} 条重复)")

        # 每个标签存一份中间文件
        save_json({"tag_name": tag_name, "posts": unique_posts},
                  f"n7_{tag_slug}_raw.json", subdir=OUTPUT_SUBDIR + "/phase1")

    print(f"\n总计采集: {total} 条帖子 (去重前 {total + duplicates} 条，重复 {duplicates} 条)")
    return all_posts


# ============================================================
# Phase 2: 帖子筛选 + 回复抓取
# ============================================================

def fetch_discussion_detail(discussion_id: str) -> dict | None:
    """获取帖子详情（含所有回复）"""
    url = f"{API_BASE}/{discussion_id}"
    try:
        return fetch_json(url)
    except Exception as e:
        print(f"    ✗ 获取帖子 {discussion_id} 详情失败: {e}")
        return None


def extract_replies(detail: dict) -> list[dict]:
    """
    从帖子详情中提取回复，计算质量评分，按质量排序。
    返回高价值回复列表（纯文本，去除 HTML 标签）。
    """
    included = detail.get("included", [])
    replies = []

    for item in included:
        if item.get("type") != "posts":
            continue

        attrs = item.get("attributes", {})
        number = attrs.get("number", 0)

        # number=1 是首帖（楼主），跳过
        if number <= 1:
            continue

        # 点赞数 — 来自 relationships.likes.data 的数组长度
        likes_data = item.get("relationships", {}).get("likes", {}).get("data", [])
        like_count = len(likes_data) if isinstance(likes_data, list) else 0

        # 被引用数 — 被其他回复引用的次数
        mentioned_data = item.get("relationships", {}).get("mentionedBy", {}).get("data", [])
        mention_count = len(mentioned_data) if isinstance(mentioned_data, list) else 0

        quality_score = like_count + mention_count

        replies.append({
            "number": number,
            "created_at": attrs.get("createdAt", ""),
            "content_html": attrs.get("contentHtml", ""),
            "content_text": attrs.get("contentText", attrs.get("contentHtml", "")),
            "like_count": like_count,
            "mention_count": mention_count,
            "quality_score": quality_score,
            "is_valuable": quality_score >= MIN_LIKES_FOR_VALUE,
        })

    # 按质量评分降序，取 top-N
    replies.sort(key=lambda r: r["quality_score"], reverse=True)
    return replies[:MAX_REPLIES_PER_POST]


def get_first_post_content(detail: dict) -> str:
    """从帖子详情中提取首帖（楼主）的文本内容"""
    included = detail.get("included", [])
    for item in included:
        if item.get("type") != "posts":
            continue
        attrs = item.get("attributes", {})
        if attrs.get("number") == 1:
            return attrs.get("contentText", attrs.get("contentHtml", ""))
    # fallback: 从 data.attributes 取
    data = detail.get("data", {})
    attrs = data.get("attributes", {})
    return attrs.get("contentText", attrs.get("contentHtml", ""))


def filter_and_fetch_replies(all_posts: dict[str, list[dict]]) -> list[dict]:
    """
    筛选有价值帖子 + 拉取回复（并发版）：
      1. 过滤：回复数 >= MIN_REPLIES
      2. 并发请求详情 API，提取回复
      3. 再次过滤：至少有一条回复 quality_score >= MIN_LIKES_FOR_VALUE
    返回候选帖子列表（含回复数据）
    """
    print("\n" + "=" * 60)
    print(f"Phase 2: 筛选帖子 + 并发抓取回复 ({DETAIL_WORKERS} workers)")
    print("=" * 60)

    # ---- 第一步：收集所有待拉取的帖子 ----
    fetch_list = []  # [(post_dict, tag_name), ...]
    for tag_slug, posts in all_posts.items():
        tag_name = next((name for s, name in KNOWLEDGE_TAGS if s == tag_slug), tag_slug)
        worthy = [p for p in posts if p["comment_count"] >= MIN_REPLIES]
        print(f"  [{tag_name}] {len(posts)} 条帖子 → {len(worthy)} 条回复数 ≥ {MIN_REPLIES}")
        for post in worthy:
            fetch_list.append((post, tag_name))

    print(f"\n  共 {len(fetch_list)} 条待拉取详情 → {DETAIL_WORKERS} 并发\n")

    # ---- 第二步：并发拉取详情 ----
    candidates = []
    completed = 0

    def fetch_one(post_tag):
        """拉取单条帖子详情并处理"""
        post, tag_name = post_tag
        detail = fetch_discussion_detail(post["id"])
        if not detail:
            return None
        replies = extract_replies(detail)
        valuable = [r for r in replies if r["is_valuable"]]
        if not valuable:
            return None
        first_post_text = get_first_post_content(detail)
        post["first_post_text"] = first_post_text
        post["replies"] = replies
        post["valuable_reply_count"] = len(valuable)
        post["top_quality_score"] = valuable[0]["quality_score"] if valuable else 0
        return post

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        futures = {pool.submit(fetch_one, item): item for item in fetch_list}
        for f in as_completed(futures):
            completed += 1
            result = f.result()
            if result is not None:
                candidates.append(result)
                print(f"  [{len(candidates)}] ({result['comment_count']}回复, "
                      f"score={result['top_quality_score']}) {result['title'][:50]}...")

    # ---- 第三步：排序 + 保存 ----
    candidates.sort(key=lambda p: p["top_quality_score"], reverse=True)

    print(f"\n筛选结果: {len(fetch_list)} 条检查 → {len(candidates)} 条候选 "
          f"(过滤率 {100*(1-len(candidates)/max(len(fetch_list),1)):.0f}%)")

    # 保存中间结果
    save_json({
        "total_candidates": len(candidates),
        "candidates": candidates,
    }, "n7_candidates.json", subdir=OUTPUT_SUBDIR)

    return candidates


# ============================================================
# Phase 3: LLM 答案合成
# ============================================================

# few-shot 示例放在 system prompt 中（API 可缓存，不重复计费）
SYNTHESIS_SYSTEM_PROMPT = """你是一个校园知识提取助手。根据每个帖子及其回复，提取一条结构化的知识问答。每帖必出，不跳过。

帖子分为两种类型：
- 类型A（求助帖）：标题/正文提问，回复中有解答 → 从回复提取答案
- 类型B（信息帖）：标题/正文直接发布信息（通知、攻略、教程）→ 从正文提炼答案

重点提取以下内容：
1. 具体的建议、地点、联系方式、方法、经验教训
2. 过来人的职业发展、选择经验（即使主帖是闲聊）
3. 可操作的信息（网址、课程名、老师名、流程步骤），保留原文
4. 个人经历、心路历程、心态调整方法，对后来人有共鸣价值
5. 讨论/投票型帖子的共识观点和多元视角

你的回复必须以 { 开头，以 } 结尾。不输出任何解释。

Few-shot 示例：

示例1 — 类型A
输入：
帖子标题: 大一下学期选课有什么推荐的水课？
帖子正文: 想选几门给分好工作量小的公选课
回复: [👍3] 公选课推荐《书法鉴赏》老师人好期末交作品给分90+
[👍2] 《环境与健康》平时不点名期末开卷
输出：
{"post_type":"Q&A","category":"选课/课程","question":"科大有哪些给分好的公选课推荐？","answer":"口碑较好的公选课：《书法鉴赏》期末交作品给分90+；《环境与健康》开卷不点名。选课前确认授课教师是否更换。","key_points":["《书法鉴赏》交作品给分90+","《环境与健康》开卷不点名"],"references":[],"is_temporary":false}

示例2 — 类型B
输入：
帖子标题: 图书馆暑期开放时间调整通知
帖子正文: 7月20日至8月25日东区图书馆8:00-18:00西区闭馆。详情 https://lib.ustc.edu.cn/notice/123
回复: (无)
输出：
{"post_type":"信息发布","category":"通知/公告","question":"暑期图书馆开放时间是怎样的？","answer":"7月20日至8月25日暑期东区图书馆8:00-18:00西区闭馆。需使用图书馆请前往东区。","key_points":["东区8:00-18:00","西区闭馆"],"references":[{"label":"图书馆通知","url":"https://lib.ustc.edu.cn/notice/123"}],"is_temporary":true}

字段说明：
- post_type: "Q&A" | "信息发布"
- category: "保研/升学" | "选课/课程" | "学分/政策" | "生活/校园" | "通知/公告" | "技术/教程" | "心理/成长" | "求职/实习" | "其他"
- question: 精炼成通用情境
- answer: 按信息量自适应，实在无信息也至少写一句总结
- key_points: 2-3个要点
- references: [{"label":"描述","url":"..."}] 没有则 []
- is_temporary: 短期信息为true"""


def build_synthesis_prompt(title: str, first_post: str, replies: list[dict]) -> str:
    """构建 LLM 合成用户输入（仅帖子和回复数据，不含系统指令）"""
    first_post_clean = first_post[:1500] if first_post else "(无正文)"

    reply_lines = []
    for i, r in enumerate(replies):
        text = r.get("content_text", r.get("content_html", ""))[:800]
        reply_lines.append(
            f"[回复{i+1}] 👍{r['like_count']} 💬被引{r['mention_count']}\n{text}\n"
        )
    replies_text = "\n".join(reply_lines)

    return f"""帖子标题: {title}

帖子正文: {first_post_clean}

回复:
{replies_text}"""


def synthesize_answers(candidates: list[dict], model: str = SYNTHESIS_MODEL) -> list[dict]:
    """
    用 LLM 将帖子+回复合成为 Q&A 知识条目（分批 + 并发 + 断点续跑）。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    api_base = os.getenv("DEEPSEEK_API_BASE")
    if not api_key:
        print("\n⚠ 未设置 DEEPSEEK_API_KEY，跳过 LLM 合成。"); return []
    try:
        from openai import OpenAI
    except ImportError:
        print("\n⚠ 未安装 openai 库，跳过 LLM 合成。"); return []
    client = OpenAI(api_key=api_key, base_url=api_base)

    print("\n" + "=" * 60)
    print(f"Phase 3: LLM 答案合成 (模型: {model}, {SYNTHESIS_WORKERS} 并发)")
    print("=" * 60)

    BATCH_SIZE = 10
    CKPT_FILE = str(Path(DATA_RAW) / OUTPUT_SUBDIR / "n7_qa_checkpoint.json")

    qa_entries = []
    processed_ids = set()
    start_idx = 0
    if os.path.exists(CKPT_FILE):
        ckpt = json.load(open(CKPT_FILE, "r", encoding="utf-8"))
        qa_entries = ckpt.get("entries", [])
        processed_ids = set(ckpt.get("processed_ids", []))
        start_idx = ckpt.get("next_idx", 0)
        print(f"  📋 断点恢复: {len(qa_entries)} 条, 从第 {start_idx+1} 条继续\n")

    skip_list = []

    for i in range(start_idx, len(candidates), BATCH_SIZE):
        batch = candidates[i:i + BATCH_SIZE]
        batch_end = min(i + BATCH_SIZE, len(candidates))
        print(f"\n--- 批次 [{i+1}-{batch_end}/{len(candidates)}] ---")

        # 准备本批次待处理项
        batch_items = []  # [(idx, post, valuable), ...]
        batch_map = {}     # idx -> (post, valuable) 供重试查找
        for j, post in enumerate(batch):
            idx = i + j
            if str(post.get("id", "")) in processed_ids:
                continue
            valuable = [r for r in post.get("replies", []) if r.get("is_valuable")]
            if not valuable:
                processed_ids.add(str(post.get("id", "")))
                continue
            batch_items.append((idx, post, valuable))
            batch_map[idx] = (post, valuable)

        if not batch_items:
            continue

        def _process(idx, post, valuable):
            title = post.get("title", "")
            prompt = build_synthesis_prompt(title, post.get("first_post_text", ""), valuable)
            if len(prompt) > MAX_SYNTHESIS_CHARS:
                prompt = prompt[:MAX_SYNTHESIS_CHARS]
            try:
                r = client.chat.completions.create(
                    model=model,
                    messages=[{"role":"system","content":SYNTHESIS_SYSTEM_PROMPT},
                              {"role":"user","content":prompt}],
                    temperature=0.1, max_tokens=1024)
                raw = r.choices[0].message.content
                if not raw: return (idx, None, "API 空返回", 0)
                # 提取 JSON：优先 ```json 块，兜底 { } + json_repair
                clean = raw
                if "```json" in clean:
                    clean = clean.split("```json")[1].split("```")[0].strip()
                elif "```" in clean:
                    clean = clean.split("```")[1].split("```")[0].strip()
                else:
                    start = clean.find('{')
                    end = clean.rfind('}')
                    if start >= 0 and end > start:
                        clean = clean[start:end+1]
                # 先标准解析，失败用 repair 修复
                try:
                    result = json.loads(clean)
                except (json.JSONDecodeError, ValueError):
                    repaired = repair_json(clean)
                    result = json.loads(repaired) if isinstance(repaired, str) else repaired
                if isinstance(result, list):
                    result = result[0] if result else {}
                if isinstance(result, dict) and result.get("answer"):
                    entry = {
                        "id": f"n7-{post['id']}",
                        "question": result.get("question", title),
                        "answer": result.get("answer", "") + f"\n\n📎 原帖：https://ustcforum.com/d/{post['id']}",
                        "category": result.get("category", "其他"),
                        "post_type": result.get("post_type", "Q&A"),
                        "key_points": result.get("key_points", []),
                        "references": result.get("references", []),
                        "is_temporary": result.get("is_temporary", False),
                        "raw_replies": [{"text": r2.get("content_text","")[:1000],
                                         "likes": r2.get("like_count",0),
                                         "quality_score": r2.get("quality_score",0)} for r2 in valuable[:3]],
                        "source": {"platform":"南七茶馆","post_id":post["id"],
                                   "post_title":title,"url":f"https://ustcforum.com/d/{post['id']}",
                                   "tag":post.get("tag_name","")},
                        "quality": {"original_reply_count":post.get("comment_count",0),
                                    "valuable_reply_count":post.get("valuable_reply_count",0),
                                    "top_reply_score":post.get("top_quality_score",0)},
                        "collected_at": datetime.now().isoformat(),
                    }
                    return (idx, entry, None, 0)
                elif isinstance(result, dict):
                    reason = result.get("skip_reason") or ""
                    return (idx, None, "⊘" + (reason[:40] if reason else "无实质信息"), post.get("top_quality_score", 0))
                else:
                    return (idx, None, "JSON: parse type error", post.get("top_quality_score", 0))
            except json.JSONDecodeError as e:
                return (idx, None, f"JSON:{str(e)[:25]}", post.get("top_quality_score",0))
            except Exception as e:
                return (idx, None, f"ERR:{str(e)[:25]}", post.get("top_quality_score",0))

        t0 = time.time()
        ok = skip = err = 0
        total_batch = len(batch_items)
        failed_items = []  # 待重试

        with ThreadPoolExecutor(max_workers=SYNTHESIS_WORKERS) as pool:
            fs = {pool.submit(_process, idx, post, val): idx for idx, post, val in batch_items}
            for f in as_completed(fs):
                idx, entry, msg, score = f.result()
                done = ok + skip + err + 1

                pid = str(candidates[idx].get("id","?"))
                purl = f"https://ustcforum.com/d/{pid}"

                if entry:
                    qa_entries.append(entry); ok += 1
                    processed_ids.add(pid)
                    print(f"  [{done}/{total_batch}] ✓ n7-{pid} | {entry['question'][:45]} | {purl}")
                elif msg and msg.startswith("⊘"):
                    skip += 1
                    processed_ids.add(pid)
                    if score >= 3:
                        skip_list.append({"title":candidates[idx].get("title",""),"score":score,"reason":msg})
                    print(f"  [{done}/{total_batch}] ⊘ n7-{pid} | {msg[1:][:35]} | {purl}")
                else:
                    err += 1
                    print(f"  [{done}/{total_batch}] ✗ n7-{pid} | {msg or '?'} | {purl}")
                    post, val = batch_map[idx]
                    failed_items.append((idx, post, val))

        # ---- 重试失败项 ----
        if failed_items:
            print(f"\n  🔄 重试 {len(failed_items)} 条失败项...")
            retry_ok = 0
            for attempt in range(1, 3):  # 最多2次
                still_failed = []
                for idx, post, val in failed_items:
                    time.sleep(2)  # 重试间隔
                    _, entry, msg, _ = _process(idx, post, val)
                    pid = str(candidates[idx].get("id","?"))
                    purl = f"https://ustcforum.com/d/{pid}"
                    if entry:
                        qa_entries.append(entry); ok += 1; err -= 1; retry_ok += 1
                        processed_ids.add(pid)
                        print(f"    ✓ 重试{attempt}成功 n7-{pid} | {entry['question'][:35]} | {purl}")
                    elif msg and msg.startswith("⊘"):
                        skip += 1; err -= 1
                        processed_ids.add(pid)
                        print(f"    ⊘ 重试{attempt}判定跳过 n7-{pid} | {purl}")
                    else:
                        still_failed.append((idx, post, val))
                failed_items = still_failed
                if not failed_items:
                    break
            for idx, post, val in failed_items:
                pid = str(candidates[idx].get("id","?"))
                processed_ids.add(pid)
                print(f"    ✗ 最终放弃 n7-{pid} | https://ustcforum.com/d/{pid}")

        # batch summary
        elapsed = time.time() - t0
        rate = total_batch / elapsed if elapsed > 0 else 0
        print(f"  批次完成: ✓{ok} ⊘{skip} ✗{len(failed_items)} | {elapsed:.0f}s ({rate:.1f}条/s)")

        ckpt = {"model":model, "total_candidates":len(candidates), "next_idx":batch_end,
                "processed_ids":list(processed_ids), "entries":qa_entries,
                "saved_at":datetime.now().isoformat()}
        with open(CKPT_FILE, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, ensure_ascii=False, indent=2)
        print(f"  💾 checkpoint → {len(qa_entries)} 条知识 | 进度 {batch_end}/{len(candidates)}")

    skipped = len(processed_ids) - len(qa_entries)
    save_json({"source":"南七茶馆","total_entries":len(qa_entries),"total_skipped":skipped,
               "collected_at":datetime.now().isoformat(),"model":model,"entries":qa_entries},
              "n7_qa_knowledge.json", subdir=OUTPUT_SUBDIR)

    by_category = {}
    for e in qa_entries:
        by_category.setdefault(e["category"], []).append(e)
    for cat, entries in by_category.items():
        save_json({"category":cat,"entries":entries}, f"n7_qa_{cat.replace('/','_')}.json", subdir=OUTPUT_SUBDIR)

    print("\n" + "-" * 40)
    print(f"LLM 合成完成: {len(qa_entries)} 条知识, 跳过 {skipped} 条")
    for cat, entries in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"  {cat}: {len(entries)}")
    if skip_list:
        print(f"  高分跳过 ({len(skip_list)}):")
        for s in skip_list:
            print(f"    score={s['score']} {s['title'][:35]} — {s['reason'][:35]}")
    print("-" * 40)
    return qa_entries

# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="南七茶馆 Q&A 知识提取 — 从求助帖中提取精华问答"
    )
    parser.add_argument(
        "--no-synthesis", action="store_true",
        help="仅抓取+筛选，不做 LLM 合成（保存中间结果）"
    )
    parser.add_argument(
        "--synthesis-only", action="store_true",
        help="跳过抓取，基于已有 candidates 数据直接做 LLM 合成"
    )
    parser.add_argument(
        "--max-pages", type=int, default=50,
        help="每个标签最大抓取页数 (默认 50)"
    )
    args = parser.parse_args()

    start_time = time.time()

    if args.synthesis_only:
        # 从已有中间文件加载
        print("从已有数据加载 candidates ...")
        try:
            data = load_json("n7_candidates.json", subdir=OUTPUT_SUBDIR)
            candidates = data.get("candidates", [])
            print(f"加载 {len(candidates)} 条候选帖子")
        except FileNotFoundError:
            print("✗ 未找到 n7_candidates.json，请先运行采集（不加 --synthesis-only）")
            sys.exit(1)

        synthesize_answers(candidates)

    else:
        # Phase 1: 采集
        all_posts = scrape_all_tags(max_pages=args.max_pages)

        # Phase 2: 筛选 + 回复抓取
        candidates = filter_and_fetch_replies(all_posts)

        if not args.no_synthesis and candidates:
            # Phase 3: LLM 合成
            synthesize_answers(candidates)
        else:
            print(f"\n✅ 采集+筛选完成。共 {len(candidates)} 条候选帖子。")
            if args.no_synthesis:
                print("   (已跳过 LLM 合成)")

    elapsed = time.time() - start_time
    print(f"\n⏱ 总耗时: {elapsed/60:.1f} 分钟")


if __name__ == "__main__":
    main()
