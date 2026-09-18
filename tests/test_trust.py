from pathlib import Path
import pytest
from cyc.agent.trust import WorkspaceTrustManager


def test_workspace_trust_manager_flow(tmp_path: Path):
    trust_file = tmp_path / "trusted_workspaces.json"
    mgr = WorkspaceTrustManager(storage_path=trust_file)

    project_dir = tmp_path / "my_project"
    sub_dir = project_dir / "src" / "deep"
    sub_dir.mkdir(parents=True)

    # Initial state: None
    assert mgr.get_trust_status(project_dir) is None
    assert mgr.get_trust_status(sub_dir) is None

    # Trust parent project_dir
    mgr.set_trust(project_dir, True)
    assert mgr.get_trust_status(project_dir) is True
    # Subdirectory inherits parent trust
    assert mgr.get_trust_status(sub_dir) is True

    # Check persistence
    mgr2 = WorkspaceTrustManager(storage_path=trust_file)
    assert mgr2.get_trust_status(sub_dir) is True

    # Restrict
    mgr.set_trust(project_dir, False)
    assert mgr.get_trust_status(project_dir) is False
    assert mgr.get_trust_status(sub_dir) is False


@pytest.mark.asyncio
async def test_ensure_workspace_trust_auto(tmp_path: Path):
    trust_file = tmp_path / "trusted_workspaces.json"
    mgr = WorkspaceTrustManager(storage_path=trust_file)
    proj = tmp_path / "auto_proj"
    proj.mkdir()

    # Explicit auto_trust flag
    status = await mgr.ensure_workspace_trust(proj, auto_trust=True)
    assert status is True
    assert mgr.get_trust_status(proj) is True

    status_deny = await mgr.ensure_workspace_trust(proj, auto_trust=False)
    assert status_deny is False
    assert mgr.get_trust_status(proj) is False
