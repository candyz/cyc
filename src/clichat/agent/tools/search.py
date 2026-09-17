import asyncio
import re
import shutil
from pathlib import Path
from typing import List, Optional
from clichat.agent.tools.base import Tool

MAX_MATCHES = 50

class GrepSearchTool(Tool):
    name = "grep_search"
    description = "Search for a pattern (regular expression or string) across files in a directory."
    is_mutation = False
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex or string pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory or file path to search within (default: current directory).",
            },
            "include": {
                "type": "string",
                "description": "File glob filter, e.g. '*.py' or '*.ts'.",
            },
        },
        "required": ["pattern"],
    }

    IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}

    async def execute(self, pattern: str, path: str = ".", include: Optional[str] = None, **kwargs) -> str:
        search_path = Path(path).expanduser().resolve()
        if not search_path.exists():
            return f"Error: Path '{path}' does not exist."

        # If ripgrep (rg) is installed, use it for optimal speed
        rg_path = shutil.which("rg")
        if rg_path:
            cmd = [rg_path, "--line-number", "--max-count", str(MAX_MATCHES), "--heading"]
            for d in self.IGNORED_DIRS:
                cmd.extend(["--glob", f"!{d}/*"])
            if include:
                cmd.extend(["--glob", include])
            cmd.extend([pattern, str(search_path)])

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_data, _ = await proc.communicate()
                out_str = stdout_data.decode("utf-8", errors="replace").strip()
                if out_str:
                    lines = out_str.splitlines()
                    if len(lines) > 100:
                        out_str = "\n".join(lines[:100]) + f"\n\n[Note: Truncated to first 100 lines]"
                    return out_str
                return f"No matches found for pattern '{pattern}' in '{path}'."
            except Exception:
                pass  # Fallback to python search if rg execution fails

        # Pure Python fallback
        matches: List[str] = []
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regular expression pattern '{pattern}': {e}"

        files_to_search: List[Path] = []
        if search_path.is_file():
            files_to_search = [search_path]
        else:
            for p in search_path.rglob("*"):
                # Exclude ignored dirs
                if any(ignored in p.parts for ignored in self.IGNORED_DIRS):
                    continue
                if p.is_file():
                    if include and not p.match(include):
                        continue
                    files_to_search.append(p)

        for file_p in files_to_search:
            try:
                content = file_p.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), start=1):
                    if regex.search(line):
                        rel_path = file_p.relative_to(search_path) if search_path.is_dir() else file_p.name
                        matches.append(f"{rel_path}:{i}: {line.strip()}")
                        if len(matches) >= MAX_MATCHES:
                            break
                if len(matches) >= MAX_MATCHES:
                    break
            except Exception:
                continue

        if not matches:
            return f"No matches found for pattern '{pattern}' in '{path}'."

        result = "\n".join(matches)
        if len(matches) >= MAX_MATCHES:
            result += f"\n\n[Note: Capped at maximum {MAX_MATCHES} matches.]"
        return result
