# Agent Guide for em_rag

This project is a local RAG system for embedded development documents. Use these rules when helping a user operate it from an AI agent or MCP client.

## Default Flow

For a new business project, prefer the conservative default flow:

1. Initialize the project with `python -m em_rag init` or the interactive `setup.sh` / `setup.bat` launcher.
2. Do not index by default. Let the user choose the document directory or file set.
3. When the user asks to build or refresh RAG, run `python -m em_rag add ./docs` or `python -m em_rag add <path>`.
4. Run `python -m em_rag doctor` after setup or rebuild.
5. Use `python -m em_rag list` to confirm indexed documents.

The true retrieval stores are `.em_rag/chroma_db` and `.em_rag/fts.db`.

## MCP Tool Use

When answering engineering questions in an MCP client:

- Call `list_docs` first if you do not know whether the project has indexed documents.
- Call `search_docs` before answering questions about chips, registers, datasheets, SDK APIs, source files, or board-specific behavior.
- Prefer focused technical queries, for example `STM32F103 SPI GPIO alternate function` or `AT24C02 write cycle time`.
- Use `doc_filter` only after `list_docs` shows the document ID and the user wants a specific document.
- Do not call `index_doc` unless the user explicitly asks to add, rebuild, refresh, or index documents.
- Do not call `remove_doc` unless the user explicitly asks to remove a document from the RAG index.

## Optional PDF Flows

Default PDF backend:

- `parsing.pdf_backend: "pymupdf"`
- Best for normal datasheets, reference manuals, Markdown/source mixed projects, and fast local indexing.
- Uses `.em_rag/figures` when `figures.enabled: true` to save likely timing diagram or waveform image assets.

MinerU backend:

- `parsing.pdf_backend: "mineru"`
- Best for scanned PDFs, complex layouts, and PDFs where PyMuPDF/pdfplumber extraction is poor.
- Requires MinerU to be installed and configured with `parsing.mineru_command`.
- Writes intermediate Markdown, images, and JSON under `.em_rag/mineru`.
- The index is still written to `.em_rag/chroma_db` and `.em_rag/fts.db`; queries do not normally read MinerU output directly.

If MinerU table OCR is too slow or unstable, use a safer text-oriented command:

```yaml
parsing:
  pdf_backend: "mineru"
  mineru_args: ["-b", "pipeline", "-m", "txt", "-l", "ch", "-f", "false", "-t", "false"]
```

This still uses MinerU for PDF-to-Markdown conversion, but disables formula and table parsing.

## Directory Meanings

- `.em_rag/config.yaml`: project-local RAG configuration.
- `.em_rag/chroma_db`: vector index used by retrieval.
- `.em_rag/fts.db`: SQLite full-text index used by retrieval.
- `.em_rag/mineru`: MinerU intermediate outputs, only relevant when using the MinerU PDF backend.
- `.em_rag/figures`: PyMuPDF figure assets, mainly timing diagrams and waveform pages.
- `.mcp.json`: project-local MCP client configuration.

## Migration and Repair

If a project was copied from another machine or absolute paths changed, run:

```bash
python -m em_rag repair
python -m em_rag doctor
```

`repair` resets portable model path settings and regenerates MCP configuration.

## Answering Style

When reporting RAG state to the user, include:

- whether `doctor` passed,
- current PDF backend,
- number of indexed documents,
- whether the answer came from indexed docs,
- any skipped or failed documents,
- important dependency conflicts if they affect indexing.

