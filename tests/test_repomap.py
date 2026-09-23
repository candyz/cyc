import pytest
from pathlib import Path
from cyc.agent.repomap import RepoMap
from cyc.agent.tools.repomap import RepoMapTool

def test_repo_map_python_parsing(tmp_path):
    py_code = """
class Calculator:
    def add(self, a, b):
        return a + b

    async def compute_async(self):
        pass

def helper_func():
    pass
"""
    (tmp_path / "calc.py").write_text(py_code, encoding="utf-8")
    mapper = RepoMap(root_dir=tmp_path)
    res = mapper.generate_map()

    assert "calc.py:" in res
    assert "class Calculator" in res
    assert "def add(...)" in res
    assert "def compute_async(...)" in res
    assert "def helper_func(...)" in res

def test_repo_map_polyglot_parsing(tmp_path):
    js_code = """
export function calculateTax(amount) {
    return amount * 0.05;
}
class InvoiceManager {
}
"""
    (tmp_path / "invoice.js").write_text(js_code, encoding="utf-8")

    go_code = """
package main

func ProcessOrder() {
}
type Order struct {}
"""
    (tmp_path / "order.go").write_text(go_code, encoding="utf-8")

    mapper = RepoMap(root_dir=tmp_path)
    res = mapper.generate_map()

    assert "invoice.js:" in res
    assert "calculateTax" in res
    assert "InvoiceManager" in res
    assert "order.go:" in res
    assert "ProcessOrder" in res

@pytest.mark.asyncio
async def test_repo_map_tool(tmp_path):
    (tmp_path / "test.py").write_text("def test_me(): pass\n", encoding="utf-8")
    tool = RepoMapTool()
    res = await tool.execute(path=str(tmp_path))
    assert "test.py:" in res
    assert "def test_me(...)" in res

@pytest.mark.asyncio
async def test_repo_map_tool_invalid_path():
    tool = RepoMapTool()
    res = await tool.execute(path="/non/existent/path/xyz")
    assert "does not exist" in res
