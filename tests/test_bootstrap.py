import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import bootstrap


def test_bootstrap_writes_project_files_and_runs_doctor(tmp_path, monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(bootstrap, "find_python", lambda: tmp_path / "python")
    monkeypatch.setattr(bootstrap, "ensure_venv", lambda ctx, prompt: calls.append("venv"))
    monkeypatch.setattr(bootstrap, "install_dependencies", lambda ctx, prompt: calls.append("deps"))
    monkeypatch.setattr(bootstrap, "run_doctor", lambda ctx: calls.append("doctor"))
    monkeypatch.setattr(bootstrap, "prompt_bool", lambda *args, **kwargs: True)

    bootstrap.bootstrap(tmp_path)

    assert calls == ["venv", "deps", "doctor"]
    config_path = tmp_path / ".em_rag" / "config.yaml"
    mcp_path = tmp_path / ".mcp.json"
    assert config_path.exists()
    assert mcp_path.exists()
    mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["em-rag"]["args"] == ["-m", "em_rag.mcp_auto"]
    output = capsys.readouterr().out
    assert "中文启动向导" in output


def test_write_project_config_respects_overwrite_prompt(tmp_path, monkeypatch):
    context = bootstrap.BootstrapContext(
        repo_root=tmp_path,
        python_exe=tmp_path / "python",
        venv_dir=tmp_path / ".venv",
        venv_python=tmp_path / ".venv" / "bin" / "python",
        project_root=tmp_path,
        config_path=tmp_path / ".em_rag" / "config.yaml",
        mcp_path=tmp_path / ".mcp.json",
    )
    context.config_path.parent.mkdir(parents=True, exist_ok=True)
    context.config_path.write_text("old: true\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "prompt_bool", lambda *args, **kwargs: False)

    changed = bootstrap.write_project_config(context, bootstrap.prompt_bool)

    assert changed is False
    assert context.config_path.read_text(encoding="utf-8") == "old: true\n"


def test_write_mcp_config_uses_existing_template(tmp_path, monkeypatch):
    context = bootstrap.BootstrapContext(
        repo_root=tmp_path,
        python_exe=tmp_path / "python",
        venv_dir=tmp_path / ".venv",
        venv_python=tmp_path / ".venv" / "bin" / "python",
        project_root=tmp_path,
        config_path=tmp_path / ".em_rag" / "config.yaml",
        mcp_path=tmp_path / ".mcp.json",
    )
    context.config_path.parent.mkdir(parents=True, exist_ok=True)
    context.config_path.write_text("storage:\n  chroma_path: chroma_db\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "prompt_bool", lambda *args, **kwargs: True)

    changed = bootstrap.write_mcp_config(context, bootstrap.prompt_bool, force=True)

    assert changed is True
    payload = json.loads(context.mcp_path.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["em-rag"]["cwd"] == str(tmp_path.resolve())
