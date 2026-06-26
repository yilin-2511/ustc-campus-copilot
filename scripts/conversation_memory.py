"""
对话记忆管理 — 供 Router Agent 使用
====================================
简单的多轮对话历史管理器，支持：
- 添加/获取对话历史
- 按轮数截断 (FIFO)
- 可选 JSONL 持久化（调试用）
"""
from __future__ import annotations


class ConversationMemory:
    """基于列表的对话历史管理器"""

    def __init__(self, max_turns: int = 10, persist_path: str | None = None):
        """
        Args:
            max_turns: 最多保留 N 轮对话（1 轮 = user + assistant）
            persist_path: JSONL 文件路径，None 则不持久化
        """
        self.max_turns = max_turns
        self.persist_path = persist_path
        self._history: list[dict] = []

    def add_turn(self, user_msg: str, assistant_msg: str):
        """记录一轮对话"""
        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": assistant_msg})
        # 截断旧轮次
        max_messages = self.max_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
        # 可选持久化
        if self.persist_path:
            self._append_to_file(user_msg, assistant_msg)

    def get_history(self) -> list[dict]:
        """返回对话历史（不含 system prompt）"""
        return list(self._history)

    def clear(self):
        """清空历史"""
        self._history = []

    def conversation_summary(self) -> str:
        """返回对话摘要（用于调试）"""
        if not self._history:
            return "(empty)"
        turns = []
        for i in range(0, len(self._history), 2):
            u = self._history[i]["content"][:60]
            a = (
                self._history[i + 1]["content"][:60]
                if i + 1 < len(self._history)
                else "..."
            )
            turns.append(f"  [{i//2+1}] U: {u}...")
            turns.append(f"      A: {a}...")
        return "\n".join(turns)

    def _append_to_file(self, user_msg: str, assistant_msg: str):
        """追加一行 JSON 到持久化文件"""
        import json

        try:
            with open(self.persist_path, "a", encoding="utf-8") as f:
                json.dump(
                    {"user": user_msg, "assistant": assistant_msg},
                    f,
                    ensure_ascii=False,
                )
                f.write("\n")
        except Exception:
            pass  # 持久化失败不影响主流程
