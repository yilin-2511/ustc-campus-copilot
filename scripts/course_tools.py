"""
教务查询工具 — 供 Router Agent 调用
====================================
调用 catalog.ustc.edu.cn 公开 API 查询课程/考试/教室信息。
无需登录，完全公开。
"""
from __future__ import annotations
import json
import ssl
import urllib.parse
import urllib.request

ssl._create_default_https_context = ssl._create_unverified_context
BASE = "https://catalog.ustc.edu.cn"
HDR = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}


def _fetch(url: str, data: dict | None = None) -> dict | list:
    """通用 API 请求"""
    body = json.dumps(data).encode() if data else None
    method = "POST" if data else "GET"
    req = urllib.request.Request(url, data=body, headers=HDR, method=method)
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def _get_latest_semester() -> str:
    """获取最新学期 code（如 20261）"""
    semesters = _fetch(BASE + "/api/teach/semester/list")
    # 找最新的 isLast 或倒数第二个
    last = [s for s in semesters if s.get("isLast")]
    if last:
        return last[0]["code"]
    # fallback: 倒数第二个（当前学期通常是倒数第二个）
    return semesters[-2]["code"]


def search_courses(keyword: str) -> list[dict]:
    """搜索课程，返回匹配的课程列表"""
    kw = urllib.parse.quote(keyword)
    return _fetch(BASE + "/api/teach/course/search?keyword=" + kw)


def get_course_detail(codes: list[str]) -> list[dict]:
    """获取课程详情（学分、考核方式、教材等）"""
    return _fetch(BASE + "/api/teach/course/infos", {"codes": codes})


def get_lesson_info(codes: list[str], semester: str | None = None) -> list[dict]:
    """获取课程的上课时间/地点/教师"""
    if semester is None:
        semester = _get_latest_semester()
    return _fetch(BASE + "/api/teach/lesson/infos", {"codes": codes, "semester": semester})


def search_course_info(keyword: str, query_type: str) -> str:
    """
    Router Agent 的 search_course_info 工具实现。

    Args:
        keyword: 课程名称关键词
        query_type: course_schedule | exam_schedule | classroom_availability
    """
    type_names = {
        "course_schedule": "全校开课查询",
        "exam_schedule": "考试查询",
        "classroom_availability": "教室使用情况查询",
    }
    type_name = type_names.get(query_type, query_type)

    # 教室和考试查询直接给链接（timetable API 数据太大）
    if query_type in ("exam_schedule", "classroom_availability"):
        return (
            "{}功能请直接访问教务公共查询：\n"
            "  URL: https://catalog.ustc.edu.cn/query/{}\n"
            "  无需登录，完全公开。选择相应查询类型即可。\n"
            "  提示：教室查询选具体教学楼+日期即可看到每节课的占用/空闲状态。"
        ).format(type_name, query_type)

    # 课程查询：通过 API 搜索
    if query_type == "course_schedule":
        try:
            courses = search_courses(keyword)
        except Exception as e:
            return "课程搜索失败: {}。请直接访问 https://catalog.ustc.edu.cn/query/lesson 查询。".format(e)

        if not courses:
            return (
                "未找到与「{}」相关的课程。\n"
                "建议：\n"
                "  1. 尝试更短的课程名（如 '数学分析' 而非 '数学分析B1'）\n"
                "  2. 直接访问 https://catalog.ustc.edu.cn/query/lesson 浏览全部课程"
            ).format(keyword)

        # 取 top-5 课程，获取详情和开课信息
        top5 = courses[:5]
        codes = [c["number"] for c in top5]

        # 并行获取详情
        try:
            details = {c["code"]: c for c in get_course_detail(codes)} if codes else {}
        except Exception:
            details = {}

        try:
            semester = _get_latest_semester()
            lessons = get_lesson_info(codes, semester)
        except Exception:
            lessons = []
            semester = ""

        lines = ["找到 {} 门与「{}」相关的课程：\n".format(len(courses), keyword)]
        for c in top5:
            code = c["number"]
            name = c.get("name", "")
            dept = c.get("dept", "")
            last = c.get("lastTerm") or "未知"

            detail = details.get(code, {})
            credit = detail.get("credit", "?")
            grading = detail.get("grading", "")
            exam = detail.get("examType", "")

            lines.append("【{}】{} ({}学分)".format(name, code, credit))
            lines.append("  开课院系: {} | 最近开课: {}".format(dept, last))
            if grading:
                lines.append("  评分制: {} | 考核: {}".format(grading, exam))

            # 上课时间地点
            course_lessons = [l for l in lessons if l.get("code") == code]
            if course_lessons:
                lines.append("  上课安排:")
                for l in course_lessons[:3]:
                    teachers = l.get("teachers", "")
                    room = l.get("room", "")
                    schedule = l.get("schedule", "")
                    if isinstance(schedule, dict):
                        schedule = " ".join(
                            "{} {}".format(k, v) for k, v in schedule.items()
                        )
                    lines.append(
                        "    教师: {} | 教室: {} | 时间: {}".format(
                            teachers, room, str(schedule)[:80]
                        )
                    )
            lines.append("")

        lines.append(
            "更多课程请访问: https://catalog.ustc.edu.cn/query/lesson（无需登录）"
        )
        return "\n".join(lines)

    return "未知查询类型: {}".format(query_type)


if __name__ == "__main__":
    import sys

    kw = sys.argv[1] if len(sys.argv) > 1 else "数学分析"
    print("=== 课程搜索: {} ===".format(kw))
    print(search_course_info(kw, "course_schedule"))
