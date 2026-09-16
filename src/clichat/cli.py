import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from prompt_toolkit import PromptSession
from rich.console import Console

from clichat.config import Config, init_config_file, load_config
from clichat.providers import create_provider
from clichat.providers.base import BaseProvider
from clichat.session import SessionManager
from clichat.ui import TerminalUI, create_prompt_session

console = Console()
HISTORY_FILE = Path.home() / ".local" / "share" / "clichat" / "history"

class CliApp:
    def __init__(self, config: Config, provider_name: Optional[str] = None, model_name: Optional[str] = None):
        self.config = config
        self.provider_name = provider_name or config.default_provider
        self.provider_config = config.get_provider(self.provider_name)
        self.model = model_name or self.provider_config.default_model or config.default_model
        self.provider: BaseProvider = create_provider(self.provider_config)
        self.session = SessionManager()
        self.ui = TerminalUI(stream_markdown=config.ui.markdown_render)
        self.cached_models: List[str] = []
        self.multiline_mode: bool = False

    def get_known_models(self) -> List[str]:
        return self.cached_models

    def get_known_providers(self) -> List[str]:
        return list(self.config.providers.keys())

    async def update_cached_models(self) -> None:
        try:
            models = await self.provider.list_models()
            if self.provider_name.lower() == "openrouter":
                self.cached_models = [m for m in models if m.lower().endswith("free")]
            else:
                self.cached_models = models
        except Exception:
            self.cached_models = []

    def switch_provider(self, provider_name: str, model_name: Optional[str] = None):
        self.provider_config = self.config.get_provider(provider_name)
        self.provider_name = provider_name
        self.provider = create_provider(self.provider_config)
        self.model = model_name or self.provider_config.default_model or self.config.default_model
        console.print(f"[bold green]Switched to provider:[/bold green] {self.provider_name} (model: {self.model})")
        # Trigger background model cache refresh
        asyncio.create_task(self.update_cached_models())

    async def run_single_prompt(self, user_prompt: str) -> None:
        self.session.add_user_message(user_prompt)
        try:
            stream_gen = self.provider.chat_stream(self.session.get_messages(), self.model)
            response_text = ""
            # In single prompt mode, stream directly to stdout
            async for chunk in stream_gen:
                sys.stdout.write(chunk)
                sys.stdout.flush()
                response_text += chunk
            sys.stdout.write("\n")
            sys.stdout.flush()
            self.session.add_assistant_message(response_text)
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}")

    async def handle_slash_command(self, cmd: str) -> bool:
        """Handle slash commands. Return True if command was handled."""
        parts = cmd.strip().split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if action in ("/quit", "/exit"):
            console.print("[dim]Goodbye![/dim]")
            sys.exit(0)
        elif action == "/clear":
            self.session.clear()
            console.print("[bold yellow]Session history cleared.[/bold yellow]")
            return True
        elif action == "/help":
            console.print("""[bold cyan]Available Commands:[/bold cyan]
  /help               Show this help message
  /models             List available models for the active provider
  /model <name>       Switch active model (tab-completion supported)
  /provider <name>    Switch active provider (tab-completion supported)
  /system <prompt>    Set or inspect system prompt
  /tokens             Show context token usage statistics
  /multiline          Toggle multi-line input mode
  /save <filepath>    Save current conversation to Markdown (.md) or JSON (.json)
  /load <filepath>    Load previous conversation from a JSON file
  /clear              Clear current session history
  /exit or /quit      Exit CLI""")
            return True
        elif action == "/multiline":
            self.multiline_mode = not self.multiline_mode
            status = "[bold green]ON[/bold green] (Press Esc+Enter to submit)" if self.multiline_mode else "[bold yellow]OFF[/bold yellow] (Press Enter to submit, Alt+Enter for newline)"
            console.print(f"Multi-line mode: {status}")
            return True
        elif action == "/models":
            console.print("[dim]Fetching models...[/dim]")
            try:
                raw_models = await self.provider.list_models()
                if self.provider_name.lower() == "openrouter":
                    show_all = arg.lower() in ("--all", "-a", "all")
                    display_models = raw_models if show_all else [m for m in raw_models if m.lower().endswith("free")]
                    self.cached_models = [m for m in raw_models if m.lower().endswith("free")]
                else:
                    display_models = raw_models
                    self.cached_models = raw_models

                if display_models:
                    self.ui.print_models_table(display_models, self.model, self.provider_name)
                    if self.provider_name.lower() == "openrouter" and not arg.lower() in ("--all", "-a", "all"):
                        console.print("[dim]Tip: Filtered to free models (*free). Use '/models --all' to show all models.[/dim]")
                else:
                    console.print(f"[yellow]No models found or listing not supported by provider '{self.provider_name}'.[/yellow]")
            except Exception as e:
                console.print(f"[bold red]Failed to fetch models:[/bold red] {e}")
            return True
        elif action == "/model":
            if not arg:
                console.print(f"Current model: [bold green]{self.model}[/bold green]")
            else:
                self.model = arg
                console.print(f"[bold green]Switched model to:[/bold green] {self.model}")
            return True
        elif action == "/provider":
            if not arg:
                console.print(f"Current provider: [bold green]{self.provider_name}[/bold green]")
                console.print(f"Configured providers: {', '.join(self.config.providers.keys())}")
            else:
                try:
                    self.switch_provider(arg)
                except KeyError as e:
                    console.print(f"[bold red]Error:[/bold red] {e}")
            return True
        elif action == "/system":
            if not arg:
                current = self.session.system_prompt or "None"
                console.print(f"System prompt: [cyan]{current}[/cyan]")
            else:
                self.session.set_system_prompt(arg)
                console.print(f"[bold green]System prompt updated:[/bold green] {arg}")
            return True
        elif action == "/tokens":
            self.ui.print_tokens_stats(
                tokens=self.session.total_estimated_tokens(),
                limit=self.session.max_context_tokens,
                msg_count=len(self.session.messages),
            )
            return True
        elif action == "/save":
            if not arg:
                console.print("[yellow]Usage: /save <filepath>[/yellow]")
            else:
                out_path = Path(arg).expanduser()
                if out_path.suffix.lower() == ".json":
                    self.session.save_json(out_path)
                else:
                    self.session.save_markdown(out_path)
                console.print(f"[bold green]Session saved to {out_path}[/bold green]")
            return True
        elif action == "/load":
            if not arg:
                console.print("[yellow]Usage: /load <filepath.json>[/yellow]")
            else:
                in_path = Path(arg).expanduser()
                if not in_path.exists():
                    console.print(f"[bold red]File not found:[/bold red] {in_path}")
                else:
                    try:
                        self.session = SessionManager.load_json(in_path)
                        console.print(f"[bold green]Loaded {len(self.session.messages)} messages from {in_path}[/bold green]")
                    except Exception as e:
                        console.print(f"[bold red]Failed to load session:[/bold red] {e}")
            return True
        return False

    async def repl(self) -> None:
        self.ui.print_banner(self.provider_name, self.model, self.multiline_mode)
        # Prefetch model list for tab completion
        asyncio.create_task(self.update_cached_models())

        while True:
            prompt_session = create_prompt_session(
                history_file=HISTORY_FILE,
                get_models=self.get_known_models,
                get_providers=self.get_known_providers,
                multiline=self.multiline_mode,
            )

            prompt_label = "... > " if self.multiline_mode else "you > "

            try:
                user_input = await asyncio.to_thread(prompt_session.prompt, prompt_label)
                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.startswith("/"):
                    handled = await self.handle_slash_command(user_input)
                    if handled:
                        continue

                self.session.add_user_message(user_input)

                try:
                    stream_gen = self.provider.chat_stream(self.session.get_messages(), self.model)
                    response_text = await self.ui.stream_response(
                        stream_gen=stream_gen,
                        provider=self.provider_name,
                        model=self.model,
                    )
                    if response_text:
                        self.session.add_assistant_message(response_text)
                except Exception as e:
                    console.print(f"\n[bold red]API Error:[/bold red] {e}\n")

            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Exiting clichat...[/dim]")
                break

def parse_args():
    parser = argparse.ArgumentParser(description="CLI Chat with Local & Cloud LLMs")
    parser.add_argument("prompt", nargs="*", help="Direct prompt or piped query (or 'init' to initialize config)")
    parser.add_argument("-p", "--provider", help="Specify provider (e.g. ollama, openrouter, omlx, nvidia, gemini)")
    parser.add_argument("-m", "--model", help="Specify model name")
    parser.add_argument("-s", "--system", help="Set system prompt")
    parser.add_argument("-c", "--config", help="Custom config path")
    parser.add_argument("--init", action="store_true", help="Generate default configuration file")
    parser.add_argument("-f", "--force", action="store_true", help="Force overwrite existing config during init")
    return parser.parse_args()

async def async_main():
    args = parse_args()
    config_path = Path(args.config) if args.config else None

    # Handle 'clichat init' or 'clichat --init'
    is_init_cmd = args.init or (len(args.prompt) == 1 and args.prompt[0].lower() == "init")
    if is_init_cmd:
        try:
            target = init_config_file(config_path, force=args.force)
            console.print(f"[bold green]Configuration initialized successfully:[/bold green] {target}")
            console.print("[dim]You can now edit this file to configure API keys and default models.[/dim]")
            return
        except FileExistsError as e:
            console.print(f"[bold yellow]{e}[/bold yellow]")
            return
        except Exception as e:
            console.print(f"[bold red]Failed to create config:[/bold red] {e}")
            return

    config = load_config(config_path)

    app = CliApp(config, provider_name=args.provider, model_name=args.model)
    if args.system:
        app.session.set_system_prompt(args.system)

    piped_input = ""
    if not sys.stdin.isatty():
        piped_input = sys.stdin.read().strip()

    prompt_arg = " ".join(args.prompt).strip()

    if piped_input or prompt_arg:
        full_prompt = f"{piped_input}\n\n{prompt_arg}".strip() if piped_input and prompt_arg else (piped_input or prompt_arg)
        await app.run_single_prompt(full_prompt)
    else:
        await app.repl()

def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
