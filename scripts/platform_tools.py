"""
校园平台路由工具 — 供 Router Agent 调用
========================================
从 platform_routing.json 加载 44 个校园平台，
根据用户问题关键词匹配推荐最合适的平台。
独立运行测试: python scripts/platform_tools.py "怎么查成绩"
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PLATFORM_FILE = ROOT_DIR / "data" / "platform_routing.json"

# 模块级缓存
_platforms: list[dict] | None = None


def load_platforms() -> list[dict]:
    """加载全部平台数据，模块级缓存"""
    global _platforms
    if _platforms is not None:
        return _platforms
    with open(PLATFORM_FILE, "r", encoding="utf-8") as f:
        _platforms = json.load(f)
    return _platforms


def match_platform(question: str) -> dict | None:
    """
    根据用户问题匹配最相关的校园平台。

    算法：关键词命中 + routeRules 文本重叠度双层打分。
    返回得分最高的平台 dict，无匹配时返回 None。
    """
    platforms = load_platforms()
    question_lower = question.lower()

    scored = []
    for p in platforms:
        score = 0.0

        # 第一层：关键词命中（每个命中 +2 分）
        for kw in p.get("keywords", []):
            if kw.lower() in question_lower:
                score += 2.0

        # 第二层：routeRules 的 when 文本重叠度
        for rule in p.get("routeRules", []):
            when_text = rule.get("when", "")
            # 提取 when 中的实义词
            when_lower = (
                when_text.replace("用户", "")
                .replace("咨询", "")
                .replace("问", "")
                .replace("想", "")
                .replace("需要", "")
                .replace("是否", "")
                .lower()
            )
            # 计算字符级重叠
            overlap = sum(1 for c in when_lower if c in question_lower)
            score += overlap * 0.02  # 小权重

        if score > 0:
            scored.append((score, p))

    if not scored:
        return None

    scored.sort(key=lambda x: -x[0])

    # 低于阈值视为不匹配
    if scored[0][0] < 1.5:
        return None

    return scored[0][1]


def format_platform_result(platform: dict | None, question: str = "") -> str:
    """
    将平台匹配结果格式化为 LLM 可读的文本。

    如果 platform 为 None，返回 ustc.life 兜底建议。
    """
    if platform is None:
        return (
            "未找到与你的问题完全匹配的校园平台。\n"
            "建议访问 USTC 导航 (https://ustc.life/)，它聚合了 60+ 个校园网站，"
            "按学习/生活/技术分类，可以快速找到你需要的平台。\n"
            "或者更具体地描述你的需求，比如 '怎么查成绩'、'哪里报修教室设备'。"
        )

    login_note = (
        "需要 CAS 统一身份认证登录（学号+密码）。"
        if platform.get("needLogin")
        else "无需登录，直接访问。"
    )

    lines = [
        f"推荐平台：{platform['name']}",
        f"网址：{platform['url']}",
        f"用途：{platform['description']}",
        f"登录要求：{login_note}",
        f"使用提示：{platform.get('tips', '')}",
    ]
    return "\n".join(lines)


def navigate_to_platform(question: str) -> str:
    """
    Router Agent 的 navigate_to_platform 工具实现。
    接收用户问题，返回格式化平台推荐文本。
    """
    platform = match_platform(question)
    return format_platform_result(platform, question)


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
            "想找空教室自习",
            "怎么选课",
            "保研失败了怎么办",  # 应该匹配不到（经验类问题）
        ]
    )

    for q in test_queries:
        print(f"\n🔍 问题: {q}")
        print("-" * 50)
        result = navigate_to_platform(q)
        print(result)
