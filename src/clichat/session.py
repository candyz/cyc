import json
import time
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_SESSIONS_DIR = Path.home() / ".local" / "share" / "clichat" / "sessions"

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
        provider: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        sessions_dir: Optional[Path] = None,
    ):
        self.system_prompt = system_prompt
        self.max_context_tokens = max_context_tokens
        self.session_id = session_id or f"session_{int(time.time())}"
        self.provider = provider
        self.model = model
        self.mode = mode
        self.sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        self.messages: List[Dict] = []
        self.created_at = time.time()
        self.updated_at = time.time()
        self.history_checkpoints: List[List[Dict]] = []

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        self.system_prompt = prompt
        self.auto_save()

    def add_user_message(self, content: str) -> None:
        # Save snapshot of messages before starting a new user interaction turn
        import copy
        self.history_checkpoints.append(copy.deepcopy(self.messages))
        # Keep maximum 20 undo checkpoints in memory
        if len(self.history_checkpoints) > 20:
            self.history_checkpoints.pop(0)

        self.messages.append({"role": "user", "content": content})
        self.updated_at = time.time()
        self._prune_context_if_needed()
        self.auto_save()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self.updated_at = time.time()
        self._prune_context_if_needed()
        self.auto_save()

    def undo_turn(self) -> bool:
        """Roll back conversation messages to the state before the last user turn.
        Returns True if rollback succeeded, False if no checkpoints available.
        """
        if not self.history_checkpoints:
            # Fallback: if messages exist, try popping the last turn (e.g. user + assistant/tools)
            if not self.messages:
                return False
            # Find the last user message and remove everything from there
            last_user_idx = None
            for idx in range(len(self.messages) - 1, -1, -1):
                if self.messages[idx].get("role") == "user":
                    last_user_idx = idx
                    break
            if last_user_idx is not None:
                self.messages = self.messages[:last_user_idx]
                self.updated_at = time.time()
                self.auto_save()
                return True
            return False

        self.messages = self.history_checkpoints.pop()
        self.updated_at = time.time()
        self.auto_save()
        return True

    def clear(self) -> None:
        self.messages.clear()
        self.history_checkpoints.clear()
        self.updated_at = time.time()
        self.auto_save()

    def get_messages(self) -> List[Dict]:
        result: List[Dict] = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend(self.messages)
        return result

    def total_estimated_tokens(self) -> int:
        total = 0
        if self.system_prompt:
            total += estimate_tokens(self.system_prompt) + 4
        for msg in self.messages:
            total += estimate_tokens(str(msg.get("content", ""))) + 4
        return total

    def _prune_context_if_needed(self) -> None:
        """Sliding window: prune oldest messages while preserving conversation coherence.
        Ensures system prompt is never pruned.
        """
        while len(self.messages) > 2 and self.total_estimated_tokens() > self.max_context_tokens:
            self.messages.pop(0)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "estimated_tokens": self.total_estimated_tokens(),
        }

    @classmethod
    def from_dict(cls, data: Dict, sessions_dir: Optional[Path] = None) -> "SessionManager":
        manager = cls(
            system_prompt=data.get("system_prompt"),
            session_id=data.get("session_id"),
            provider=data.get("provider"),
            model=data.get("model"),
            mode=data.get("mode"),
            sessions_dir=sessions_dir,
        )
        manager.created_at = data.get("created_at", time.time())
        manager.updated_at = data.get("updated_at", manager.created_at)
        manager.messages = data.get("messages", [])
        return manager

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def auto_save(self) -> None:
        """Automatically persist active session to sessions_dir."""
        try:
            if not self.messages and not self.system_prompt:
                return
            target_file = self.sessions_dir / f"{self.session_id}.json"
            self.save_json(target_file)
        except Exception:
            pass

    @classmethod
    def load_json(cls, path: Path, sessions_dir: Optional[Path] = None) -> "SessionManager":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, sessions_dir=sessions_dir)

    def save_markdown(self, path: Path) -> None:
        lines: List[str] = [f"# Chat Session: {self.session_id}\n\n"]
        if self.provider or self.model:
            lines.append(f"> **Provider**: {self.provider or 'N/A'} | **Model**: {self.model or 'N/A'} | **Mode**: {self.mode or 'N/A'}\n\n")
        if self.system_prompt:
            lines.append(f"> **System**: {self.system_prompt}\n\n---\n\n")
        for msg in self.messages:
            role = "**You**" if msg["role"] == "user" else "**Assistant**"
            content = msg.get("content", "")
            lines.append(f"{role}:\n\n{content}\n\n---\n\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(lines), encoding="utf-8")

    @classmethod
    def list_sessions(cls, sessions_dir: Optional[Path] = None) -> List[Dict]:
        """List all saved sessions sorted by most recent first."""
        target_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        if not target_dir.exists():
            return []

        results = []
        for file in target_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                msgs = data.get("messages", [])
                preview = ""
                for m in reversed(msgs):
                    if m.get("content"):
                        preview = m["content"].replace("\n", " ").strip()
                        if len(preview) > 60:
                            preview = preview[:57] + "..."
                        break
                results.append({
                    "session_id": data.get("session_id", file.stem),
                    "created_at": data.get("created_at", file.stat().st_mtime),
                    "updated_at": data.get("updated_at", file.stat().st_mtime),
                    "provider": data.get("provider", ""),
                    "model": data.get("model", ""),
                    "mode": data.get("mode", "chat"),
                    "message_count": len(msgs),
                    "preview": preview,
                    "file_path": file,
                })
            except Exception:
                continue

        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    @classmethod
    def get_latest_session(cls, sessions_dir: Optional[Path] = None) -> Optional["SessionManager"]:
        sessions = cls.list_sessions(sessions_dir=sessions_dir)
        if not sessions:
            return None
        latest_file = sessions[0]["file_path"]
        return cls.load_json(latest_file, sessions_dir=sessions_dir)

    @classmethod
    def find_session(cls, query: str, sessions_dir: Optional[Path] = None) -> Optional["SessionManager"]:
        target_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        # Direct filename or path
        direct_path = Path(query).expanduser()
        if direct_path.exists():
            return cls.load_json(direct_path, sessions_dir=sessions_dir)

        # Match exact ID
        exact_file = target_dir / f"{query}.json"
        if exact_file.exists():
            return cls.load_json(exact_file, sessions_dir=sessions_dir)

        # Match prefix of session_id
        for s in cls.list_sessions(sessions_dir=sessions_dir):
            if s["session_id"].startswith(query):
                return cls.load_json(s["file_path"], sessions_dir=sessions_dir)

        return None

# For backward compatibility
Session = SessionManager
