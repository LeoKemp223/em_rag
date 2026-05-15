"""MCP server entrypoint for ``python -m em_rag.mcp_server``."""

from src.mcp_server import main


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

