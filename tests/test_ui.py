from prompt_toolkit.document import Document
from cyc.ui import CommandCompleter, TerminalUI

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

    # Test /mode argument completion
    doc_mode = Document("/mode ")
    completions_mode = list(completer.get_completions(doc_mode, None))
    assert [c.text for c in completions_mode] == ["chat", "agent"]

    doc_mode_ag = Document("/mode ag")
    completions_mode_ag = list(completer.get_completions(doc_mode_ag, None))
    assert len(completions_mode_ag) == 1
    assert completions_mode_ag[0].text == "agent"

    # Test /sessions completion
    doc_sessions = Document("/sessions ")
    completions_sessions = list(completer.get_completions(doc_sessions, None))
    expected_options = ["all", "cyc", "agy", "claude", "pi", "opencode", "manage", "delete", "rm", "prune", "clean", "rename"]
    assert [c.text for c in completions_sessions] == expected_options

    doc_sessions_pi = Document("/sessions p")
    completions_sessions_pi = list(completer.get_completions(doc_sessions_pi, None))
    assert [c.text for c in completions_sessions_pi] == ["pi", "prune"]

    # Test /resume completion
    def fake_get_sessions(agent=None):
        data = {
            "cyc": ["LATEST", "20260917-103000-abcd"],
            "agy": ["agy_conv-1234"],
            "claude": ["claude_proj-5678"],
            "pi": ["pi_sess-9999"],
            "opencode": ["ses_oc-1111"],
        }
        if agent and agent in data:
            return data[agent]
        all_s = []
        for s_list in data.values():
            all_s.extend(s_list)
        return all_s

    completer_with_sessions = CommandCompleter(
        get_models=lambda: [],
        get_providers=lambda: [],
        get_sessions=fake_get_sessions,
    )

    # 1. /resume [space] offers agent names + all session IDs
    doc_resume = Document("/resume ")
    completions_resume = [c.text for c in completer_with_sessions.get_completions(doc_resume, None)]
    assert "agy" in completions_resume
    assert "claude" in completions_resume
    assert "pi" in completions_resume
    assert "opencode" in completions_resume
    assert "cyc" in completions_resume
    assert "LATEST" in completions_resume

    # 2. /resume agy [space] offers only agy sessions
    doc_resume_agy = Document("/resume agy ")
    completions_resume_agy = [c.text for c in completer_with_sessions.get_completions(doc_resume_agy, None)]
    assert completions_resume_agy == ["agy_conv-1234"]

    # 3. /resume opencode [space] offers only opencode sessions
    doc_resume_oc = Document("/resume opencode ")
    completions_resume_oc = [c.text for c in completer_with_sessions.get_completions(doc_resume_oc, None)]
    assert completions_resume_oc == ["ses_oc-1111"]

def test_terminal_ui_render():
    ui = TerminalUI(stream_markdown=True)
    # Ensure tables and banners format cleanly without exceptions
    ui.print_banner("ollama", "llama3.3", multiline=False)
    ui.print_models_table(["llama3.3", "qwen2.5"], current_model="llama3.3", provider="ollama")
    ui.print_tokens_stats(tokens=120, limit=8192, msg_count=4)

    # Test thinking / CoT block formatting
    sample_cot_resp = "<think>\nLet's analyze the codebase and consider options.\n</think>\nHere is the answer."
    ui.render_formatted_response(sample_cot_resp)
    # Plain text without think
    ui.render_formatted_response("Standard answer without thinking tags.")


import pytest

@pytest.mark.asyncio
async def test_terminal_ui_stream_response():
    ui = TerminalUI(stream_markdown=True)

    async def fake_stream():
        yield "Hello "
        yield "World!"

    output = await ui.stream_response(fake_stream(), provider="test-prov", model="test-mod")
    assert output == "Hello World!"

    # Test stream_response with <think> tags
    async def fake_think_stream():
        yield "<think>\nAnalyzing weather data...\n"
        yield "</think>\nTD29 has formed into a tropical depression."

    think_output = await ui.stream_response(fake_think_stream(), provider="test-prov", model="test-mod")
    assert "<think>" in think_output
    assert "TD29" in think_output


def test_terminal_ui_render_resumed_history():
    ui = TerminalUI(stream_markdown=True)
    # Empty messages should not raise
    ui.render_resumed_history([])

    sample_messages = [
        {"role": "user", "content": "Can you check the files?"},
        {
            "role": "assistant",
            "content": "I will inspect the workspace.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "list_dir", "arguments": '{"path": "."}'},
                }
            ],
        },
        {"role": "tool", "name": "list_dir", "content": "file1.txt\nfile2.py\nfile3.md"},
        {"role": "assistant", "content": "I found 3 files in your repository."},
    ]
    ui.render_resumed_history(sample_messages)

    # Test with more than max_messages to check truncation / slice indicator
    many_messages = sample_messages * 4
    ui.render_resumed_history(many_messages, max_messages=5)


def test_create_prompt_session_docked():
    from cyc.ui import create_prompt_session
    from prompt_toolkit.layout.containers import HSplit

    # 1. Non-docked (standard PromptSession layout has default toolbars and controls)
    session_classic = create_prompt_session(docked=False)
    assert len(session_classic.app.layout.container.children) > 2

    # 2. Docked (wrapped with [top_filler, inner_container])
    session_docked = create_prompt_session(docked=True)
    assert isinstance(session_docked.app.layout.container, HSplit)
    # The top container of HSplit should have exactly 2 children: top filler and original container
    assert len(session_docked.app.layout.container.children) == 2



