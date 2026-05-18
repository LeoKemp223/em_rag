"""Auto-configuring MCP server entrypoint for ``python -m em_rag.mcp_auto``."""

from src.mcp_auto import main


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
