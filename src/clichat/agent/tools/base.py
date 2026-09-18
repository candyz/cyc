import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class Tool(ABC):
    name: str
    description: str
    parameters: Dict[str, Any]
    is_mutation: bool = False

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool asynchronously and return a string result (observation)."""
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        """Format as OpenAI Function Calling JSON schema (for OpenRouter, Ollama, NVIDIA)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_gemini_tool(self) -> Dict[str, Any]:
        """Format as Gemini FunctionDeclaration schema (for Google GenAI SDK)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

def truncate_tool_output(
    output: str,
    max_lines: int = 250,
    max_chars: int = 30_000,
    head_lines: int = 150,
    tail_lines: int = 60,
    head_chars: int = 20_000,
    tail_chars: int = 8_000,
) -> str:
    """Safely truncate oversized tool observations using a head+tail preservation strategy.
    
    Ensures that tool outputs cannot blow up model context or exceed token boundaries,
    while preserving both the beginning (command header, start of trace) and the end
    (final exit messages, error stack traces).
    """
    if not output:
        return output

    lines = output.splitlines()
    total_lines = len(lines)
    total_chars = len(output)

    line_truncated = total_lines > max_lines
    char_truncated = total_chars > max_chars

    if not line_truncated and not char_truncated:
        return output

    # 1. First line-level truncation if line count exceeds max_lines
    if line_truncated:
        if head_lines + tail_lines >= total_lines:
            # Fallback if thresholds are tight
            selected_lines = lines[:max_lines]
            omitted_count = total_lines - len(selected_lines)
            output = "\n".join(selected_lines) + f"\n\n... [Output truncated: omitted {omitted_count} lines. Consider viewing specific line ranges or piping through grep/tail/head] ..."
        else:
            h_lines = lines[:head_lines]
            t_lines = lines[-tail_lines:]
            omitted_lines = total_lines - head_lines - tail_lines
            marker = f"\n\n... [Output truncated: omitted {omitted_lines} lines ({head_lines} head / {tail_lines} tail preserved). Refine query or specify line ranges/grep] ...\n\n"
            output = "\n".join(h_lines) + marker + "\n".join(t_lines)

    # 2. Character-level truncation if string length still exceeds max_chars
    if len(output) > max_chars:
        omitted_chars = len(output) - (head_chars + tail_chars)
        if omitted_chars > 0:
            h_part = output[:head_chars]
            t_part = output[-tail_chars:]
            marker = f"\n\n... [Output truncated: omitted {omitted_chars} characters ({head_chars} head / {tail_chars} tail preserved). Consider filtering output] ...\n\n"
            output = h_part + marker + t_part
        else:
            output = output[:max_chars] + f"\n\n... [Output truncated to {max_chars} characters] ..."

    return output

def enrich_tool_error_observation(tool_name: str, observation: str, arguments: Optional[Dict[str, Any]] = None) -> str:
    """Enrich tool error observations with intelligent diagnostic recovery hints.

    Provides actionable guidance for LLMs when tools fail due to common errors
    (missing files, non-unique target strings in replace_file_content, unrecognized tools, permission denied, command exit errors).
    """
    if not observation or not isinstance(observation, str):
        return observation

    args = arguments or {}
    lower_obs = observation.lower()

    # Only provide recovery advice if it's an error observation
    is_err = lower_obs.startswith("error") or "error:" in lower_obs or "exit code: " in lower_obs

    if not is_err:
        return observation

    hints: List[str] = []

    # 1. Unrecognized / Unknown tool
    if "is not recognized" in lower_obs:
        hints.append("Suggested Action: Check available tools with proper naming (e.g. read_file, write_file, replace_file_content, run_command, run_script, list_dir, grep_search). Do not invent unregistered tool names.")

    # 2. replace_file_content specific errors
    elif "target text not found" in lower_obs:
        hints.append("Suggested Action: Exact match failed. Call `read_file` to view the latest lines, check exact whitespace and indentation, and retry with the exact verbatim snippet.")

    elif "found" in lower_obs and "times" in lower_obs and tool_name == "replace_file_content":
        hints.append("Suggested Action: The replacement target is ambiguous. Include 2-3 additional lines of surrounding context (or function/class signature) above and below to make the target block unique.")

    # 3. Path is a directory when a file was expected
    elif "is a directory, not a file" in lower_obs or "is a directory" in lower_obs:
        hints.append("Suggested Action: The target is a folder. Use `list_dir(path=...)` instead of `read_file` to inspect its contents.")

    # 4. File does not exist / not found
    elif "does not exist" in lower_obs or "no such file or directory" in lower_obs or "file not found" in lower_obs:
        target_path = args.get("path") or args.get("file") or args.get("cwd") or ""
        if target_path:
            hints.append(f"Suggested Action: The path '{target_path}' could not be found. Use `list_dir` to inspect the directory structure or `grep_search` to verify the actual location and filename.")
        else:
            hints.append("Suggested Action: Verify the path by calling `list_dir` or `grep_search` before attempting to access or edit it.")

    # 5. Permission denied by user or system
    elif "permission was denied" in lower_obs or "permission denied" in lower_obs or "denied by the user" in lower_obs:
        hints.append("Suggested Action: Explain to the user why this action was necessary, and either propose an alternative read-only/non-mutating approach or request permission explicitly.")

    # 6. Non-zero command exit code or execution failure
    elif "exit code: " in lower_obs:
        # Check if exit code is non-zero
        m = re.search(r"exit code:\s*(\d+)", lower_obs)
        if m and m.group(1) != "0":
            code = m.group(1)
            hints.append(f"Suggested Action: The command failed with exit code {code}. Carefully review stderr above, check syntax or missing dependencies/flags, and adjust command parameters.")

    # 7. Command timed out
    elif "timed out after" in lower_obs:
        hints.append("Suggested Action: The command took too long to complete. Consider specifying a larger `timeout` parameter or running with background/non-interactive flags.")

    if hints:
        recovery_text = "\n\n[Diagnostic Self-Repair Hint]\n" + "\n".join(f"• {h}" for h in hints)
        return observation + recovery_text

    return observation
