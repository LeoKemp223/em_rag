# Claude Guide

Read `AGENTS.md` first. It is the canonical agent workflow for this repository.

Key rules:

- For normal engineering questions, inspect the current RAG state with `list_docs` when needed, then use `search_docs` before answering.
- Do not call `index_doc` unless the user explicitly asks to add, rebuild, refresh, or index documents.
- Do not call `remove_doc` unless the user explicitly asks to delete a document from the RAG index.
- For PDF indexing, default to `pymupdf`; use MinerU only when the user asks for stronger PDF parsing or the PDF quality requires it.
- Treat `.em_rag/chroma_db` and `.em_rag/fts.db` as the retrieval stores. `.em_rag/mineru` and `.em_rag/figures` are generated assets, not the primary query path.

