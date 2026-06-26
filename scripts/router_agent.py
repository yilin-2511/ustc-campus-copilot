"""
校园 Copilot — Function-Calling Router Agent
=============================================

基于 OpenAI Function Calling 的智能路由 Agent。
根据用户问题自动决定：
  - search_forum_knowledge → RAG 知识库（论坛经验）
  - navigate_to_platform    → 校园平台导航（办事/查询）
  - search_course_info      → 教务数据查询（未来）

用法: python scripts/router_agent.py
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

# 确保工作目录在项目根
os.chdir(Path(__file__).resolve().parent.parent)
sys.path.insert(0, "scripts")

from openai import OpenAI
from rag_tools import query_forum_knowledge
from platform_tools import navigate_to_platform
from conversation_memory import ConversationMemory

# ============================================================
# 配置
# ============================================================
MODEL = os.environ.get("ROUTER_MODEL", "deepseek-v4-pro")
MAX_TOOL_ROUNDS = 3
TEMPERATURE = 0.3

_llm = None  # 延迟初始化


def _get_llm():
    """延迟加载 LLM 客户端（首次调用时加载 API Key）"""
    global _llm
    if _llm is not None:
        return _llm

    env_file = Path(__file__).resolve().parent.parent / ".env"

    # 1. 尝试从 .env 加载
    try:
        from dotenv import load_dotenv
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass

    key = os.environ.get("DEEPSEEK_API_KEY", "")
    base = os.environ.get("DEEPSEEK_API_BASE", "https://api.llm.ustc.edu.cn/v1")

    # 2. 如果还没有，交互式输入
    if not key:
        print()
        print("[API Key] No API Key found. Get one at https://api.llm.ustc.edu.cn")
        try:
            key = input("[API Key] Paste your key: ").strip()
        except EOFError:
            key = ""
        if not key:
            raise RuntimeError(
                "API Key is required. Set DEEPSEEK_API_KEY env variable or create .env file.\n"
                "  cp .env.example .env\n"
                "  # then edit .env with your key"
            )

        # 3. 自动保存
        env_file.write_text(
            "DEEPSEEK_API_KEY={}\nDEEPSEEK_API_BASE={}\n".format(key, base),
            encoding="utf-8"
        )
        print("[API Key] Saved to {}, won't ask again.\n".format(env_file))

    os.environ["DEEPSEEK_API_KEY"] = key
    os.environ["DEEPSEEK_API_BASE"] = base

    _llm = OpenAI(api_key=key, base_url=base)
    return _llm

# ============================================================
# System Prompt
# ============================================================
SYSTEM_PROMPT = """你叫"校园 Copilot"，是中国科学技术大学（USTC）的校园智能助手。
你的目标用户是本科生（尤其是大一新生），你要用友好、耐心的语气帮助他们解决校园生活中的问题。

============================================================
【核心原则：你是导航员，不是百科全书】
============================================================

科大已经有大量优秀的校园平台（教务系统、评课社区、图书馆、校园地图、校医院等）。
你的任务是：
1. 经验类问题 → 搜索论坛知识库，获取学长学姐的真实经历
2. 办事/查询类问题 → 告诉用户去哪个平台、怎么用
3. 常识类问题 → 如果你确定答案，可以直接回答

============================================================
【你的三个工具】
============================================================

工具1: search_forum_knowledge
  什么时候用：
  - 用户问经验/评价/感受类问题：保研怎么准备、某门课难不难、哪个老师好、食堂推荐、宿舍条件、心理焦虑等
  - 用户问攻略/方法类问题：怎么进实验室、暑研怎么申请、转专业经验等
  什么时候不用：
  - 纯客观事实（如图书馆几点关门）→ 你知道就直接回答
  - 需要登录办事（如选课、查成绩）→ 用 navigate_to_platform

工具2: navigate_to_platform
  什么时候用：
  - 用户需要去某个平台办具体事情：查成绩、选课、借书、报修、查课表、交学费等
  - 用户问"怎么查XX""去哪里XX""哪个网站可以XX""XX平台在哪里"
  什么时候不用：
  - 纯经验分享、闲聊、你能直接回答的常识

工具3: search_course_info
  什么时候用：
  - 用户想查具体某门课的上课时间/地点、考试安排、空教室
  - 注意：此功能仍在开发中，会返回教务系统链接供用户自行查询

============================================================
【调用策略】
============================================================

1. 先想：这个问题你能直接回答吗？
   - 能 → 直接回答，不要调用工具
   - 不能 → 选择合适的工具

2. 如果你的回答中提到了具体的校园平台（如"去教务系统查""找空教室""图书馆"等），
   必须同时调用 navigate_to_platform，把平台链接附上。不要让用户自己去找。

3. 经验+平台都要 → 先 search_forum_knowledge 获取经验，
   再 navigate_to_platform 推荐相关平台，最后合成回答。

4. 工具返回空结果 → 如实告知，不要编造。引导用户访问 ustc.life 或咨询辅导员。

5. 同一轮最多调用 3 次工具

============================================================
【回答格式 — Synthesizer】
============================================================

每次回答灵活组织，但一般遵循：

1. 核心答案：先直接回答用户的问题
2. 平台推荐：如果用了 navigate_to_platform，附上平台名称、网址、使用提示
3. 来源说明：
   - 论坛经验 → "来自学长学姐的经验分享，仅供参考"
   - 官方渠道 → 说明信息可靠度
4. 免责：如果需要登录办事，说明"需要 CAS 统一身份认证登录（学号+密码）"

============================================================
【重要约束】
============================================================

- 你只回答与 USTC 相关的问题。非校园问题礼貌表示只回答校园相关问题。
- 不要编造校园平台的信息。如果不确定，引导用户访问 ustc.life。
- 保持友好、亲切的语气。可以适当使用 emoji。
- 回答使用中文。
- 如果用户情绪低落（焦虑、迷茫），先共情，再给建议。
"""

# ============================================================
# Tool Schemas（OpenAI Function Calling 格式）
# ============================================================
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_forum_knowledge",
            "description": (
                "搜索南七茶馆论坛的 RAG 知识库，获取学长学姐的真实经验分享。"
                "适用场景：保研/考研/升学经验、选课避坑、导师评价、食堂/宿舍等校园生活体验、"
                "心理困惑/心态调整、求职实习攻略、技术教程等主观经验类问题。"
                "不适用：纯客观事实查询（如图书馆开放时间）、需要登录办事（如查成绩/选课）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "用户的原始问题或搜索关键词。越具体越好，"
                            "例如 'GPA 2.8 能保研本校吗' 比 '保研' 效果更好。"
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to_platform",
            "description": (
                "根据用户问题推荐最合适的科大校园平台。覆盖 44 个常用平台，"
                "包括教务系统、评课社区、图书馆、校园地图、校医院、一卡通、"
                "迎新网、学工在线、第二课堂、自习预约、报修、缴费、正版软件等。"
                "适用场景：用户需要办事（查成绩/选课/借书/报修）、"
                "用户问'怎么查XX''去哪里XX'、"
                "以及 RAG 回答中提到了具体平台（如'教务系统''空教室'）需要附上链接时。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户的完整问题或需求描述。",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_course_info",
            "description": (
                "查询教务系统公共数据（课程安排、考试安排、教室使用情况）。"
                "注意：此功能仍在开发中，目前返回教务系统链接供用户自行查询。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "课程名称、教师姓名或关键词。",
                    },
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "course_schedule",
                            "exam_schedule",
                            "classroom_availability",
                        ],
                        "description": (
                            "查询类型：course_schedule=开课安排/上课时间地点, "
                            "exam_schedule=考试安排, classroom_availability=空闲教室查询"
                        ),
                    },
                },
                "required": ["keyword", "query_type"],
            },
        },
    },
]

# ============================================================
# Tool 处理器
# ============================================================
def handle_search_knowledge(query: str) -> str:
    """处理 search_forum_knowledge 工具调用"""
    return query_forum_knowledge(query)


def handle_navigate_platform(question: str) -> str:
    """处理 navigate_to_platform 工具调用"""
    return navigate_to_platform(question)


def handle_search_course(keyword: str, query_type: str) -> str:
    """处理 search_course_info 工具调用（占位）"""
    type_names = {
        "course_schedule": "全校开课查询",
        "exam_schedule": "考试查询",
        "classroom_availability": "教室使用情况查询",
    }
    type_name = type_names.get(query_type, query_type)
    return (
        f"该功能正在接入教务系统数据中，暂时无法自动查询。\n"
        f"你可以自行访问教务系统公共查询：https://catalog.ustc.edu.cn/query/\n"
        f"选择「{type_name}」，输入关键词「{keyword}」即可查询。\n"
        f"无需登录，完全公开。"
    )


TOOL_HANDLERS = {
    "search_forum_knowledge": handle_search_knowledge,
    "navigate_to_platform": handle_navigate_platform,
    "search_course_info": handle_search_course,
}

# ============================================================
# LLM 客户端
# ============================================================
# ============================================================
# 对话循环
# ============================================================
def chat(
    user_input: str,
    memory: ConversationMemory,
    stream: bool = False,
) -> str:
    """
    处理单轮用户输入，返回 Agent 回复。

    核心流程：
    1. 构建 messages = system + history + user
    2. LLM 推理 → 可能产生 tool_calls
    3. 执行 tool_calls → 结果追加到 messages
    4. 回到 LLM → 重复（最多 MAX_TOOL_ROUNDS 轮）
    5. 生成最终回答
    """
    # 1. 构建消息列表
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(memory.get_history())
    messages.append({"role": "user", "content": user_input})

    # 2. 工具调用循环
    tool_round = 0
    final_text = ""

    while tool_round < MAX_TOOL_ROUNDS:
        try:
            response = _get_llm().chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=TEMPERATURE,
            )
        except Exception as e:
            error_msg = f"抱歉，LLM 服务暂时不可用（{e}）。请稍后重试。"
            memory.add_turn(user_input, error_msg)
            return error_msg

        msg = response.choices[0].message

        if msg.tool_calls:
            # LLM 决定调用工具
            messages.append(msg)  # 追加 assistant 消息（含 tool_calls）

            for tc in msg.tool_calls:
                func_name = tc.function.name
                try:
                    func_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    func_args = {}

                # 执行工具
                handler = TOOL_HANDLERS.get(func_name)
                if handler:
                    try:
                        result = handler(**func_args)
                    except Exception as e:
                        result = f"[工具执行错误] {func_name}: {e}"
                else:
                    result = f"[未知工具] {func_name}"

                # 追加 tool 结果消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            tool_round += 1
        else:
            # LLM 认为不需要（更多）工具调用 → 最终回答
            final_text = msg.content or ""
            break

    # 3. 如果超过最大轮次仍未出最终答案，强制要求总结
    if tool_round >= MAX_TOOL_ROUNDS and not final_text:
        messages.append({
            "role": "user",
            "content": "请根据以上工具返回的信息，用中文给出最终回答。",
        })
        try:
            final_resp = _get_llm().chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=TEMPERATURE,
            )
            final_text = final_resp.choices[0].message.content or ""
        except Exception as e:
            final_text = f"抱歉，生成回答时出错: {e}"

    # 4. 保存记忆
    if not final_text:
        final_text = "抱歉，我暂时无法回答这个问题。建议访问 ustc.life 查找相关校园平台，或咨询辅导员。"
    memory.add_turn(user_input, final_text)

    return final_text


# ============================================================
# CLI 交互入口
# ============================================================
def main():
    print("\n" + "=" * 55)
    print("  🎓 校园 Copilot — 智能路由助手")
    print("  知识库: 1,215 条论坛经验 | 平台路由: 44 个校园站点")
    print("  输入问题开始，输入 q 退出，输入 /clear 清空对话")
    print("=" * 55 + "\n")

    memory = ConversationMemory(max_turns=10)

    while True:
        try:
            user_input = input("🔍 你有什么问题？> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 👋")
            break

        if not user_input:
            continue

        if user_input.lower() in ("q", "quit", "exit"):
            print("再见 👋")
            break

        if user_input.lower() in ("/clear", "/reset"):
            memory.clear()
            print("✓ 对话已清空\n")
            continue

        if user_input.lower() == "/history":
            print(memory.conversation_summary() + "\n")
            continue

        # 处理输入
        reply = chat(user_input, memory)
        print(f"\n{reply}\n")


if __name__ == "__main__":
    main()
