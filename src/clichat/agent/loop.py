import json
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from clichat.agent.permissions import PermissionManager
from clichat.agent.tools import ToolRegistry
from clichat.providers.base import AgentTurnResponse, BaseProvider
from clichat.providers.gemini import GeminiProvider
from clichat.session import SessionManager

console = Console()

class AgentLoop:
    def __init__(
        self,
        provider: BaseProvider,
        model: str,
        session: SessionManager,
        tool_registry: Optional[ToolRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
        max_turns: int = 15,
        ui: Optional[Any] = None,
        strategy: str = "standard",
    ):
        self.provider = provider
        self.model = model
        self.session = session
        self.tool_registry = tool_registry or ToolRegistry()
        self.permission_manager = permission_manager or PermissionManager()
        self.max_turns = max_turns
        self.ui = ui
        self.strategy = strategy.lower()  # "standard", "plan", "minimal"

    def _render_tool_call_card(self, tool_name: str, args: Dict[str, Any]):
        args_formatted = json.dumps(args, ensure_ascii=False, indent=2)
        console.print(Panel(
            args_formatted,
            title=f"[bold cyan]⚙️  Agent Tool Call: {tool_name}[/bold cyan]",
            border_style="cyan",
            expand=False,
        ))

    def _render_tool_result_preview(self, tool_name: str, result: str):
        lines = result.splitlines()
        preview = "\n".join(lines[:6])
        if len(lines) > 6:
            preview += f"\n... [{len(lines) - 6} more lines]"
        console.print(Panel(
            preview,
            title=f"[dim green]✓ Observation: {tool_name}[/dim green]",
            border_style="dim green",
            expand=False,
        ))

    async def run_turn(self, user_prompt: str) -> str:
        """Execute autonomous agent loop for a user query according to current strategy."""
        # In 'plan' strategy, prepend planning guidance if it's a new complex request
        effective_prompt = user_prompt
        if self.strategy == "plan":
            effective_prompt = (
                f"{user_prompt}\n\n"
                "[Instruction: Execute using Plan-and-Solve mode. First output a brief bullet-point plan of actions "
                "before invoking tools. Follow each step and verify the result.]"
            )

        self.session.add_user_message(effective_prompt)

        # Minimal strategy caps turns to 3
        effective_max_turns = 3 if self.strategy == "minimal" else self.max_turns

        turn_count = 0
        final_content = ""

        while turn_count < effective_max_turns:
            turn_count += 1

            # Prepare tool definitions suitable for provider
            if isinstance(self.provider, GeminiProvider):
                tools = self.tool_registry.to_gemini_tools()
            else:
                tools = self.tool_registry.to_openai_tools()

            # Query model with tool definitions
            with console.status(f"[dim cyan]Agent thinking (turn {turn_count}/{effective_max_turns})...[/dim cyan]", spinner="dots"):
                response: AgentTurnResponse = await self.provider.chat_with_tools(
                    messages=self.session.get_messages(),
                    model=self.model,
                    tools=tools,
                )

            # Check if model wants to invoke tools
            if response.has_tool_calls:
                # Add assistant message with tool_calls structure to session
                raw_tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
                self.session.messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": raw_tool_calls,
                })

                if response.content:
                    if self.ui and hasattr(self.ui, "render_formatted_response"):
                        self.ui.render_formatted_response(response.content)
                    else:
                        console.print(Markdown(response.content))

                for tc in response.tool_calls:
                    self._render_tool_call_card(tc.name, tc.arguments)

                    try:
                        tool = self.tool_registry.get(tc.name)
                        permitted = await self.permission_manager.check_permission(tool, tc.arguments)
                        if permitted:
                            with console.status(f"[dim cyan]Executing tool: {tc.name}...[/dim cyan]", spinner="dots"):
                                observation = await tool.execute(**tc.arguments)
                            self._render_tool_result_preview(tc.name, observation)
                        else:
                            observation = "Error: Execution of this tool was denied by the user."
                    except KeyError:
                        observation = f"Error: Tool '{tc.name}' is not recognized."
                    except Exception as e:
                        observation = f"Error executing tool '{tc.name}': {e}"

                    # Append tool result to session
                    self.session.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": observation,
                    })

                # Loop continues with tool observations now in context
                continue

            # Model did not call any tools -> final answer reached
            final_content = response.content or ""
            if final_content:
                if self.ui and hasattr(self.ui, "render_formatted_response"):
                    self.ui.render_formatted_response(final_content)
                else:
                    console.print(Markdown(final_content))
                self.session.add_assistant_message(final_content)
            break

        if turn_count >= self.max_turns:
            console.print(f"[bold yellow]Warning: Reached maximum agent loop limit ({self.max_turns} turns).[/bold yellow]")

        return final_content
