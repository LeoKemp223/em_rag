import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp_auto import find_project_config, repo_default_config


def test_find_project_config_walks_up_from_nested_directory(tmp_path):
    project = tmp_path / "project"
    nested = project / "src" / "drivers"
    rag_dir = project / ".em_rag"
    nested.mkdir(parents=True)
    rag_dir.mkdir()
    config = rag_dir / "config.yaml"
    config.write_text("storage:\n  chroma_path: chroma_db\n", encoding="utf-8")

    found_config, found_root = find_project_config(nested)

    assert found_config == config
    assert found_root == project


def test_find_project_config_returns_none_when_missing(tmp_path):
    found_config, found_root = find_project_config(tmp_path)

    assert found_config is None
    assert found_root is None


def test_repo_default_config_points_to_repo_config():
    assert repo_default_config().name == "config.yaml"
    assert repo_default_config().exists()
