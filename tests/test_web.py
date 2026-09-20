import asyncio
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from cyc.config import Config, DEFAULT_CONFIG_DICT
from cyc.web.app import create_app


@pytest.fixture
def web_test_client(tmp_path):
    config = Config(**DEFAULT_CONFIG_DICT)
    config.web.auth_token = "secret123"
    app = create_app(config=config, auth_token="secret123", workspace_path=tmp_path)
    return TestClient(app)


def test_web_auth_failure(web_test_client):
    res = web_test_client.get("/api/status")
    assert res.status_code == 401


def test_web_favicon(web_test_client):
    res = web_test_client.get("/favicon.ico")
    assert res.status_code == 200
    assert "image/x-icon" in res.headers.get("content-type", "")
    assert len(res.content) > 0

    res_static = web_test_client.get("/static/favicon.png")
    assert res_static.status_code == 200
    assert "image/png" in res_static.headers.get("content-type", "")



def test_web_auth_success_with_query_token(web_test_client):
    res = web_test_client.get("/api/status?token=secret123")
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert "workspace" in data
    assert "providers" in data


def test_web_auth_success_with_header(web_test_client):
    res = web_test_client.get("/api/status", headers={"Authorization": "Bearer secret123"})
    assert res.status_code == 200
    data = res.json()
    assert "version" in data


def test_web_providers_and_models(web_test_client):
    res = web_test_client.get("/api/providers", headers={"Authorization": "Bearer secret123"})
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert len(data["providers"]) > 0


def test_web_sessions_list_and_create(web_test_client):
    # List sessions
    res = web_test_client.get("/api/sessions", headers={"Authorization": "Bearer secret123"})
    assert res.status_code == 200
    assert "sessions" in res.json()

    # Create session
    create_res = web_test_client.post(
        "/api/sessions",
        headers={"Authorization": "Bearer secret123"},
        json={"mode": "agent"},
    )
    assert create_res.status_code == 200
    created = create_res.json()
    assert "session_id" in created

    # Get single session
    sess_id = created["session_id"]
    get_res = web_test_client.get(f"/api/sessions/{sess_id}", headers={"Authorization": "Bearer secret123"})
    assert get_res.status_code == 200
    assert get_res.json()["session_id"] == sess_id


def test_web_file_browsing(web_test_client, tmp_path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("print('hello cyc web')", encoding="utf-8")

    # List directory
    res = web_test_client.get("/api/files", headers={"Authorization": "Bearer secret123"})
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "directory"
    names = [item["name"] for item in data["items"]]
    assert "sample.py" in names

    # Read file
    res_file = web_test_client.get("/api/files?path=sample.py", headers={"Authorization": "Bearer secret123"})
    assert res_file.status_code == 200
    file_data = res_file.json()
    assert file_data["type"] == "file"
    assert "hello cyc web" in file_data["content"]


def test_web_index_html_serving(web_test_client):
    res = web_test_client.get("/")
    assert res.status_code == 200
    assert "cyc" in res.text
    assert "Web Terminal" in res.text


def test_web_terminal_websocket(web_test_client):
    with web_test_client.websocket_connect("/ws/terminal?token=secret123") as ws:
        ws.send_text("echo test_term\n")
        # Receive output from PTY
        output = ""
        for _ in range(5):
            chunk = ws.receive_text()
            output += chunk
            if "test_term" in output:
                break
        assert "test_term" in output


def test_web_mcp_servers(web_test_client):
    res = web_test_client.get("/api/mcp", headers={"Authorization": "Bearer secret123"})
    assert res.status_code == 200
    data = res.json()
    assert "mcp_servers" in data
    assert "total" in data


def test_web_compact_session(web_test_client):
    # 1. Create session
    create_res = web_test_client.post(
        "/api/sessions",
        headers={"Authorization": "Bearer secret123"},
        json={"mode": "agent"},
    )
    sess_id = create_res.json()["session_id"]

    # 2. Compact session
    compact_res = web_test_client.post(
        f"/api/sessions/{sess_id}/compact?ratio=0.50",
        headers={"Authorization": "Bearer secret123"},
    )
    assert compact_res.status_code == 200
    data = compact_res.json()
    assert data["status"] == "compacted"
    assert "result" in data
def test_web_agent_websocket_approval(web_test_client):
    with web_test_client.websocket_connect("/ws/agent?token=secret123") as ws:
        ws.send_json({
            "action": "query",
            "prompt": "hi",
            "auto_approve": False,
            "strategy": "minimal",
            "max_turns": 10,
        })
        first_event = ws.receive_json()
        assert "type" in first_event
        ws.send_json({"action": "cancel"})


def test_web_sse_streaming(web_test_client):
    res = web_test_client.post(
        "/api/events/sse?token=secret123",
        json={
            "prompt": "hello",
            "strategy": "minimal",
            "max_turns": 5,
        },
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_run_web_server_startup(tmp_path):
    from cyc.web.server import run_web_server
    import asyncio
    config = Config(**DEFAULT_CONFIG_DICT)
    config.web.port = 18889

    # Start run_web_server as task and stop quickly
    task = asyncio.create_task(
        run_web_server(
            config=config,
            host="127.0.0.1",
            port=18889,
            auth_token="test_token",
            open_browser=False,
            workspace_path=tmp_path,
        )
    )
    # Wait briefly for server to bind
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass




