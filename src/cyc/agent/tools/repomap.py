from pathlib import Path
from typing import Any, Dict, Optional
from cyc.agent.repomap import RepoMap
from cyc.agent.tools.base import Tool

class RepoMapTool(Tool):
    """Tool that returns a compact symbol outline and map of code files in the repository."""
    name: str = "repo_map"
    description: str = (
        "Generate a compact outline of repository source files and code symbols (classes, methods, functions). "
        "Useful for understanding project structure, finding definitions, and discovering architecture before diving in."
    )
    is_mutation: bool = False
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional subdirectory to restrict the repo map to. Defaults to workspace root.",
            },
        },
    }

    async def execute(self, path: Optional[str] = None, **kwargs) -> str:
        root_dir = Path(path).expanduser().resolve() if path else Path.cwd().resolve()
        if not root_dir.exists():
            return f"Error: Directory '{root_dir}' does not exist."
        if not root_dir.is_dir():
            return f"Error: Path '{root_dir}' is a file, not a directory."

        mapper = RepoMap(root_dir=root_dir, max_files=150, max_tokens=1500)
        return mapper.generate_map()
