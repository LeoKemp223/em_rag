import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import default_model_dir, load_config


def test_load_config_resolves_project_paths_relative_to_config(tmp_path):
    project = tmp_path / "project"
    rag_dir = project / ".em_rag"
    rag_dir.mkdir(parents=True)
    config_path = rag_dir / "config.yaml"
    config_path.write_text(
        """
storage:
  chroma_path: "chroma_db"
  fts_path: "fts.db"
figures:
  output_dir: "figures"
documents:
  source_dir: "../docs"
""",
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config.storage.chroma_path == str((rag_dir / "chroma_db").resolve())
    assert config.storage.fts_path == str((rag_dir / "fts.db").resolve())
    assert config.figures.output_dir == str((rag_dir / "figures").resolve())
    assert config.documents.source_dir == str((rag_dir / "../docs").resolve())


def test_load_config_reads_utf8_yaml_comments(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
# 中文注释：Windows 默认 GBK 时也应该按 UTF-8 读取
storage:
  chroma_path: "chroma_db"
""",
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config.storage.chroma_path == str((tmp_path / "chroma_db").resolve())


def test_load_config_resolves_auto_model_dir_to_installation():
    config = load_config("__missing_config_for_test__.yaml")

    assert config.embedding.model_dir == str(default_model_dir())


def test_load_config_accepts_glm_embedding_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
embedding:
  provider: "glm"
  api_key_env: "ZHIPU_API_KEY"
  model: "embedding-3"
  dimensions: 1024
""",
        encoding="utf-8",
    )

    config = load_config(str(config_path))

    assert config.embedding.provider == "glm"
    assert config.embedding.api_key_env == "ZHIPU_API_KEY"
    assert config.embedding.model == "embedding-3"
    assert config.embedding.dimensions == 1024
