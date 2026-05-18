import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import cli


def test_expand_add_targets_recurses_supported_files(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "manual.pdf").write_text("pdf")
    (tmp_path / "docs" / "note.md").write_text("md")
    (tmp_path / "docs" / "ignore.bin").write_text("bin")
    (tmp_path / ".em_rag").mkdir()
    (tmp_path / ".em_rag" / "hidden.md").write_text("hidden")

    targets = cli._expand_add_targets(str(tmp_path))

    assert [p.name for p in targets] == ["manual.pdf", "note.md"]


def test_expand_add_targets_keeps_url_as_string():
    targets = cli._expand_add_targets("https://example.com/doc")

    assert targets == ["https://example.com/doc"]


def test_cmd_init_writes_project_files(tmp_path, capsys):
    class Args:
        project_root = str(tmp_path)
        force = False
        no_mcp = False

    cli.cmd_init(Args(), None)

    config_path = tmp_path / ".em_rag" / "config.yaml"
    mcp_path = tmp_path / ".mcp.json"
    assert config_path.exists()
    assert mcp_path.exists()
    assert "model_dir:" in config_path.read_text(encoding="utf-8")

    mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    server = mcp["mcpServers"]["em-rag"]
    assert server["command"] == sys.executable
    assert server["args"] == ["-m", "em_rag.mcp_auto"]
    assert server["cwd"] == str(tmp_path.resolve())
    assert 'model_dir: "auto"' in config_path.read_text(encoding="utf-8")

    output = capsys.readouterr().out
    assert "初始化完成" in output


def test_cmd_mcp_writes_project_mcp_json(tmp_path):
    rag_dir = tmp_path / ".em_rag"
    rag_dir.mkdir()
    config_path = rag_dir / "config.yaml"
    config_path.write_text("storage:\n  chroma_path: chroma_db\n", encoding="utf-8")

    class Args:
        project_root = str(tmp_path)
        config = "config.yaml"
        force = True

    cli.cmd_mcp(Args(), None)

    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp["mcpServers"]["em-rag"]
    assert server["command"] == sys.executable
    assert server["args"] == ["-m", "em_rag.mcp_auto"]
    assert server["cwd"] == str(tmp_path.resolve())


def test_cmd_repair_makes_project_config_portable(tmp_path):
    rag_dir = tmp_path / ".em_rag"
    rag_dir.mkdir()
    config_path = rag_dir / "config.yaml"
    config_path.write_text(
        """
embedding:
  provider: "local"
  local_model: "all-MiniLM-L6-v2"
  model_dir: "/old/machine/em_rag/models"
storage:
  chroma_path: "chroma_db"
""",
        encoding="utf-8",
    )

    class Args:
        project_root = str(tmp_path)
        no_mcp = False

    cli.cmd_repair(Args(), None)

    assert 'model_dir: "auto"' in config_path.read_text(encoding="utf-8")
    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["em-rag"]["args"] == ["-m", "em_rag.mcp_auto"]


def test_cmd_add_calls_index_path_for_each_target(tmp_path, monkeypatch, capsys):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("a")
    (docs / "b.md").write_text("b")
    calls = []

    def fake_index_path(path, config):
        calls.append(Path(path).name)
        return Path(path).stem, 1

    monkeypatch.setattr(cli, "index_path", fake_index_path)

    class Args:
        path = str(docs)

    cli.cmd_add(Args(), object())

    assert calls == ["a.md", "b.md"]
    assert "成功 2, 失败 0" in capsys.readouterr().out


def test_index_path_skips_empty_chunks(tmp_path, monkeypatch, capsys):
    doc = tmp_path / "empty.md"
    doc.write_text("")

    class EmptyParser:
        def parse(self, path):
            return []

    class EmptyClassifier:
        def classify(self, elements):
            return elements

    class EmptyChunker:
        def __init__(self, config):
            pass

        def chunk(self, elements):
            return []

    def fail_create_embedder(config):
        raise AssertionError("embedding should not run for empty chunks")

    monkeypatch.setattr("src.parsers.create_parser", lambda path, figures: EmptyParser())
    monkeypatch.setattr("src.element_classifier.ElementClassifier", EmptyClassifier)
    monkeypatch.setattr("src.chunker.Chunker", EmptyChunker)
    monkeypatch.setattr("src.embedder.create_embedder", fail_create_embedder)

    class Config:
        figures = object()
        chunking = object()

    doc_id, chunks = cli.index_path(str(doc), Config())

    assert doc_id == "empty"
    assert chunks == 0
    assert "跳过: 未生成可索引内容" in capsys.readouterr().out
