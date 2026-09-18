import asyncio
import json
import re
import shutil
from typing import Any, AsyncGenerator, Dict, List, Optional

from cyc.providers.base import BaseProvider

DEFAULT_AGY_MODELS = [
    "gemini-3.1-pro-high",
    "gemini-3.1-pro-low",
    "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium",
    "gemini-3.8-flash-low",
    "claude-sonnet-4-6",
]

class AntigravityProvider(BaseProvider):
    def __init__(self, binary_path: Optional[str] = None):
        self.binary_path = binary_path or shutil.which("agy") or "agy"

    def _format_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format multi-turn conversation into a single prompt for agy CLI."""
        if not messages:
            return ""
        if len(messages) == 1:
            return messages[0].get("content", "")

        formatted_turns = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                formatted_turns.append(f"[System Instructions]\n{content}\n")
            elif role == "user":
                formatted_turns.append(f"[User]\n{content}\n")
            elif role == "assistant":
                formatted_turns.append(f"[Assistant]\n{content}\n")

        formatted_turns.append("[Assistant Response]:")
        return "\n".join(formatted_turns)

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        if not shutil.which(self.binary_path):
            raise FileNotFoundError(
                f"Antigravity CLI binary '{self.binary_path}' not found in PATH. "
                "Please ensure agy is installed or specify its full path."
            )

        prompt = self._format_messages_to_prompt(messages)
        cmd = [
            self.binary_path,
            "--output-format",
            "stream-json",
            "--disable-slash-commands",
            "--dangerously-skip-permissions",
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["-p", prompt])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                    if data.get("event") == "step_update":
                        delta = data.get("step_update", {}).get("text_delta")
                        if delta:
                            yield delta
                except json.JSONDecodeError:
                    continue

            await proc.wait()
            if proc.returncode != 0:
                stderr_data = await proc.stderr.read()
                err_msg = stderr_data.decode("utf-8", errors="replace").strip()
                if err_msg:
                    raise RuntimeError(f"agy process failed with code {proc.returncode}: {err_msg}")

        except (asyncio.CancelledError, KeyboardInterrupt):
            try:
                proc.terminate()
                await proc.wait()
            except Exception:
                pass
            raise

    async def list_models(self) -> List[str]:
        if not shutil.which(self.binary_path):
            return DEFAULT_AGY_MODELS

        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                "models",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return DEFAULT_AGY_MODELS

            output = stdout.decode("utf-8", errors="replace")
            models: List[str] = []
            for line in output.splitlines():
                clean = re.sub(r"\x1b\[[0-9;]*[mK]", "", line)
                clean = re.sub(r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏\s]+", "", clean).strip()
                if clean:
                    parts = clean.split()
                    if parts:
                        model_id = parts[0]
                        if model_id and not model_id.startswith("Fetching"):
                            models.append(model_id)

            return models if models else DEFAULT_AGY_MODELS
        except Exception:
            return DEFAULT_AGY_MODELS

    async def get_usage_info(self, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        binary_available = bool(shutil.which(self.binary_path))
        return {
            "provider": "Google Antigravity (agy)",
            "tier": "Gemini AI Pro Subscription / Google Workspace",
            "model": model or "gemini-3.1-pro-high",
            "rate_limit": "Pro Subscription Quota (Managed by Google AGY)",
            "local_binary": "Installed" if binary_available else "Not Found",
        }

