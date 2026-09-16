import json
import time
from pathlib import Path
from typing import Dict, List, Optional

def estimate_tokens(text: str) -> int:
    """Heuristic token estimation:
    - CJK characters roughly count as 1 token each.
    - Non-CJK words/whitespace/punctuation roughly count as ~4 chars per token.
    """
    if not text:
        return 0
    cjk_count = 0
    other_chars = 0
    for char in text:
        # Unicode range for CJK Unified Ideographs
        if '\u4e00' <= char <= '\u9fff' or '\u3400' <= char <= '\u4dbf':
            cjk_count += 1
        else:
            other_chars += 1
    return cjk_count + max(1, (other_chars + 3) // 4)

class SessionManager:
    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_context_tokens: int = 8192,
        session_id: Optional[str] = None,
    ):
        self.system_prompt = system_prompt
        self.max_context_tokens = max_context_tokens
        self.session_id = session_id or f"session_{int(time.time())}"
        self.messages: List[Dict[str, str]] = []
        self.created_at = time.time()

    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self._prune_context_if_needed()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self._prune_context_if_needed()

    def clear(self) -> None:
        self.messages.clear()

    def get_messages(self) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend(self.messages)
        return result

    def total_estimated_tokens(self) -> int:
        total = 0
        if self.system_prompt:
            total += estimate_tokens(self.system_prompt) + 4
        for msg in self.messages:
            total += estimate_tokens(msg.get("content", "")) + 4
        return total

    def _prune_context_if_needed(self) -> None:
        """Sliding window: prune oldest messages while preserving conversation coherence.
        Ensures system prompt is never pruned.
        """
        while len(self.messages) > 2 and self.total_estimated_tokens() > self.max_context_tokens:
            # Remove the oldest message pair (usually user + assistant)
            self.messages.pop(0)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "estimated_tokens": self.total_estimated_tokens(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionManager":
        manager = cls(
            system_prompt=data.get("system_prompt"),
            session_id=data.get("session_id"),
        )
        manager.created_at = data.get("created_at", time.time())
        manager.messages = data.get("messages", [])
        return manager

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_json(cls, path: Path) -> "SessionManager":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def save_markdown(self, path: Path) -> None:
        lines: List[str] = [f"# Chat Session: {self.session_id}\n\n"]
        if self.system_prompt:
            lines.append(f"> **System**: {self.system_prompt}\n\n---\n\n")
        for msg in self.messages:
            role = "**You**" if msg["role"] == "user" else "**Assistant**"
            lines.append(f"{role}:\n\n{msg['content']}\n\n---\n\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(lines), encoding="utf-8")

# For backward compatibility
Session = SessionManager
