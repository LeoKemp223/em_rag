import sys
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import mcp_server


def test_mcp_parse_args_accepts_config_and_project_root():
    args = mcp_server.parse_args([
        "--config",
        "/tmp/project/.em_rag/config.yaml",
        "--project-root",
        "/tmp/project",
    ])

    assert args.config == "/tmp/project/.em_rag/config.yaml"
    assert args.project_root == "/tmp/project"


def test_mcp_resolves_relative_doc_path_against_project_root(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    mcp_server.configure(
        str(project / ".em_rag" / "config.yaml"),
        str(project),
    )

    assert mcp_server._resolve_doc_path("docs/manual.pdf") == str(
        (project / "docs/manual.pdf").resolve()
    )


def test_mcp_tool_descriptions_include_agent_flow_hints():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.list_tools())}

    assert "回答芯片" in tools["search_docs"].description
    assert "应先调用" in tools["list_docs"].description
    assert "普通问答不要自动触发索引" in tools["index_doc"].description
    assert "只有在用户明确要求删除时" in tools["remove_doc"].description
