import os
import pytest
from pathlib import Path

@pytest.fixture(autouse=True)
def isolate_cyc_sessions(tmp_path: Path, monkeypatch):
    """Automatically isolate all test sessions into a dedicated tmp_path directory.
    Prevents test sessions from polluting the user's ~/.local/share/cyc/sessions directory.
    """
    test_sessions_dir = tmp_path / "test_sessions"
    test_sessions_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CYC_SESSIONS_DIR", str(test_sessions_dir))
    return test_sessions_dir
