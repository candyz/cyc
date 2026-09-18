"""Adapters for importing and bridging sessions from external agents:
- agy (Antigravity): ~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript.jsonl
- claude (Claude Code): ~/.claude/projects/*/*.jsonl
- pi (Pi Agent): ~/.pi/agent/sessions/*/*.jsonl
- opencode (OpenCode): ~/.local/share/opencode/opencode.db
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from cyc.session import SessionManager

AGY_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-cli" / "brain"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
PI_SESSIONS_DIR = Path.home() / ".pi" / "agent" / "sessions"
OPENCODE_DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


class SessionAdapters:
    """Helper class to discover and import sessions from agy, claude, pi, and opencode."""

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

        session.external_metadata = {
            "source_agent": "agy",
            "source_id": matched["id"],
            "file_path": str(transcript_file),
            "base_message_count": len(session.messages),
        }
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

        session.external_metadata = {
            "source_agent": "claude",
            "source_id": matched["id"],
            "file_path": str(file_path),
            "base_message_count": len(session.messages),
        }
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

        session.external_metadata = {
            "source_agent": "pi",
            "source_id": matched["id"],
            "file_path": str(file_path),
            "base_message_count": len(session.messages),
        }
        session.auto_save()
        return session

    # ------------------------------------------------------------------
    # OpenCode Adapter
    # ------------------------------------------------------------------
    @classmethod
    def list_opencode_sessions(cls, db_path: Optional[Path] = None) -> List[Dict]:
        target_db = db_path or OPENCODE_DB_PATH
        if not target_db.exists():
            return []

        results = []
        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            cursor = conn.cursor()

            query = """
            SELECT
                s.id,
                s.title,
                s.time_updated,
                s.directory,
                s.agent,
                s.model,
                (
                    SELECT p.data
                    FROM message m
                    JOIN part p ON m.id = p.message_id
                    WHERE m.session_id = s.id
                      AND json_extract(m.data, '$.role') = 'user'
                      AND json_extract(p.data, '$.type') = 'text'
                    ORDER BY m.time_created ASC, p.time_created ASC
                    LIMIT 1
                ) AS first_user_part,
                (
                    SELECT COUNT(m.id)
                    FROM message m
                    WHERE m.session_id = s.id
                      AND json_extract(m.data, '$.role') = 'user'
                ) AS user_msg_count
            FROM session s
            ORDER BY s.time_updated DESC;
            """
            cursor.execute(query)
            rows = cursor.fetchall()

            for row in rows:
                sid, title, time_updated, directory, agent, model_raw, first_user_part_raw, user_msg_count = row
                preview = ""
                if first_user_part_raw:
                    try:
                        part_obj = json.loads(first_user_part_raw)
                        clean_text = part_obj.get("text", "").replace("\n", " ").strip()
                        if len(clean_text) > 60:
                            clean_text = clean_text[:57] + "..."
                        preview = clean_text
                    except Exception:
                        pass

                if not preview and title and not title.startswith("New session -"):
                    preview = title

                # Model info extraction
                model_name = ""
                if model_raw:
                    try:
                        m_info = json.loads(model_raw)
                        model_name = m_info.get("id") or m_info.get("modelID") or ""
                    except Exception:
                        model_name = str(model_raw)

                # time_updated in opencode is in milliseconds
                updated_sec = (time_updated / 1000.0) if time_updated else 0

                results.append({
                    "agent": "opencode",
                    "id": sid,
                    "title": title or "",
                    "model": model_name,
                    "provider": "opencode",
                    "mode": "agent",
                    "updated_at": updated_sec,
                    "message_count": user_msg_count or 0,
                    "preview": preview or "(no user prompt)",
                })

            conn.close()
        except Exception:
            return []

        return results

    @classmethod
    def import_opencode_session(cls, query: str, db_path: Optional[Path] = None) -> Optional[SessionManager]:
        target_db = db_path or OPENCODE_DB_PATH
        if not target_db.exists():
            return None

        sessions = cls.list_opencode_sessions(db_path=target_db)
        matched = None
        for s in sessions:
            if s["id"] == query or s["id"].startswith(query):
                matched = s
                break

        if not matched:
            return None

        session_id = matched["id"]
        session = SessionManager(
            session_id=f"opencode_{session_id[:12]}",
            provider="opencode",
            model=matched.get("model") or None,
            mode="agent",
        )

        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Retrieve messages in order
            msg_query = """
            SELECT id, data
            FROM message
            WHERE session_id = ?
            ORDER BY time_created ASC;
            """
            cursor.execute(msg_query, (session_id,))
            messages = cursor.fetchall()

            for msg_id, msg_data_raw in messages:
                try:
                    msg_meta = json.loads(msg_data_raw)
                except Exception:
                    continue

                role = msg_meta.get("role")

                # Get all parts for this message
                part_query = """
                SELECT data
                FROM part
                WHERE message_id = ?
                ORDER BY time_created ASC;
                """
                cursor.execute(part_query, (msg_id,))
                parts = cursor.fetchall()

                if role == "user":
                    user_text = ""
                    for (part_raw,) in parts:
                        try:
                            p_data = json.loads(part_raw)
                            if p_data.get("type") == "text":
                                user_text += p_data.get("text", "")
                        except Exception:
                            continue
                    if user_text:
                        session.messages.append({"role": "user", "content": user_text})

                elif role == "assistant":
                    asst_text = ""
                    tool_calls = []
                    for (part_raw,) in parts:
                        try:
                            p_data = json.loads(part_raw)
                            ptype = p_data.get("type")
                            if ptype == "text":
                                asst_text += p_data.get("text", "")
                            elif ptype == "tool":
                                call_id = p_data.get("callID") or f"call_{len(tool_calls)}"
                                tool_name = p_data.get("tool", "unknown_tool")
                                state = p_data.get("state") or {}
                                input_args = state.get("input") or {}
                                tool_calls.append({
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(input_args, ensure_ascii=False) if isinstance(input_args, dict) else str(input_args),
                                    },
                                })
                        except Exception:
                            continue

                    msg_obj = {"role": "assistant", "content": asst_text}
                    if tool_calls:
                        msg_obj["tool_calls"] = tool_calls
                    if asst_text or tool_calls:
                        session.messages.append(msg_obj)

                    # Also append tool observation messages from completed tools
                    for (part_raw,) in parts:
                        try:
                            p_data = json.loads(part_raw)
                            if p_data.get("type") == "tool":
                                call_id = p_data.get("callID") or "call_0"
                                tool_name = p_data.get("tool", "tool")
                                state = p_data.get("state") or {}
                                output = state.get("output", "")
                                session.messages.append({
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": tool_name,
                                    "content": str(output),
                                })
                        except Exception:
                            continue

            conn.close()
            session.external_metadata = {
                "source_agent": "opencode",
                "source_id": matched["id"],
                "file_path": str(target_db),
                "base_message_count": len(session.messages),
            }
            session.auto_save()
            return session
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Two-Way Write-Back Bridge (Sync Back to External Agents)
    # ------------------------------------------------------------------
    @classmethod
    def export_session_to_agy(
        cls,
        session: SessionManager,
        target_conv_id: Optional[str] = None,
        brain_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Write back newly generated messages in session to AGY transcript.jsonl.
        Returns a status dictionary with success status and written lines count.
        """
        import datetime
        target_dir = brain_dir or AGY_BRAIN_DIR

        # Determine target agy conversation id
        conv_id = target_conv_id
        if not conv_id and session.external_metadata.get("source_agent") == "agy":
            conv_id = session.external_metadata.get("source_id")

        if not conv_id:
            # Generate a new AGY conversation directory if none specified
            import uuid
            conv_id = str(uuid.uuid4())

        # Determine transcript file path
        if session.external_metadata.get("file_path") and Path(session.external_metadata["file_path"]).exists():
            transcript_file = Path(session.external_metadata["file_path"])
        else:
            conv_folder = target_dir / conv_id
            log_folder = conv_folder / ".system_generated" / "logs"
            log_folder.mkdir(parents=True, exist_ok=True)
            transcript_file = log_folder / "transcript.jsonl"

        # Determine last step_index
        last_step_index = -1
        if transcript_file.exists():
            try:
                with open(transcript_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            idx = data.get("step_index")
                            if isinstance(idx, int) and idx > last_step_index:
                                last_step_index = idx
            except Exception:
                pass

        # Identify messages to write back
        base_count = 0
        if session.external_metadata.get("source_id") == conv_id:
            base_count = session.external_metadata.get("base_message_count", 0)

        new_messages = session.messages[base_count:]
        if not new_messages:
            return {
                "success": True,
                "synced_count": 0,
                "conv_id": conv_id,
                "transcript_file": str(transcript_file),
                "message": "Already up to date (no new messages to sync back).",
            }

        written_count = 0
        current_step = last_step_index + 1
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with open(transcript_file, "a", encoding="utf-8") as f:
            for msg in new_messages:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    entry = {
                        "step_index": current_step,
                        "source": "USER_EXPLICIT",
                        "type": "USER_INPUT",
                        "status": "DONE",
                        "created_at": now_iso,
                        "content": f"<USER_REQUEST>\n{content}\n</USER_REQUEST>",
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    current_step += 1
                    written_count += 1

                elif role == "assistant":
                    tool_calls_raw = msg.get("tool_calls", [])
                    agy_tc = []
                    for tc in tool_calls_raw:
                        fn = tc.get("function", {})
                        t_name = fn.get("name", "tool")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        agy_tc.append({"name": t_name, "args": args})

                    entry = {
                        "step_index": current_step,
                        "source": "MODEL",
                        "type": "PLANNER_RESPONSE",
                        "status": "DONE",
                        "created_at": now_iso,
                    }
                    if content:
                        entry["content"] = content
                    if agy_tc:
                        entry["tool_calls"] = agy_tc

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    current_step += 1
                    written_count += 1

                elif role == "tool":
                    entry = {
                        "step_index": current_step,
                        "source": "MODEL",
                        "type": "GENERIC",
                        "status": "DONE",
                        "created_at": now_iso,
                        "content": str(content),
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    current_step += 1
                    written_count += 1

        # Update base_message_count so next sync won't duplicate
        session.external_metadata["source_agent"] = "agy"
        session.external_metadata["source_id"] = conv_id
        session.external_metadata["file_path"] = str(transcript_file)
        session.external_metadata["base_message_count"] = len(session.messages)
        session.auto_save()

        return {
            "success": True,
            "synced_count": written_count,
            "conv_id": conv_id,
            "transcript_file": str(transcript_file),
            "message": f"Successfully synced {written_count} turns back to AGY conversation '{conv_id}'",
        }

    @classmethod
    def export_session_to_claude(
        cls,
        session: SessionManager,
        target_session_id: Optional[str] = None,
        projects_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Write back newly generated messages in session to Claude Code project JSONL file."""
        target_dir = projects_dir or CLAUDE_PROJECTS_DIR
        sess_id = target_session_id
        if not sess_id and session.external_metadata.get("source_agent") == "claude":
            sess_id = session.external_metadata.get("source_id")

        if not sess_id:
            import uuid
            sess_id = str(uuid.uuid4())

        # Determine target file
        target_file = None
        if session.external_metadata.get("file_path") and Path(session.external_metadata["file_path"]).exists():
            target_file = Path(session.external_metadata["file_path"])
        else:
            default_proj = target_dir / "default"
            default_proj.mkdir(parents=True, exist_ok=True)
            target_file = default_proj / f"{sess_id}.jsonl"

        base_count = 0
        if session.external_metadata.get("source_id") == sess_id:
            base_count = session.external_metadata.get("base_message_count", 0)

        new_messages = session.messages[base_count:]
        if not new_messages:
            return {
                "success": True,
                "synced_count": 0,
                "session_id": sess_id,
                "file_path": str(target_file),
                "message": "Already up to date (no new messages to sync back).",
            }

        written_count = 0
        with open(target_file, "a", encoding="utf-8") as f:
            for msg in new_messages:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    record = {
                        "type": "user",
                        "message": {"role": "user", "content": content},
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_count += 1

                elif role == "assistant":
                    tool_calls_raw = msg.get("tool_calls", [])
                    content_blocks = []
                    if content:
                        content_blocks.append({"type": "text", "text": content})
                    for tc in tool_calls_raw:
                        fn = tc.get("function", {})
                        t_name = fn.get("name", "tool")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", "call_0"),
                            "name": t_name,
                            "input": args,
                        })

                    record = {
                        "type": "assistant",
                        "message": {"role": "assistant", "content": content_blocks},
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_count += 1

                elif role == "tool":
                    record = {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": msg.get("tool_call_id", "call_0"),
                                    "content": str(content),
                                }
                            ],
                        },
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_count += 1

        session.external_metadata["source_agent"] = "claude"
        session.external_metadata["source_id"] = sess_id
        session.external_metadata["file_path"] = str(target_file)
        session.external_metadata["base_message_count"] = len(session.messages)
        session.auto_save()

        return {
            "success": True,
            "synced_count": written_count,
            "session_id": sess_id,
            "file_path": str(target_file),
            "message": f"Successfully synced {written_count} turns back to Claude Code session '{sess_id}'",
        }

    @classmethod
    def export_session_to_pi(
        cls,
        session: SessionManager,
        target_session_id: Optional[str] = None,
        sessions_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Write back newly generated messages in session to Pi Agent JSONL file."""
        target_dir = sessions_dir or PI_SESSIONS_DIR
        sess_id = target_session_id
        if not sess_id and session.external_metadata.get("source_agent") == "pi":
            sess_id = session.external_metadata.get("source_id")

        if not sess_id:
            import uuid
            sess_id = str(uuid.uuid4())

        target_file = None
        if session.external_metadata.get("file_path") and Path(session.external_metadata["file_path"]).exists():
            target_file = Path(session.external_metadata["file_path"])
        else:
            default_sub = target_dir / "default"
            default_sub.mkdir(parents=True, exist_ok=True)
            target_file = default_sub / f"{sess_id}.jsonl"

        base_count = 0
        if session.external_metadata.get("source_id") == sess_id:
            base_count = session.external_metadata.get("base_message_count", 0)

        new_messages = session.messages[base_count:]
        if not new_messages:
            return {
                "success": True,
                "synced_count": 0,
                "session_id": sess_id,
                "file_path": str(target_file),
                "message": "Already up to date (no new messages to sync back).",
            }

        written_count = 0
        with open(target_file, "a", encoding="utf-8") as f:
            for msg in new_messages:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    record = {
                        "type": "message",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": content}],
                        },
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_count += 1

                elif role == "assistant":
                    tool_calls_raw = msg.get("tool_calls", [])
                    content_list = []
                    if content:
                        content_list.append({"type": "text", "text": content})
                    for tc in tool_calls_raw:
                        fn = tc.get("function", {})
                        t_name = fn.get("name", "tool")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        content_list.append({
                            "type": "toolCall",
                            "id": tc.get("id", "call_0"),
                            "name": t_name,
                            "arguments": args,
                        })

                    record = {
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": content_list,
                        },
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_count += 1

                elif role == "tool":
                    record = {
                        "type": "message",
                        "message": {
                            "role": "toolResult",
                            "toolCallId": msg.get("tool_call_id", "call_0"),
                            "toolName": msg.get("name", "tool"),
                            "content": [{"type": "text", "text": str(content)}],
                        },
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_count += 1

        session.external_metadata["source_agent"] = "pi"
        session.external_metadata["source_id"] = sess_id
        session.external_metadata["file_path"] = str(target_file)
        session.external_metadata["base_message_count"] = len(session.messages)
        session.auto_save()

        return {
            "success": True,
            "synced_count": written_count,
            "session_id": sess_id,
            "file_path": str(target_file),
            "message": f"Successfully synced {written_count} turns back to Pi Agent session '{sess_id}'",
        }

    @classmethod
    def export_session_to_opencode(
        cls,
        session: SessionManager,
        target_session_id: Optional[str] = None,
        db_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Write back newly generated messages in session to OpenCode SQLite database."""
        target_db = db_path or OPENCODE_DB_PATH
        if not target_db.exists():
            return {
                "success": False,
                "error": f"OpenCode database not found at {target_db}",
            }

        sess_id = target_session_id
        if not sess_id and session.external_metadata.get("source_agent") == "opencode":
            sess_id = session.external_metadata.get("source_id")

        if not sess_id:
            import uuid
            sess_id = f"ses_{uuid.uuid4().hex[:16]}"

        base_count = 0
        if session.external_metadata.get("source_id") == sess_id:
            base_count = session.external_metadata.get("base_message_count", 0)

        new_messages = session.messages[base_count:]
        if not new_messages:
            return {
                "success": True,
                "synced_count": 0,
                "session_id": sess_id,
                "file_path": str(target_db),
                "message": "Already up to date (no new messages to sync back).",
            }

        import time
        import uuid

        written_count = 0
        try:
            conn = sqlite3.connect(str(target_db))
            cursor = conn.cursor()

            # Ensure session exists in session table
            cursor.execute("SELECT id FROM session WHERE id = ?;", (sess_id,))
            if not cursor.fetchone():
                now_ms = int(time.time() * 1000)
                cursor.execute("""
                INSERT INTO session (id, time_created, time_updated, model)
                VALUES (?, ?, ?, ?);
                """, (sess_id, now_ms, now_ms, session.model or "default"))

            now_ms = int(time.time() * 1000)
            for msg in new_messages:
                role = msg.get("role")
                content = msg.get("content", "")
                msg_id = f"msg_{uuid.uuid4().hex[:16]}"

                if role == "user":
                    cursor.execute("""
                    INSERT INTO message (id, session_id, time_created, time_updated, data)
                    VALUES (?, ?, ?, ?, ?);
                    """, (msg_id, sess_id, now_ms, now_ms, json.dumps({"role": "user"})))

                    part_id = f"part_{uuid.uuid4().hex[:16]}"
                    cursor.execute("""
                    INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """, (part_id, msg_id, sess_id, now_ms, now_ms, json.dumps({"type": "text", "text": content})))
                    written_count += 1
                    now_ms += 10

                elif role == "assistant":
                    tool_calls_raw = msg.get("tool_calls", [])
                    cursor.execute("""
                    INSERT INTO message (id, session_id, time_created, time_updated, data)
                    VALUES (?, ?, ?, ?, ?);
                    """, (msg_id, sess_id, now_ms, now_ms, json.dumps({"role": "assistant"})))

                    if content:
                        part_id = f"part_{uuid.uuid4().hex[:16]}"
                        cursor.execute("""
                        INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """, (part_id, msg_id, sess_id, now_ms, now_ms, json.dumps({"type": "text", "text": content})))

                    for tc in tool_calls_raw:
                        fn = tc.get("function", {})
                        t_name = fn.get("name", "tool")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                pass
                        part_id = f"part_{uuid.uuid4().hex[:16]}"
                        cursor.execute("""
                        INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """, (part_id, msg_id, sess_id, now_ms, now_ms, json.dumps({
                            "type": "tool",
                            "tool": t_name,
                            "callID": tc.get("id", "call_0"),
                            "state": {"input": args},
                        })))
                    written_count += 1
                    now_ms += 10

                elif role == "tool":
                    # Tool observation in opencode part
                    part_id = f"part_{uuid.uuid4().hex[:16]}"
                    cursor.execute("""
                    INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """, (part_id, msg_id, sess_id, now_ms, now_ms, json.dumps({
                        "type": "tool",
                        "tool": msg.get("name", "tool"),
                        "callID": msg.get("tool_call_id", "call_0"),
                        "state": {"output": str(content)},
                    })))
                    written_count += 1
                    now_ms += 10

            # Update session time_updated
            cursor.execute("UPDATE session SET time_updated = ? WHERE id = ?;", (now_ms, sess_id))
            conn.commit()
            conn.close()

            session.external_metadata["source_agent"] = "opencode"
            session.external_metadata["source_id"] = sess_id
            session.external_metadata["file_path"] = str(target_db)
            session.external_metadata["base_message_count"] = len(session.messages)
            session.auto_save()

            return {
                "success": True,
                "synced_count": written_count,
                "session_id": sess_id,
                "file_path": str(target_db),
                "message": f"Successfully synced {written_count} turns back to OpenCode session '{sess_id}'",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write to OpenCode SQLite database: {e}",
            }

    @classmethod
    def sync_session_back(
        cls,
        session: SessionManager,
        target_agent: Optional[str] = None,
        custom_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Automatically detect or target external agent and write new conversation turns back."""
        agent = (target_agent or session.external_metadata.get("source_agent") or "").lower()
        if agent in ("agy", "antigravity"):
            return cls.export_session_to_agy(session, brain_dir=custom_path)
        elif agent in ("claude", "claude_code"):
            return cls.export_session_to_claude(session, projects_dir=custom_path)
        elif agent in ("pi", "pi_agent"):
            return cls.export_session_to_pi(session, sessions_dir=custom_path)
        elif agent in ("opencode", "zen"):
            return cls.export_session_to_opencode(session, db_path=custom_path)
        elif not agent:
            return {
                "success": False,
                "error": "No source agent detected in session. Specify target agent (e.g. '/sync agy', '/sync claude', '/sync pi', '/sync opencode').",
            }
        else:
            return {
                "success": False,
                "error": f"Unsupported agent '{agent}'. Supported: agy, claude, pi, opencode.",
            }

