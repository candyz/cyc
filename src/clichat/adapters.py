"""Adapters for importing and bridging sessions from external agents:
- agy (Antigravity): ~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript.jsonl
- claude (Claude Code): ~/.claude/projects/*/*.jsonl
- pi (Pi Agent): ~/.pi/agent/sessions/*/*.jsonl
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from clichat.session import SessionManager

AGY_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-cli" / "brain"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
PI_SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions"


class SessionAdapters:
    """Helper class to discover and import sessions from agy, claude, and pi."""

    # ------------------------------------------------------------------
    # AGY (Google Antigravity) Adapter
    # ------------------------------------------------------------------
    @classmethod
    def list_agy_sessions(cls, brain_dir: Optional[Path] = None) -> List[Dict]:
        target_dir = brain_dir or AGY_BRAIN_DIR
        if not target_dir.exists():
            return []

        results = []
        for conv_dir in target_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            transcript_file = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if not transcript_file.exists():
                continue

            conv_id = conv_dir.name
            mtime = transcript_file.stat().st_mtime
            preview = ""
            user_msg_count = 0

            try:
                with open(transcript_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        step = json.loads(line)
                        if step.get("type") == "USER_INPUT" and step.get("content"):
                            user_msg_count += 1
                            raw_content = step["content"]
                            # Clean <USER_REQUEST> tags if present
                            clean_text = re.sub(r"</?USER_REQUEST>", "", raw_content).strip()
                            clean_text = clean_text.replace("\n", " ")
                            if len(clean_text) > 60:
                                clean_text = clean_text[:57] + "..."
                            preview = clean_text
            except Exception:
                continue

            results.append({
                "agent": "agy",
                "id": conv_id,
                "file_path": transcript_file,
                "updated_at": mtime,
                "message_count": user_msg_count,
                "preview": preview or "(no user prompt)",
            })

        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    @classmethod
    def import_agy_session(cls, query: str, brain_dir: Optional[Path] = None) -> Optional[SessionManager]:
        sessions = cls.list_agy_sessions(brain_dir=brain_dir)
        matched = None
        for s in sessions:
            if s["id"] == query or s["id"].startswith(query):
                matched = s
                break

        if not matched:
            return None

        transcript_file = matched["file_path"]
        session = SessionManager(
            session_id=f"agy_{matched['id'][:8]}",
            provider="agy",
            mode="agent",
        )

        with open(transcript_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                step = json.loads(line)
                stype = step.get("type")

                if stype == "USER_INPUT":
                    content = step.get("content", "")
                    clean_content = re.sub(r"</?USER_REQUEST>", "", content).strip()
                    if clean_content:
                        session.messages.append({"role": "user", "content": clean_content})
                elif stype == "PLANNER_RESPONSE":
                    tool_calls = step.get("tool_calls", [])
                    raw_tc = []
                    for tc in tool_calls:
                        args = tc.get("args") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        raw_tc.append({
                            "id": f"call_{len(raw_tc)}",
                            "type": "function",
                            "function": {
                                "name": tc.get("name", "unknown_tool"),
                                "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
                            },
                        })
                    content = step.get("content") or ""
                    msg_obj = {"role": "assistant", "content": content}
                    if raw_tc:
                        msg_obj["tool_calls"] = raw_tc
                    if content or raw_tc:
                        session.messages.append(msg_obj)
                elif stype == "GENERIC":
                    # Tool observations in agy transcript
                    content = step.get("content", "")
                    if content:
                        session.messages.append({
                            "role": "tool",
                            "name": "observation",
                            "content": content,
                        })

        session.auto_save()
        return session

    # ------------------------------------------------------------------
    # Claude Code Adapter
    # ------------------------------------------------------------------
    @classmethod
    def list_claude_sessions(cls, projects_dir: Optional[Path] = None) -> List[Dict]:
        target_dir = projects_dir or CLAUDE_PROJECTS_DIR
        if not target_dir.exists():
            return []

        results = []
        for file in target_dir.glob("*/*.jsonl"):
            if "subagents" in file.parts:
                continue
            session_id = file.stem
            mtime = file.stat().st_mtime
            preview = ""
            user_msg_count = 0

            try:
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        if record.get("type") == "user":
                            msg = record.get("message", {})
                            content = msg.get("content", "")
                            if isinstance(content, str) and content:
                                user_msg_count += 1
                                clean_text = content.replace("\n", " ").strip()
                                if len(clean_text) > 60:
                                    clean_text = clean_text[:57] + "..."
                                preview = clean_text
            except Exception:
                continue

            results.append({
                "agent": "claude",
                "id": session_id,
                "file_path": file,
                "updated_at": mtime,
                "message_count": user_msg_count,
                "preview": preview or "(no user prompt)",
            })

        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    @classmethod
    def import_claude_session(cls, query: str, projects_dir: Optional[Path] = None) -> Optional[SessionManager]:
        sessions = cls.list_claude_sessions(projects_dir=projects_dir)
        matched = None
        for s in sessions:
            if s["id"] == query or s["id"].startswith(query):
                matched = s
                break

        if not matched:
            return None

        file_path = matched["file_path"]
        session = SessionManager(
            session_id=f"claude_{matched['id'][:8]}",
            provider="openrouter",
            mode="agent",
        )

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                rtype = record.get("type")

                if rtype == "user":
                    msg = record.get("message", {})
                    content = msg.get("content")
                    if isinstance(content, str) and content:
                        session.messages.append({"role": "user", "content": content})
                    elif isinstance(content, list):
                        # List of tool_result items
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_result":
                                session.messages.append({
                                    "role": "tool",
                                    "tool_call_id": item.get("tool_use_id", "call_0"),
                                    "content": str(item.get("content", "")),
                                })
                elif rtype == "assistant":
                    msg = record.get("message", {})
                    content_blocks = msg.get("content", [])
                    text_acc = ""
                    tool_calls = []
                    if isinstance(content_blocks, list):
                        for b in content_blocks:
                            if not isinstance(b, dict):
                                continue
                            if b.get("type") == "text":
                                text_acc += b.get("text", "")
                            elif b.get("type") == "tool_use":
                                tool_calls.append({
                                    "id": b.get("id", f"call_{len(tool_calls)}"),
                                    "type": "function",
                                    "function": {
                                        "name": b.get("name", "unknown_tool"),
                                        "arguments": json.dumps(b.get("input", {}), ensure_ascii=False),
                                    },
                                })
                    elif isinstance(content_blocks, str):
                        text_acc = content_blocks

                    msg_obj = {"role": "assistant", "content": text_acc}
                    if tool_calls:
                        msg_obj["tool_calls"] = tool_calls
                    if text_acc or tool_calls:
                        session.messages.append(msg_obj)

        session.auto_save()
        return session

    # ------------------------------------------------------------------
    # Pi Agent Adapter
    # ------------------------------------------------------------------
    @classmethod
    def list_pi_sessions(cls, sessions_dir: Optional[Path] = None) -> List[Dict]:
        target_dir = sessions_dir or PI_SESSIONS_DIR
        if not target_dir.exists():
            return []

        results = []
        for file in target_dir.glob("*/*.jsonl"):
            session_id = file.stem
            mtime = file.stat().st_mtime
            preview = ""
            user_msg_count = 0

            try:
                with open(file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        if record.get("type") == "message":
                            msg = record.get("message", {})
                            if msg.get("role") == "user":
                                user_msg_count += 1
                                content = msg.get("content", [])
                                if isinstance(content, list):
                                    for c in content:
                                        if isinstance(c, dict) and c.get("type") == "text":
                                            clean_text = c.get("text", "").replace("\n", " ").strip()
                                            if len(clean_text) > 60:
                                                clean_text = clean_text[:57] + "..."
                                            preview = clean_text
            except Exception:
                continue

            results.append({
                "agent": "pi",
                "id": session_id,
                "file_path": file,
                "updated_at": mtime,
                "message_count": user_msg_count,
                "preview": preview or "(no user prompt)",
            })

        results.sort(key=lambda s: s["updated_at"], reverse=True)
        return results

    @classmethod
    def import_pi_session(cls, query: str, sessions_dir: Optional[Path] = None) -> Optional[SessionManager]:
        sessions = cls.list_pi_sessions(sessions_dir=sessions_dir)
        matched = None
        for s in sessions:
            if s["id"] == query or s["id"].startswith(query):
                matched = s
                break

        if not matched:
            return None

        file_path = matched["file_path"]
        session = SessionManager(
            session_id=f"pi_{matched['id'][:8]}",
            provider="nvidia",
            mode="agent",
        )

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                rtype = record.get("type")

                if rtype == "message":
                    msg = record.get("message", {})
                    role = msg.get("role")

                    if role == "user":
                        text_acc = ""
                        for c in msg.get("content", []):
                            if isinstance(c, dict) and c.get("type") == "text":
                                text_acc += c.get("text", "")
                        if text_acc:
                            session.messages.append({"role": "user", "content": text_acc})

                    elif role == "assistant":
                        text_acc = ""
                        tool_calls = []
                        for c in msg.get("content", []):
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "text":
                                text_acc += c.get("text", "")
                            elif c.get("type") == "toolCall":
                                tool_calls.append({
                                    "id": c.get("id", f"call_{len(tool_calls)}"),
                                    "type": "function",
                                    "function": {
                                        "name": c.get("name", "unknown_tool"),
                                        "arguments": json.dumps(c.get("arguments", {}), ensure_ascii=False),
                                    },
                                })
                        msg_obj = {"role": "assistant", "content": text_acc}
                        if tool_calls:
                            msg_obj["tool_calls"] = tool_calls
                        if text_acc or tool_calls:
                            session.messages.append(msg_obj)

                    elif role == "toolResult":
                        obs_acc = ""
                        for c in msg.get("content", []):
                            if isinstance(c, dict) and c.get("type") == "text":
                                obs_acc += c.get("text", "")
                        session.messages.append({
                            "role": "tool",
                            "tool_call_id": msg.get("toolCallId", "call_0"),
                            "name": msg.get("toolName", "tool"),
                            "content": obs_acc,
                        })

        session.auto_save()
        return session
