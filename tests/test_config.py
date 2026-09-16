import os
from pathlib import Path
import pytest
from clichat.config import expand_env_vars, init_config_file, load_config

def test_expand_env_vars(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "secret_123")
    monkeypatch.setenv("ANOTHER_KEY", "abc")

    data = {
        "url": "https://api.example.com",
        "key1": "${TEST_KEY}",
        "key2": "Bearer $ANOTHER_KEY",
        "nested": {
            "token": "${TEST_KEY}",
        },
        "list": ["${TEST_KEY}", 123]
    }

    expanded = expand_env_vars(data)
    assert expanded["key1"] == "secret_123"
    assert expanded["key2"] == "Bearer abc"
    assert expanded["nested"]["token"] == "secret_123"
    assert expanded["list"][0] == "secret_123"
    assert expanded["list"][1] == 123

def test_load_default_config():
    config = load_config(Path("/nonexistent/path/config.yaml"))
    assert config.default_provider == "ollama"
    assert "ollama" in config.providers
    assert "openrouter" in config.providers
    assert "agy" in config.providers
    assert config.get_provider("ollama").base_url == "http://localhost:11434/v1"
    assert config.get_provider("omlx").base_url == "http://localhost:8000/v1"

def test_init_config_file(tmp_path: Path):
    target = tmp_path / "subdir" / "config.yaml"
    res = init_config_file(target)
    assert res == target
    assert target.exists()

    content = target.read_text(encoding="utf-8")
    assert "ollama" in content
    assert "gemini" in content
    assert "openrouter" in content
    assert "agy" in content

    # Should raise error if already exists and force is False
    with pytest.raises(FileExistsError):
        init_config_file(target, force=False)

    # Should succeed if force is True
    init_config_file(target, force=True)
    assert target.exists()
