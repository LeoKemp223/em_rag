"""MCP server entrypoint for ``python -m em_rag.mcp_server``."""

from src.mcp_server import configure, main, parse_args


def run():
    import asyncio

    args = parse_args()
    configure(args.config, args.project_root)
    asyncio.run(main())


if __name__ == "__main__":
    run()
