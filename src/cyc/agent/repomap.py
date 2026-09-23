import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

# File extensions and corresponding language parsers
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
}

# Ignore common non-source directories
IGNORE_DIRS: Set[str] = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "target",
}

class RepoMap:
    """Generates a compact symbol map (classes, methods, functions) of the repository."""

    def __init__(self, root_dir: Optional[Path] = None, max_files: int = 200, max_tokens: int = 2000):
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.max_files = max_files
        self.max_tokens = max_tokens

    def _parse_python_file(self, content: str) -> List[str]:
        """Extract top-level classes and functions/methods using ast."""
        symbols = []
        try:
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    symbols.append(f"  class {node.name}")
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            # Check if private/dunder
                            symbols.append(f"    def {item.name}(...)")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(f"  def {node.name}(...)")
        except SyntaxError:
            # Fallback to regex if syntax error (e.g. newer syntax or template)
            symbols = self._parse_regex(content, "python")
        return symbols

    def _parse_regex(self, content: str, lang: str) -> List[str]:
        """Generic regex symbol extractor for JS/TS/Go/Rust/Python fallback."""
        symbols = []
        lines = content.splitlines()

        if lang in ("javascript", "typescript"):
            # matches: function name, class name, const/let name = ... =>, export default function
            pattern = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+([a-zA-Z0-9_$]+)|class\s+([a-zA-Z0-9_$]+)|interface\s+([a-zA-Z0-9_$]+)|type\s+([a-zA-Z0-9_$]+)|(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\()")
            for line in lines:
                m = pattern.search(line)
                if m:
                    name = next(g for g in m.groups() if g is not None)
                    symbols.append(f"  {line.strip()[:60]}")
        elif lang == "go":
            pattern = re.compile(r"^\s*(?:func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)|type\s+([a-zA-Z0-9_]+)\s+struct|type\s+([a-zA-Z0-9_]+)\s+interface)")
            for line in lines:
                m = pattern.search(line)
                if m:
                    symbols.append(f"  {line.strip()[:60]}")
        elif lang == "rust":
            pattern = re.compile(r"^\s*(?:pub\s+)?(?:fn\s+([a-zA-Z0-9_]+)|struct\s+([a-zA-Z0-9_]+)|enum\s+([a-zA-Z0-9_]+)|trait\s+([a-zA-Z0-9_]+)|impl(?:\s+.*)?\s+([a-zA-Z0-9_]+))")
            for line in lines:
                m = pattern.search(line)
                if m:
                    symbols.append(f"  {line.strip()[:60]}")
        elif lang == "python":
            pattern = re.compile(r"^\s*(?:class\s+([a-zA-Z0-9_]+)|def\s+([a-zA-Z0-9_]+))")
            for line in lines:
                m = pattern.search(line)
                if m:
                    symbols.append(f"  {line.strip()[:60]}")

        return symbols[:30]  # Cap per-file symbols

    def generate_map(self) -> str:
        """Scan workspace and generate a concise tree of files and symbols."""
        if not self.root_dir.exists():
            return "Workspace directory does not exist."

        collected_files = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    collected_files.append(Path(root) / f)
                    if len(collected_files) >= self.max_files:
                        break
            if len(collected_files) >= self.max_files:
                break

        if not collected_files:
            return "No supported source files found in workspace."

        collected_files.sort(key=lambda p: str(p.relative_to(self.root_dir)))

        map_lines = []
        approx_chars = 0
        max_chars = self.max_tokens * 4

        for file_path in collected_files:
            try:
                rel_path = file_path.relative_to(self.root_dir)
                ext = file_path.suffix.lower()
                lang = SUPPORTED_EXTENSIONS.get(ext, "")
                content = file_path.read_text(encoding="utf-8", errors="replace")

                if lang == "python":
                    symbols = self._parse_python_file(content)
                else:
                    symbols = self._parse_regex(content, lang)

                file_header = f"{rel_path}:"
                entry_lines = [file_header] + symbols
                entry_text = "\n".join(entry_lines) + "\n"

                if approx_chars + len(entry_text) > max_chars:
                    map_lines.append(f"... [Repo map truncated to fit token budget ({len(collected_files)} total files)]")
                    break

                map_lines.append(entry_text)
                approx_chars += len(entry_text)
            except Exception:
                continue

        return "\n".join(map_lines).strip()
