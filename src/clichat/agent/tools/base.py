from abc import ABC, abstractmethod
from typing import Any, Dict

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
