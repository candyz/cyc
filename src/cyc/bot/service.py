"""Telegram Bot Service for cyc CLI agent."""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

from rich.console import Console
from rich.panel import Panel

from cyc import __version__
from cyc.agent import (
    AgentLoop,
    PermissionManager,
    PermissionMode,
    ToolRegistry,
    get_default_tools,
)
from cyc.agent.diff import generate_unified_diff
from cyc.bot.formatter import chunk_message, escape_html, format_markdown_to_telegram_html
from cyc.bot.telegram import TelegramClient
from cyc.config import Config, load_config
from cyc.providers import create_provider
from cyc.session import SessionManager

console = Console()


class TelegramBotService:
    """Long-polling Telegram Bot Service with authentication, HITL approval, and agent loop execution."""

    def __init__(self, config: Optional[Config] = None, token: Optional[str] = None):
        self.config = config or load_config()
        self.token = token or self.config.bot.telegram.token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.allowed_users: Set[int] = set(self.config.bot.telegram.allowed_user_ids)
        self.auto_approve: bool = self.config.bot.telegram.auto_approve
        self.throttle_seconds: float = self.config.bot.telegram.streaming_throttle_seconds or 1.2
        self.workspace_path = (
            Path(self.config.bot.telegram.workspace_path).expanduser().resolve()
            if self.config.bot.telegram.workspace_path
            else Path.cwd()
        )

        self.client = TelegramClient(token=self.token)
        # Per chat state: session_id, mode ("agent"|"chat"), active_task
        self.chat_sessions: Dict[int, SessionManager] = {}
        self.chat_modes: Dict[int, str] = {}
        self.chat_running_tasks: Dict[int, asyncio.Task] = {}
        # Pending HITL approval futures: {approval_id: asyncio.Future}
        self.pending_approvals: Dict[str, asyncio.Future] = {}
        self._running = False

    def is_authorized(self, user_id: int) -> bool:
        """Check if user_id is in allowed list. If list is empty, disallow for safety unless explicitly allowed."""
        if not self.allowed_users:
            return False
        return user_id in self.allowed_users

    def get_session(self, chat_id: int) -> SessionManager:
        """Get or create isolated SessionManager for chat_id."""
        if chat_id not in self.chat_sessions:
            sess_id = f"tg-{chat_id}"
            session = SessionManager.find_session(sess_id)
            if not session:
                session = SessionManager(
                    session_id=sess_id,
                    provider=self.config.default_provider,
                    model=self.config.default_model,
                    mode=self.chat_modes.get(chat_id, "agent"),
                )
            self.chat_sessions[chat_id] = session
        return self.chat_sessions[chat_id]

    async def start(self) -> None:
        """Start long-polling Telegram Bot service."""
        if not self.token:
            console.print("[bold red]Error:[/bold red] Telegram Bot Token is empty. Please set bot.telegram.token in config.yaml or TELEGRAM_BOT_TOKEN env.")
            return

        try:
            bot_info = await self.client.get_me()
            bot_name = bot_info.get("first_name", "cyc bot")
            bot_username = bot_info.get("username", "cyc_bot")
        except Exception as e:
            console.print(f"[bold red]Failed to connect to Telegram Bot API:[/bold red] {e}")
            return

        panel_text = (
            f"[bold green]cyc Telegram Bot Gateway v{__version__}[/bold green]\n\n"
            f"• Bot:       [cyan]@{bot_username}[/cyan] ({bot_name})\n"
            f"• Workspace: [cyan]{self.workspace_path}[/cyan]\n"
            f"• Whitelist: [yellow]{list(self.allowed_users) or 'None (Strict Lockdown)'}[/yellow]\n"
            f"• Auto-Approve: [{'green' if self.auto_approve else 'dim'}]{self.auto_approve}[/{'green' if self.auto_approve else 'dim'}]\n\n"
            "[dim]Press Ctrl+C to stop Telegram Bot service.[/dim]"
        )
        console.print(Panel(panel_text, title="🤖 cyc Bot Service Running", border_style="cyan", expand=False))

        self._running = True
        offset: Optional[int] = None

        try:
            while self._running:
                try:
                    updates = await self.client.get_updates(offset=offset, timeout=30)
                    for update in updates:
                        offset = update["update_id"] + 1
                        await self.handle_update(update)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    console.print(f"[dim red]Telegram polling error:[/dim red] {e}")
                    await asyncio.sleep(2)
        finally:
            self._running = False
            await self.client.close()
            console.print("[yellow]Telegram Bot Service stopped.[/yellow]")

    def stop(self) -> None:
        self._running = False

    async def handle_update(self, update: Dict[str, Any]) -> None:
        """Route update to message handler or callback query handler."""
        if "callback_query" in update:
            await self.handle_callback_query(update["callback_query"])
        elif "message" in update:
            await self.handle_message(update["message"])

    async def handle_callback_query(self, cb: Dict[str, Any]) -> None:
        """Handle HITL Approval buttons clicked by user."""
        cb_id = cb["id"]
        from_user = cb.get("from", {})
        user_id = from_user.get("id")
        data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")

        if not self.is_authorized(user_id):
            await self.client.answer_callback_query(cb_id, text="⚠️ Unauthorized", show_alert=True)
            return

        # Data format: approve:<approval_id> or deny:<approval_id>
        if ":" in data:
            action, approval_id = data.split(":", 1)
            fut = self.pending_approvals.get(approval_id)
            if fut and not fut.done():
                if action == "approve":
                    fut.set_result(True)
                    await self.client.answer_callback_query(cb_id, text="✅ Action Approved")
                    if chat_id and message.get("message_id"):
                        await self.client.edit_message_text(
                            chat_id=chat_id,
                            message_id=message["message_id"],
                            text=f"{message.get('text', '')}\n\n<b>[Result: Approved ✅]</b>",
                            parse_mode="HTML",
                        )
                else:
                    fut.set_result(False)
                    await self.client.answer_callback_query(cb_id, text="❌ Action Denied")
                    if chat_id and message.get("message_id"):
                        await self.client.edit_message_text(
                            chat_id=chat_id,
                            message_id=message["message_id"],
                            text=f"{message.get('text', '')}\n\n<b>[Result: Denied ❌]</b>",
                            parse_mode="HTML",
                        )
                return

        await self.client.answer_callback_query(cb_id)

    async def handle_message(self, message: Dict[str, Any]) -> None:
        """Handle standard chat messages and bot slash commands."""
        from_user = message.get("from", {})
        user_id = from_user.get("id")
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if not text or not chat_id:
            return

        # Security check: whitelist
        if not self.is_authorized(user_id):
            console.print(f"[bold red]Unauthorized access attempt:[/bold red] User ID {user_id} (@{from_user.get('username')})")
            await self.client.send_message(
                chat_id=chat_id,
                text="⛔ <b>Access Denied</b>\n\nYour Telegram User ID is not authorized to interact with this cyc instance.",
            )
            return

        # Handle commands
        if text.startswith("/"):
            await self.handle_command(chat_id, text)
            return

        # Handle prompt with AgentLoop
        await self.run_agent_prompt(chat_id, text)

    async def handle_command(self, chat_id: int, command_text: str) -> None:
        """Process Telegram bot commands."""
        parts = command_text.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "/start":
            welcome = (
                f"👋 <b>Welcome to cyc Telegram Gateway</b> (v{__version__})\n\n"
                f"• <b>Workspace:</b> <code>{self.workspace_path}</code>\n"
                f"• <b>Default Provider:</b> <code>{self.config.default_provider}</code>\n"
                f"• <b>Mode:</b> <code>{self.chat_modes.get(chat_id, 'agent')}</code>\n\n"
                "<b>Commands:</b>\n"
                "/mode &lt;chat|agent&gt; - Switch mode\n"
                "/status - Check workspace and session status\n"
                "/undo - Undo last session turn\n"
                "/stop - Stop running agent task\n"
                "/clear - Reset conversation session\n"
                "/help - Show command manual\n\n"
                "Send any text to start pair programming!"
            )
            await self.client.send_message(chat_id=chat_id, text=welcome)

        elif cmd == "/mode":
            if not args or args[0].lower() not in ("chat", "agent"):
                curr = self.chat_modes.get(chat_id, "agent")
                await self.client.send_message(chat_id=chat_id, text=f"Current mode: <b>{curr}</b>\nUsage: <code>/mode agent</code> or <code>/mode chat</code>")
            else:
                new_mode = args[0].lower()
                self.chat_modes[chat_id] = new_mode
                session = self.get_session(chat_id)
                session.mode = new_mode
                await self.client.send_message(chat_id=chat_id, text=f"✅ Switched mode to <b>{new_mode}</b>.")

        elif cmd == "/status":
            session = self.get_session(chat_id)
            status_text = (
                f"📊 <b>cyc Status</b>\n\n"
                f"• <b>Version:</b> <code>v{__version__}</code>\n"
                f"• <b>Workspace:</b> <code>{self.workspace_path}</code>\n"
                f"• <b>Session ID:</b> <code>{session.session_id}</code>\n"
                f"• <b>Mode:</b> <code>{self.chat_modes.get(chat_id, 'agent')}</code>\n"
                f"• <b>Messages:</b> <code>{len(session.messages)}</code>\n"
                f"• <b>Auto-Approve:</b> <code>{self.auto_approve}</code>"
            )
            await self.client.send_message(chat_id=chat_id, text=status_text)

        elif cmd == "/stop":
            task = self.chat_running_tasks.get(chat_id)
            if task and not task.done():
                task.cancel()
                await self.client.send_message(chat_id=chat_id, text="⏹️ Agent task has been cancelled.")
            else:
                await self.client.send_message(chat_id=chat_id, text="ℹ️ No agent task currently running.")

        elif cmd == "/undo":
            session = self.get_session(chat_id)
            # Remove last turn (user + assistant/tools)
            if session.messages:
                last_role = session.messages[-1].get("role")
                while session.messages and session.messages[-1].get("role") in ("tool", "assistant"):
                    session.messages.pop()
                if session.messages and session.messages[-1].get("role") == "user":
                    session.messages.pop()
                session.auto_save()
                await self.client.send_message(chat_id=chat_id, text="↩️ Undid last interaction turn.")
            else:
                await self.client.send_message(chat_id=chat_id, text="ℹ️ Session is empty, nothing to undo.")

        elif cmd == "/clear":
            session = self.get_session(chat_id)
            session.messages.clear()
            session.auto_save()
            await self.client.send_message(chat_id=chat_id, text="🧹 Conversation session cleared.")

        elif cmd == "/help":
            help_text = (
                "📖 <b>cyc Telegram Bot Commands</b>\n\n"
                "• <b>/start</b> - Show welcome overview\n"
                "• <b>/mode [chat|agent]</b> - Toggle chat or agent loop\n"
                "• <b>/status</b> - Current system and session state\n"
                "• <b>/undo</b> - Undo previous turn\n"
                "• <b>/stop</b> - Interrupt active task\n"
                "• <b>/clear</b> - Reset chat history\n\n"
                "💡 <i>Tip:</i> Mutation actions (editing files, executing shell commands) will prompt you with inline buttons to Approve or Deny unless auto-approve is enabled."
            )
            await self.client.send_message(chat_id=chat_id, text=help_text)

        else:
            await self.client.send_message(chat_id=chat_id, text=f"Unknown command: <code>{escape_html(cmd)}</code>. Type /help for available commands.")

    async def run_agent_prompt(self, chat_id: int, prompt: str) -> None:
        """Run agent loop for the user query with streaming update and approval handling."""
        # Cancel previous running task if any
        prev_task = self.chat_running_tasks.get(chat_id)
        if prev_task and not prev_task.done():
            prev_task.cancel()

        task = asyncio.create_task(self._execute_agent_prompt(chat_id, prompt))
        self.chat_running_tasks[chat_id] = task

    async def _execute_agent_prompt(self, chat_id: int, prompt: str) -> None:
        session = self.get_session(chat_id)
        mode = self.chat_modes.get(chat_id, "agent")
        provider_cfg = self.config.get_provider()
        provider_inst = create_provider(provider_cfg)

        init_msg = await self.client.send_message(
            chat_id=chat_id,
            text="🤔 <i>Thinking...</i>",
        )
        msg_id = init_msg.get("message_id")

        last_update_time = 0.0
        accumulated_text = ""

        async def throttle_edit(new_content: str, force: bool = False):
            nonlocal last_update_time
            now = time.time()
            if not force and (now - last_update_time < self.throttle_seconds):
                return
            last_update_time = now
            html_text = format_markdown_to_telegram_html(new_content)
            # If length exceeds 4000, take first 4000
            if len(html_text) > 4000:
                html_text = html_text[:3990] + "..."
            try:
                if msg_id:
                    await self.client.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=html_text or "⏳ <i>Processing...</i>",
                        parse_mode="HTML",
                    )
            except Exception:
                pass

        async def tg_confirmation_handler(tool, args, prompt_text) -> bool:
            """Render HITL confirmation card with inline keyboard."""
            approval_id = os.urandom(6).hex()
            fut = asyncio.get_running_loop().create_future()
            self.pending_approvals[approval_id] = fut

            # Generate diff preview if applicable
            diff_text = None
            if tool.name == "replace_file_content":
                fp = args.get("path", "")
                target = args.get("target", "")
                repl = args.get("replacement", "")
                orig_file = Path(fp).expanduser()
                if orig_file.exists() and orig_file.is_file():
                    orig_str = orig_file.read_text(encoding="utf-8", errors="replace")
                    new_str = orig_str.replace(target, repl, 1)
                    diff_text = generate_unified_diff(fp, orig_str, new_str)
            elif tool.name == "write_file":
                fp = args.get("path", "")
                new_str = args.get("content", "")
                orig_file = Path(fp).expanduser()
                orig_str = orig_file.read_text(encoding="utf-8", errors="replace") if orig_file.exists() else ""
                diff_text = generate_unified_diff(fp, orig_str, new_str)

            # Build message text
            card_lines = [
                f"⚠️ <b>Approval Required: <code>{escape_html(tool.name)}</code></b>\n",
            ]
            if tool.name == "run_command":
                card_lines.append(f"<b>Command:</b> <code>{escape_html(args.get('command', ''))}</code>")
                card_lines.append(f"<b>Directory:</b> <code>{escape_html(args.get('cwd', '.'))}</code>")
            elif diff_text:
                card_lines.append(f"<b>File:</b> <code>{escape_html(args.get('path', ''))}</code>\n")
                diff_sample = "\n".join(diff_text.splitlines()[:15])
                card_lines.append(f"<pre><code>{escape_html(diff_sample)}</code></pre>")
            else:
                card_lines.append(f"<b>Arguments:</b> <code>{escape_html(str(args))}</code>")

            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"approve:{approval_id}"},
                        {"text": "❌ Deny", "callback_data": f"deny:{approval_id}"},
                    ]
                ]
            }

            await self.client.send_message(
                chat_id=chat_id,
                text="\n".join(card_lines),
                reply_markup=keyboard,
            )

            try:
                approved = await fut
                return bool(approved)
            finally:
                self.pending_approvals.pop(approval_id, None)

        async def tg_event_callback(event: Dict[str, Any]):
            nonlocal accumulated_text
            etype = event.get("type")
            if etype == "thinking":
                turn = event.get("turn", 1)
                max_t = event.get("max_turns", 100)
                await throttle_edit(f"🤖 <i>Agent working (turn {turn}/{max_t})...</i>")
            elif etype == "message":
                content = event.get("content", "")
                accumulated_text = content
                await throttle_edit(accumulated_text)
            elif etype == "tool_call":
                tname = event.get("name")
                call_notice = f"\n\n⚙️ <i>Executing tool: <code>{escape_html(tname)}</code>...</i>"
                await throttle_edit(accumulated_text + call_notice)

        perm_mode = PermissionMode.AUTO if self.auto_approve else PermissionMode.INTERACTIVE
        permission_mgr = PermissionManager(
            mode=perm_mode,
            confirmation_handler=tg_confirmation_handler if not self.auto_approve else None,
        )

        searxng_url = self.config.agent.searxng_url
        tool_registry = ToolRegistry(get_default_tools(searxng_url=searxng_url))

        agent_loop = AgentLoop(
            provider=provider_inst,
            model=self.config.default_model,
            session=session,
            tool_registry=tool_registry,
            permission_manager=permission_mgr,
            max_turns=self.config.agent.max_turns,
            event_callback=tg_event_callback,
        )

        try:
            result = await agent_loop.run_turn(prompt)
            # Final output formatting
            final_html = format_markdown_to_telegram_html(result or accumulated_text or "Done.")
            chunks = chunk_message(final_html, max_length=4000)

            # Edit initial message with first chunk
            if msg_id and chunks:
                await self.client.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=chunks[0],
                    parse_mode="HTML",
                )
                # Send subsequent chunks as separate messages
                for chunk in chunks[1:]:
                    await self.client.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")
            elif chunks:
                for chunk in chunks:
                    await self.client.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")

            session.auto_save()
        except asyncio.CancelledError:
            await self.client.send_message(chat_id=chat_id, text="🛑 Task execution stopped.")
        except Exception as e:
            await self.client.send_message(chat_id=chat_id, text=f"❌ Error: {escape_html(str(e))}")
