"""Interactive bootstrap for new projects."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BootstrapContext:
    repo_root: Path
    python_exe: Path
    venv_dir: Path
    venv_python: Path
    project_root: Path
    config_path: Path
    mcp_path: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_project_root(start: str | Path | None = None) -> Path:
    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    return current


def find_python() -> Path:
    env_python = os.environ.get("EM_RAG_PYTHON")
    if env_python:
        candidate = Path(env_python)
        if _python_meets_requirement(candidate):
            return candidate
        raise RuntimeError(f"指定的 Python 不满足 3.11+: {candidate}")
    if sys.version_info < (3, 11):
        raise RuntimeError("当前 Python 版本低于 3.11")
    return Path(sys.executable)


def _python_meets_requirement(python_exe: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    version = result.stdout.strip()
    try:
        major, minor = (int(part) for part in version.split("."))
    except ValueError:
        return False
    return (major, minor) >= (3, 11)


def ensure_venv(context: BootstrapContext, prompt) -> None:
    if context.venv_python.exists():
        return
    if not prompt("未找到虚拟环境，是否创建 .venv？", default=True):
        raise RuntimeError("用户取消创建虚拟环境")
    subprocess.run(
        [str(context.python_exe), "-m", "venv", str(context.venv_dir)],
        check=True,
    )


def install_dependencies(context: BootstrapContext, prompt) -> None:
    if not prompt("是否安装依赖并注册当前项目？", default=True):
        return
    subprocess.run(
        [str(context.venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=str(context.repo_root),
        check=True,
    )
    subprocess.run(
        [str(context.venv_python), "-m", "pip", "install", "-e", "."],
        cwd=str(context.repo_root),
        check=True,
    )


def write_project_config(context: BootstrapContext, prompt, force: bool = False) -> bool:
    config_path = context.config_path
    if config_path.exists() and not force:
        if not prompt(f"已存在 {config_path}，是否覆盖？", default=False):
            return False
    config_path.parent.mkdir(parents=True, exist_ok=True)
    from src.cli import _project_config_template

    config_path.write_text(_project_config_template(), encoding="utf-8")
    return True


def write_mcp_config(context: BootstrapContext, prompt, force: bool = False) -> bool:
    mcp_path = context.mcp_path
    if mcp_path.exists() and not force:
        if not prompt(f"已存在 {mcp_path}，是否覆盖？", default=False):
            return False
    from src.cli import _mcp_config_template

    mcp_path.write_text(
        _mcp_config_template(context.project_root, context.config_path),
        encoding="utf-8",
    )
    return True


def run_doctor(context: BootstrapContext) -> None:
    subprocess.run(
        [str(context.venv_python), "-m", "em_rag", "doctor"],
        cwd=str(context.project_root),
        check=False,
    )


def prompt_bool(message: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{message} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "是", "好", "确认"}


def bootstrap(project_root: str | Path | None = None) -> int:
    repo = repo_root()
    root = default_project_root(project_root)
    python_exe = find_python()
    venv_dir = root / ".venv"
    venv_python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    context = BootstrapContext(
        repo_root=repo,
        python_exe=python_exe,
        venv_dir=venv_dir,
        venv_python=venv_python,
        project_root=root,
        config_path=root / ".em_rag" / "config.yaml",
        mcp_path=root / ".mcp.json",
    )

    print("em_rag 中文启动向导")
    print(f"项目根目录: {context.project_root}")
    print(f"Python: {context.python_exe}")

    ensure_venv(context, prompt_bool)
    install_dependencies(context, prompt_bool)

    if prompt_bool("是否初始化项目配置（.em_rag/config.yaml）？", default=True):
        write_project_config(context, prompt_bool)

    if prompt_bool("是否生成 MCP 配置（.mcp.json）？", default=True):
        write_mcp_config(context, prompt_bool)

    if prompt_bool("是否运行健康检查 doctor？", default=True):
        run_doctor(context)

    print("完成。后续如需索引文档，可运行: python -m em_rag add ./docs")
    return 0


def main() -> int:
    try:
        return bootstrap()
    except Exception as exc:
        print(f"启动失败: {type(exc).__name__}: {exc}")
        return 1
