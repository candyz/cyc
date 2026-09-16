from prompt_toolkit.document import Document
from clichat.ui import CommandCompleter, TerminalUI

def test_command_completer():
    completer = CommandCompleter(
        get_models=lambda: ["llama3.3:latest", "gemma4:cloud", "mistral:latest"],
        get_providers=lambda: ["ollama", "openrouter", "nvidia", "gemini"],
    )

    # Test command completion
    doc = Document("/mo")
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert "/models" in texts
    assert "/model" in texts

    # Test /model argument completion
    doc_model = Document("/model gem")
    completions_model = list(completer.get_completions(doc_model, None))
    assert len(completions_model) == 1
    assert completions_model[0].text == "gemma4:cloud"

    # Test /provider argument completion
    doc_prov = Document("/provider op")
    completions_prov = list(completer.get_completions(doc_prov, None))
    assert len(completions_prov) == 1
    assert completions_prov[0].text == "openrouter"

def test_terminal_ui_render():
    ui = TerminalUI(stream_markdown=True)
    # Ensure tables and banners format cleanly without exceptions
    ui.print_banner("ollama", "llama3.3", multiline=False)
    ui.print_models_table(["llama3.3", "qwen2.5"], current_model="llama3.3", provider="ollama")
    ui.print_tokens_stats(tokens=120, limit=8192, msg_count=4)
