import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_SESSIONS_DIR = Path.home() / ".local" / "share" / "cyc" / "sessions"

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

def get_default_context_limit(provider: Optional[str] = None, model: Optional[str] = None) -> int:
    """Determine a modern, realistic token limit based on provider and model defaults.
    Prevents aggressive premature context window pruning.
    """
    prov = (provider or "").lower()
    mod = (model or "").lower()

    if "gemma" in mod or "nemotron" in mod:
        return 32_768
    elif "gemini" in prov or "gemini" in mod or "agy" in prov:
        return 1_000_000
    elif "claude" in mod or "anthropic" in mod:
        return 200_000
    elif "deepseek" in mod or "gpt-4" in mod or "gpt-3.5" in mod or "nvidia" in prov:
        return 128_000
    elif "qwen" in mod or "llama-3" in mod or "llama3" in mod:
        return 128_000
    # Modern general default (128k)
    return 128_000

class SessionManager:
    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_context_tokens: Optional[int] = None,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
        compact_threshold: float = 0.80,
        sessions_dir: Optional[Path] = None,
        title: Optional[str] = None,
        workspace: Optional[str] = None,
        git_branch: Optional[str] = None,
    ):
        self.system_prompt = system_prompt
        self.provider = provider
        self.model = model
        self.mode = mode
        self.title = title or ""
        self.is_custom_title = bool(title)
        self.compact_threshold = compact_threshold
        if max_context_tokens is not None and max_context_tokens > 0:
            self.max_context_tokens = max_context_tokens
        else:
            self.max_context_tokens = get_default_context_limit(provider, model)
        self.session_id = session_id or f"session_{int(time.time())}"
        self.sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        self.workspace = workspace
        self.git_branch = git_branch
        self.messages: List[Dict] = []
        self.created_at = time.time()
        self.updated_at = time.time()
        self.history_checkpoints: List[List[Dict]] = []
        self.events: List[Dict] = []
        # Cumulative token consumption tracking
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        # External agent bridge metadata (source agent, original id, path, imported message count)
        self.external_metadata: Dict = {}



    def append_event(self, event_type: str, data: Dict) -> None:
        """Record an append-only event (Event-Sourced timeline)."""
        self.events.append({
            "type": event_type,
            "timestamp": time.time(),
            "data": data,
        })
        # Save append-only jsonl log
        try:
            log_file = self.sessions_dir / f"{self.session_id}.events.jsonl"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(self.events[-1], ensure_ascii=False) + "\n")
        except Exception:
            pass

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        self.system_prompt = prompt
        self.append_event("system_prompt_set", {"prompt": prompt})
        self.auto_save()

    def add_user_message(self, content: str) -> None:
        # Save snapshot of messages before starting a new user interaction turn
        import copy
        self.history_checkpoints.append(copy.deepcopy(self.messages))
        # Keep maximum 20 undo checkpoints in memory
        if len(self.history_checkpoints) > 20:
            self.history_checkpoints.pop(0)

        self.messages.append({"role": "user", "content": content})
        self.append_event("user_message", {"content": content})
        self.total_prompt_tokens += estimate_tokens(content)
        self.updated_at = time.time()
        # Auto-set title from first user query if not set
        if not self.title and content.strip():
            first_line = content.strip().splitlines()[0].strip()
            self.title = first_line[:40] + ("..." if len(first_line) > 40 else "")
        self._prune_context_if_needed()
        self.auto_save()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self.append_event("assistant_message", {"content": content})
        self.total_completion_tokens += estimate_tokens(content)
        self.updated_at = time.time()
        self._prune_context_if_needed()
        self.auto_save()

    def add_tool_message(self, tool_call_id: str, name: str, content: str) -> None:
        from cyc.agent.tools.base import truncate_tool_output
        safe_content = truncate_tool_output(content)
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": safe_content,
        })
        self.append_event("tool_message", {"name": name, "tool_call_id": tool_call_id})
        self.total_completion_tokens += estimate_tokens(safe_content)
        self.updated_at = time.time()
        self._prune_context_if_needed()
        self.auto_save()

    def rename(self, new_title: str) -> None:
        """Rename this session with a user-friendly title."""
        self.title = new_title.strip()
        self.is_custom_title = True
        self.updated_at = time.time()
        self.append_event("session_renamed", {"title": self.title})
        target_file = self.sessions_dir / f"{self.session_id}.json"
        self.save_json(target_file)

    def fork_session(self, new_id: Optional[str] = None) -> "SessionManager":
        """Fork this session into a new independent session branch with identical history."""
        import copy
        forked_id = new_id or f"{self.session_id}_fork_{int(time.time())}"
        forked = SessionManager(
            system_prompt=self.system_prompt,
            max_context_tokens=self.max_context_tokens,
            session_id=forked_id,
            provider=self.provider,
            model=self.model,
            mode=self.mode,
            compact_threshold=self.compact_threshold,
            sessions_dir=self.sessions_dir,
            title=f"{self.title} (fork)" if self.title else "",
        )
        forked.messages = copy.deepcopy(self.messages)
        forked.history_checkpoints = copy.deepcopy(self.history_checkpoints)
        forked.events = copy.deepcopy(self.events)
        forked.append_event("forked_from", {"parent_session_id": self.session_id})
        forked.auto_save()
        return forked

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

    def sanitize_cancelled_state(self, cancellation_note: str = "Interrupted by user (Ctrl+C)") -> None:
        """Ensure message history remains valid for LLM APIs if interrupted during tool calls.

        If the last assistant message contains unresolved tool calls that did not receive
        corresponding tool responses before cancellation, append synthetic cancelled responses
        so the API schema requirement (each tool_call must have a matching tool response) is satisfied.
        """
        if not self.messages:
            return

        # Check if the last assistant message has tool_calls
        last_assistant_idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx is None:
            return

        assistant_msg = self.messages[last_assistant_idx]
        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list):
            return

        # Find which tool_call_ids were fulfilled in subsequent messages
        fulfilled_ids = set()
        for msg in self.messages[last_assistant_idx + 1:]:
            if msg.get("role") == "tool" and msg.get("tool_call_id"):
                fulfilled_ids.add(msg.get("tool_call_id"))

        # For any unfulfilled tool_calls, add cancelled tool message
        for tc in tool_calls:
            tc_id = tc.get("id")
            fn_info = tc.get("function", {})
            name = fn_info.get("name", "unknown_tool")
            if tc_id and tc_id not in fulfilled_ids:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": name,
                    "content": f"[Tool execution cancelled: {cancellation_note}]",
                })
                fulfilled_ids.add(tc_id)

        self.updated_at = time.time()
        self.auto_save()

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

    def compact(self, target_ratio: float = 0.50) -> Dict[str, Any]:
        """Compact session history by summarizing earlier messages and truncating oversized tool outputs.
        Compresses conversation down to target_ratio of max_context_tokens.
        Returns a dict summarizing before/after tokens and pruned count.
        """
        initial_tokens = self.total_estimated_tokens()
        target_tokens = int(self.max_context_tokens * target_ratio)

        # 1. Truncate oversized tool observations first
        for msg in self.messages:
            if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
                content_str = msg["content"]
                if len(content_str) > 600:
                    msg["content"] = content_str[:300] + "\n... [Tool output compacted] ...\n" + content_str[-200:]

        # 2. If still above target_tokens and have enough messages, summarize and prune older messages
        pruned_count = 0
        if self.total_estimated_tokens() > target_tokens and len(self.messages) > 4:
            # Keep the most recent 4 messages intact
            older_messages = self.messages[:-4]
            recent_messages = self.messages[-4:]

            # Extract brief summary highlights of older conversation
            summary_points = []
            for m in older_messages:
                r = m.get("role", "unknown")
                c = str(m.get("content", "")).strip().replace("\n", " ")
                if len(c) > 120:
                    c = c[:117] + "..."
                if c:
                    summary_points.append(f"- {r}: {c}")

            summary_text = "[Context compacted: summary of earlier conversation]\n" + "\n".join(summary_points[:15])
            compacted_msg = {
                "role": "user",
                "content": summary_text,
            }
            pruned_count = len(older_messages)
            self.messages = [compacted_msg] + recent_messages

        final_tokens = self.total_estimated_tokens()
        self.updated_at = time.time()
        self.append_event("session_compacted", {
            "initial_tokens": initial_tokens,
            "final_tokens": final_tokens,
            "pruned_count": pruned_count,
        })
        self.auto_save()
        return {
            "initial_tokens": initial_tokens,
            "final_tokens": final_tokens,
            "pruned_count": pruned_count,
            "saved_tokens": max(0, initial_tokens - final_tokens),
        }

    def _prune_context_if_needed(self) -> None:
        """Check if context exceeds auto-compact threshold (default 80%) or hard limit.
        If utilization >= compact_threshold, automatically compact session history.
        """
        if self.max_context_tokens > 0:
            utilization = self.total_estimated_tokens() / self.max_context_tokens
            if utilization >= self.compact_threshold and len(self.messages) > 4:
                self.compact(target_ratio=0.50)

        # Fallback hard sliding window if still exceeding hard limit
        while len(self.messages) > 2 and self.total_estimated_tokens() > self.max_context_tokens:
            self.messages.pop(0)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "events": self.events,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "max_context_tokens": self.max_context_tokens,
            "compact_threshold": self.compact_threshold,
            "external_metadata": self.external_metadata,
            "estimated_tokens": self.total_estimated_tokens(),
            "is_custom_title": self.is_custom_title,
            "workspace": self.workspace,
            "git_branch": self.git_branch,
        }

    @classmethod
    def from_dict(cls, data: Dict, sessions_dir: Optional[Path] = None) -> "SessionManager":
        workspace = data.get("workspace")
        git_branch = data.get("git_branch")
        if not workspace or not git_branch:
            sys_prompt = data.get("system_prompt") or ""
            if not workspace:
                m_cwd = re.search(r"Current Working Directory:\s*(.+)", sys_prompt)
                if m_cwd:
                    workspace = m_cwd.group(1).strip()
            if not git_branch:
                m_git = re.search(r"Git Branch:\s*##\s*([^\s\.]+)", sys_prompt)
                if m_git:
                    git_branch = m_git.group(1).strip()

        manager = cls(
            system_prompt=data.get("system_prompt"),
            max_context_tokens=data.get("max_context_tokens"),
            session_id=data.get("session_id"),
            provider=data.get("provider"),
            model=data.get("model"),
            mode=data.get("mode"),
            compact_threshold=data.get("compact_threshold", 0.80),
            sessions_dir=sessions_dir,
            title=data.get("title", ""),
            workspace=workspace,
            git_branch=git_branch,
        )
        manager.is_custom_title = data.get("is_custom_title", bool(data.get("title") and any(e.get("type") == "session_renamed" for e in data.get("events", []))))
        manager.created_at = data.get("created_at", time.time())
        manager.updated_at = data.get("updated_at", manager.created_at)
        manager.messages = data.get("messages", [])
        manager.events = data.get("events", [])
        manager.total_prompt_tokens = data.get("total_prompt_tokens", 0)
        manager.total_completion_tokens = data.get("total_completion_tokens", 0)
        manager.external_metadata = data.get("external_metadata", {})
        return manager

    def save_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def auto_save(self) -> None:
        """Automatically persist active session to sessions_dir."""
        try:
            if not self.messages and not self.system_prompt and not self.title:
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
        header_title = f"{self.title} ({self.session_id})" if self.title else self.session_id
        lines: List[str] = [f"# Chat Session: {header_title}\n\n"]
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
                is_custom = data.get("is_custom_title", False)
                if not is_custom and data.get("title") and any(e.get("type") == "session_renamed" for e in data.get("events", [])):
                    is_custom = True

                workspace = data.get("workspace")
                git_branch = data.get("git_branch")
                if not workspace or not git_branch:
                    sys_prompt = data.get("system_prompt") or ""
                    if not workspace:
                        m_cwd = re.search(r"Current Working Directory:\s*(.+)", sys_prompt)
                        if m_cwd:
                            workspace = m_cwd.group(1).strip()
                    if not git_branch:
                        m_git = re.search(r"Git Branch:\s*##\s*([^\s\.]+)", sys_prompt)
                        if m_git:
                            git_branch = m_git.group(1).strip()

                results.append({
                    "id": data.get("session_id", file.stem),
                    "session_id": data.get("session_id", file.stem),
                    "title": data.get("title", ""),
                    "is_custom_title": is_custom,
                    "agent": "cyc",
                    "workspace": workspace or "",
                    "git_branch": git_branch or "",
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
        if query == "LATEST":
            return cls.get_latest_session(sessions_dir=sessions_dir)

        target_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        # Direct filename or path
        direct_path = Path(query).expanduser()
        if direct_path.exists():
            return cls.load_json(direct_path, sessions_dir=sessions_dir)

        # Match exact ID
        exact_file = target_dir / f"{query}.json"
        if exact_file.exists():
            return cls.load_json(exact_file, sessions_dir=sessions_dir)

        # Match exact or prefix of session_id, or match title
        all_sessions = cls.list_sessions(sessions_dir=sessions_dir)
        # 1. Exact title match
        for s in all_sessions:
            if s.get("title") and s["title"].strip().lower() == query.strip().lower():
                return cls.load_json(s["file_path"], sessions_dir=sessions_dir)

        # 2. Prefix of session_id
        for s in all_sessions:
            sid = s.get("id") or s.get("session_id", "")
            if sid.startswith(query):
                return cls.load_json(s["file_path"], sessions_dir=sessions_dir)

        # 3. Partial / substring title match
        for s in all_sessions:
            if s.get("title") and query.strip().lower() in s["title"].strip().lower():
                return cls.load_json(s["file_path"], sessions_dir=sessions_dir)

        return None

    @classmethod
    def delete_session(cls, query: str, sessions_dir: Optional[Path] = None) -> bool:
        """Delete a saved session by ID, exact title, or path. Return True if deleted."""
        target_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        sess = cls.find_session(query, sessions_dir=sessions_dir)
        if sess:
            target_file = target_dir / f"{sess.session_id}.json"
            if target_file.exists():
                try:
                    target_file.unlink()
                    return True
                except Exception:
                    pass
        # Fallback to direct filename
        direct_file = target_dir / f"{query}.json"
        if direct_file.exists():
            try:
                direct_file.unlink()
                return True
            except Exception:
                pass
        return False

    @classmethod
    def prune_sessions(
        cls,
        max_messages: int = 1,
        sessions_dir: Optional[Path] = None,
    ) -> int:
        """Prune empty or near-empty sessions with message count <= max_messages and no custom title.
        Returns the number of pruned session files.
        """
        target_dir = sessions_dir or DEFAULT_SESSIONS_DIR
        pruned_count = 0
        sessions = cls.list_sessions(sessions_dir=sessions_dir)
        for s in sessions:
            # Only prune CYC local sessions
            if s.get("agent") != "cyc":
                continue
            # Keep sessions that have a custom title
            if s.get("is_custom_title"):
                continue
            if s.get("message_count", 0) <= max_messages:
                file_path = s.get("file_path")
                if file_path and Path(file_path).exists():
                    try:
                        Path(file_path).unlink()
                        pruned_count += 1
                    except Exception:
                        pass
        return pruned_count

# For backward compatibility
Session = SessionManager
