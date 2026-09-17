import asyncio
import json
import re
import shutil
from typing import AsyncGenerator, Dict, List, Optional

from clichat.providers.base import BaseProvider

DEFAULT_OPENCODE_ZEN_MODELS = [
    "opencode/nemotron-3.5-lightning-free",
    "opencode/deepseek-v4-flash-free",
    "opencode/hy3-free",
    "opencode/mimo-v2.5-free",
    "opencode/nemotron-3-ultra-free",
    "opencode/muse-spark-1.2-contributor-free",
]

class OpenCodeProvider(BaseProvider):
    def __init__(self, binary_path: Optional[str] = None):
        self.binary_path = binary_path or shutil.which("opencode") or "opencode"

    def _normalize_model(self, model: str) -> str:
        """Ensure the model has the opencode/ prefix if needed."""
        m = model.strip() if model else DEFAULT_OPENCODE_ZEN_MODELS[0]
        if not "/" in m:
            return f"opencode/{m}"
        return m

    def _format_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Format multi-turn conversation into a single prompt for opencode run."""
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
                f"OpenCode CLI binary '{self.binary_path}' not found in PATH. "
                "Please ensure opencode is installed or specify its path in config."
            )

        model_id = self._normalize_model(model)
        prompt = self._format_messages_to_prompt(messages)

        cmd = [
            self.binary_path,
            "run",
            "-m",
            model_id,
            "--format",
            "json",
            prompt,
        ]

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
                    # Handle OpenCode JSON event structures:
                    # {"type":"text", "part":{"type":"text", "text":"..."}}
                    # or {"type":"step_update", "step_update":{"text_delta":"..."}}
                    if data.get("type") == "text":
                        part = data.get("part", {})
                        text_val = part.get("text") or data.get("text")
                        if text_val:
                            yield text_val
                    elif data.get("part", {}).get("type") == "text":
                        text_val = data.get("part", {}).get("text")
                        if text_val:
                            yield text_val
                    elif "text_delta" in data:
                        yield data["text_delta"]
                except json.JSONDecodeError:
                    # Non-JSON line from stdout fallback
                    if not line_str.startswith("{") and not line_str.startswith(">"):
                        yield f"{line_str}\n"

            await proc.wait()
            if proc.returncode != 0:
                stderr_data = await proc.stderr.read()
                err_msg = stderr_data.decode("utf-8", errors="replace").strip()
                if err_msg:
                    raise RuntimeError(f"opencode process exited with code {proc.returncode}: {err_msg}")

        except (asyncio.CancelledError, KeyboardInterrupt):
            try:
                proc.terminate()
                await proc.wait()
            except Exception:
                pass
            raise

    async def list_models(self) -> List[str]:
        """List OpenCode Zen free models (under opencode/ with free in the name)."""
        if not shutil.which(self.binary_path):
            return DEFAULT_OPENCODE_ZEN_MODELS

        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                "models",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return DEFAULT_OPENCODE_ZEN_MODELS

            output = stdout.decode("utf-8", errors="replace")
            models: List[str] = []
            for line in output.splitlines():
                clean = re.sub(r"\x1b\[[0-9;]*[mK]", "", line).strip()
                # Filter specifically to OpenCode Zen free models: starts with opencode/ and contains 'free'
                if clean.startswith("opencode/") and "free" in clean.lower():
                    models.append(clean)

            return models if models else DEFAULT_OPENCODE_ZEN_MODELS
        except Exception:
            return DEFAULT_OPENCODE_ZEN_MODELS
