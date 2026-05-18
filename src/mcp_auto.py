"""Auto-configuring MCP server entrypoint."""

from __future__ import annotations

from pathlib import Path

from src import mcp_server


def repo_default_config() -> Path:
    return Path(__file__).resolve().parent.parent / "config.yaml"


def find_project_config(start: str | Path = None) -> tuple[Path, Path] | tuple[None, None]:
    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    for directory in [current, *current.parents]:
        config_path = directory / ".em_rag" / "config.yaml"
        if config_path.exists():
            return config_path, directory
    return None, None


async def main():
    config_path, project_root = find_project_config()
    if config_path and project_root:
        mcp_server.configure(str(config_path), str(project_root))
    else:
        mcp_server.configure(str(repo_default_config()), None)
    await mcp_server.main()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
