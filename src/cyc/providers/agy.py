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

    @staticmethod
    def format_reset_time(seconds: float) -> str:
        s = int(seconds)
        if s <= 0:
            return "0m"
        d = s // 86400
        h = (s % 86400) // 3600
        m = (s % 3600) // 60
        if d > 0:
            return f"{d}d {h}h"
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"

    @classmethod
    def get_quota_info(cls, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Read and parse 5h and 7d quota information for the specified model from cached statusline JSON."""
        from pathlib import Path

        candidates = [
            Path.home() / ".gemini" / "antigravity-cli" / "cache" / "statusline_input.json",
            Path("/tmp/statusline_input.json"),
        ]
        data = None
        for p in candidates:
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data and isinstance(data, dict) and "quota" in data:
                        break
                except Exception:
                    data = None

        if not data or not isinstance(data.get("quota"), dict):
            return None

        quota_dict = data["quota"]
        model_str = (model or "").lower()

        # Determine filtering keyword: 'gemini' vs '3p'
        if "gemini" in model_str:
            kw = "gemini"
        elif any(k in model_str for k in ("claude", "gpt", "sonnet", "3p")):
            kw = "3p"
        else:
            default_id = str(data.get("model", {}).get("id", "")).lower()
            kw = "gemini" if "gemini" in default_id else "3p"

        # Filter buckets containing the keyword with valid remaining_fraction & reset_in_seconds
        valid_items = []
        for k, v in quota_dict.items():
            if isinstance(v, dict) and v.get("remaining_fraction") is not None and v.get("reset_in_seconds") is not None:
                valid_items.append((k, v))

        filtered = [it for it in valid_items if kw in it[0].lower()]
        items_to_use = filtered if filtered else valid_items
        if not items_to_use:
            return None

        # Sort by reset_in_seconds ascending: short window (5h) first, long window (7d) second
        items_to_use.sort(key=lambda it: it[1].get("reset_in_seconds", 0))

        res: Dict[str, Any] = {
            "plan_tier": data.get("plan_tier", "Google AI Pro"),
            "keyword": kw,
        }

        if len(items_to_use) >= 1:
            k1, v1 = items_to_use[0]
            rem_frac1 = float(v1.get("remaining_fraction", 1.0))
            reset_secs1 = float(v1.get("reset_in_seconds", 0))
            used1 = max(0, min(100, round((1.0 - rem_frac1) * 100)))
            res["5h"] = {
                "name": k1,
                "used_pct": used1,
                "remaining_pct": 100 - used1,
                "reset_seconds": reset_secs1,
                "reset_str": cls.format_reset_time(reset_secs1),
            }

        if len(items_to_use) >= 2:
            k2, v2 = items_to_use[1]
            rem_frac2 = float(v2.get("remaining_fraction", 1.0))
            reset_secs2 = float(v2.get("reset_in_seconds", 0))
            used2 = max(0, min(100, round((1.0 - rem_frac2) * 100)))
            res["7d"] = {
                "name": k2,
                "used_pct": used2,
                "remaining_pct": 100 - used2,
                "reset_seconds": reset_secs2,
                "reset_str": cls.format_reset_time(reset_secs2),
            }

        return res

    async def get_usage_info(self, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        binary_available = bool(shutil.which(self.binary_path))
        quota = self.get_quota_info(model)
        plan = (quota.get("plan_tier") if quota else None) or "Pro"
        tier = f"{plan} (Gemini AI Pro Subscription / Google Workspace)"

        rate_limit_desc = "Pro Subscription Quota (Managed by Google AGY)"
        if quota and "5h" in quota and "7d" in quota:
            q5 = quota["5h"]
            q7 = quota["7d"]
            rate_limit_desc = f"5h: {q5['used_pct']}% used (↻ {q5['reset_str']}) | 7d: {q7['used_pct']}% used (↻ {q7['reset_str']})"

        info = {
            "provider": "Google Antigravity (agy)",
            "tier": tier,
            "model": model or "gemini-3.1-pro-high",
            "rate_limit": rate_limit_desc,
            "local_binary": "Installed" if binary_available else "Not Found",
        }
        if quota:
            info["quota"] = quota
        return info

