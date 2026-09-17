import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from clichat.agent.tools.base import Tool

MAX_READ_LINES = 250
MAX_READ_BYTES = 30 * 1024  # 30 KB limit

class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file from the filesystem. Can optionally specify start_line and end_line (1-indexed)."
    is_mutation = False
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read (relative to workspace or absolute).",
            },
            "start_line": {
                "type": "integer",
                "description": "Optional 1-indexed starting line number.",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional 1-indexed ending line number.",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, **kwargs) -> str:
        target = Path(path).expanduser()
        if not target.exists():
            return f"Error: File '{path}' does not exist."
        if not target.is_file():
            return f"Error: Path '{path}' is a directory, not a file. Use list_dir instead."

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            total_lines = len(lines)

            # Determine slice range
            s_idx = max(0, (start_line - 1)) if start_line is not None else 0
            e_idx = min(total_lines, end_line) if end_line is not None else total_lines

            sliced_lines = lines[s_idx:e_idx]
            truncated = False

            if len(sliced_lines) > MAX_READ_LINES:
                sliced_lines = sliced_lines[:MAX_READ_LINES]
                truncated = True

            output_lines = []
            for i, line in enumerate(sliced_lines, start=s_idx + 1):
                output_lines.append(f"{i:4d} | {line}")

            result = "\n".join(output_lines)
            if truncated:
                result += f"\n\n[Note: Output truncated. Showing first {MAX_READ_LINES} lines of {total_lines} total lines in file.]"
            return result
        except Exception as e:
            return f"Error reading file '{path}': {e}"

class WriteFileTool(Tool):
    name = "write_file"
    description = "Create a new file or completely overwrite an existing file with the provided content."
    is_mutation = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path of the file to write.",
            },
            "content": {
                "type": "string",
                "description": "Full text content to write into the file.",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, **kwargs) -> str:
        target = Path(path).expanduser()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content.encode('utf-8'))} bytes to '{path}'."
        except Exception as e:
            return f"Error writing to file '{path}': {e}"

class ReplaceFileContentTool(Tool):
    name = "replace_file_content"
    description = "Replace a precise block of text within an existing file. The target block must match the existing file content exactly."
    is_mutation = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to modify.",
            },
            "target": {
                "type": "string",
                "description": "Exact text block to replace in the file (must match exactly including indentation).",
            },
            "replacement": {
                "type": "string",
                "description": "New text block to insert in place of the target.",
            },
        },
        "required": ["path", "target", "replacement"],
    }

    async def execute(self, path: str, target: str, replacement: str, **kwargs) -> str:
        target_path = Path(path).expanduser()
        if not target_path.exists():
            return f"Error: File '{path}' does not exist."
        if not target_path.is_file():
            return f"Error: Path '{path}' is not a file."

        try:
            content = target_path.read_text(encoding="utf-8", errors="replace")
            count = content.count(target)
            if count == 0:
                return f"Error: Target text not found in '{path}'. Please ensure exact matching including whitespace."
            if count > 1:
                return f"Error: Target text found {count} times in '{path}'. Please specify more surrounding lines to make the target unique."

            new_content = content.replace(target, replacement, 1)
            target_path.write_text(new_content, encoding="utf-8")
            return f"Successfully replaced target block in '{path}'."
        except Exception as e:
            return f"Error replacing content in '{path}': {e}"

class ListDirTool(Tool):
    name = "list_dir"
    description = "List files and subdirectories in a directory up to a specified depth."
    is_mutation = False
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (defaults to current directory).",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum directory traversal depth (default 2).",
            },
        },
    }

    IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", "dist", "build"}

    async def execute(self, path: str = ".", max_depth: int = 2, **kwargs) -> str:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return f"Error: Directory '{path}' does not exist."
        if not root.is_dir():
            return f"Error: Path '{path}' is a file, not a directory."

        tree_lines = [f"{root.name}/"]

        def build_tree(current: Path, depth: int, prefix: str):
            if depth > max_depth:
                return
            try:
                entries = sorted(list(current.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                tree_lines.append(f"{prefix}└── [Permission Denied]")
                return

            # Filter out ignored directories
            filtered = [e for e in entries if e.name not in self.IGNORED_DIRS]
            total = len(filtered)
            for idx, entry in enumerate(filtered):
                is_last = (idx == total - 1)
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "

                if entry.is_dir():
                    tree_lines.append(f"{prefix}{connector}{entry.name}/")
                    build_tree(entry, depth + 1, prefix + sub_prefix)
                else:
                    tree_lines.append(f"{prefix}{connector}{entry.name}")

        build_tree(root, 1, "")
        return "\n".join(tree_lines)
