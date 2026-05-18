"""Auto-configuring MCP server entrypoint for ``python -m em_rag.mcp_auto``."""

from src.mcp_auto import main


def run():
    import asyncio

    asyncio.run(main())


if __name__ == "__main__":
    run()
