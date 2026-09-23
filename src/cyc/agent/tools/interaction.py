import sys
from typing import Any, Callable, Dict, List, Optional
from rich.console import Console
from rich.prompt import Prompt
from cyc.agent.tools.base import Tool

console = Console()

class AskUserTool(Tool):
    """Tool that allows the agent to interactively ask the user clarifying questions."""
    name: str = "ask_user"
    description: str = (
        "Ask the user a clarifying question when requirements are ambiguous, underspecified, "
        "or require a user decision. Can provide optional choices/options for the user to select from."
    )
    is_mutation: bool = False
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user.",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of predefined choices for the user to select from.",
            },
            "multi_select": {
                "type": "boolean",
                "description": "Whether multiple options can be chosen (default: false).",
            },
        },
        "required": ["question"],
    }

    def __init__(self, interaction_handler: Optional[Callable[..., Any]] = None):
        self.interaction_handler = interaction_handler

    async def execute(
        self,
        question: str,
        options: Optional[List[str]] = None,
        multi_select: bool = False,
        **kwargs,
    ) -> str:
        """Prompt user via custom interaction handler or CLI rich prompt."""
        # 1. If an external handler (e.g. Web UI, Telegram bot) is registered
        if self.interaction_handler:
            try:
                import inspect
                if inspect.iscoroutinefunction(self.interaction_handler):
                    res = await self.interaction_handler(question=question, options=options, multi_select=multi_select)
                else:
                    res = self.interaction_handler(question=question, options=options, multi_select=multi_select)
                return str(res)
            except Exception as e:
                return f"Error interacting with user handler: {e}"

        # 2. Non-interactive fallback (e.g. CI, pipe, automated testing)
        if not sys.stdin.isatty():
            if options and len(options) > 0:
                return f"[Non-interactive environment] Selected default option: {options[0]}"
            return "[Non-interactive environment] User interaction not available."

        # 3. Interactive CLI Prompt
        console.print(f"\n[bold yellow]❓ Agent Clarification Question:[/bold yellow] {question}")

        if options and len(options) > 0:
            console.print("[dim]Please choose from the options below, or type a custom answer:[/dim]")
            for idx, opt in enumerate(options, 1):
                console.print(f"  [cyan]{idx}.[/cyan] {opt}")

            if multi_select:
                choice_str = Prompt.ask(
                    "[bold green]Enter numbers separated by comma (e.g. 1, 3) or custom answer[/bold green]",
                    default="1",
                ).strip()
                # Parse selections
                parts = [p.strip() for p in choice_str.split(",") if p.strip()]
                selected = []
                for p in parts:
                    if p.isdigit() and 1 <= int(p) <= len(options):
                        selected.append(options[int(p) - 1])
                    else:
                        selected.append(p)
                return f"User selected: {', '.join(selected)}"
            else:
                choice = Prompt.ask(
                    f"[bold green]Select an option [1-{len(options)}] or type custom answer[/bold green]",
                    default="1",
                ).strip()
                if choice.isdigit() and 1 <= int(choice) <= len(options):
                    return f"User selected: {options[int(choice) - 1]}"
                return f"User responded: {choice}"
        else:
            answer = Prompt.ask("[bold green]Your answer[/bold green]").strip()
            return f"User responded: {answer}"
