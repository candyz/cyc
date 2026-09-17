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
