# Page and Figure RAG Design

## Goal

Improve two weak paths in the current RAG pipeline:

- Queries that fail to recall the correct PDF chapter or page.
- Timing diagram and waveform queries where the relevant knowledge is inside or around an image.

## Approach

Keep the existing ChromaDB plus SQLite FTS architecture, but make page and figure context first-class retrieval material.

Indexing will create normal text/table chunks as before, plus figure chunks whose content contains a searchable figure summary. A figure summary is built from caption, page number, context chain, detected signals, detection reason, and image path. This makes image assets discoverable by text queries before any heavier multimodal model is introduced.

Retrieval will still run vector and FTS search, but it will expand each hit with nearby page/section context. When a result is a figure, or has related images, the returned content includes image metadata and figure summary so the MCP client has enough material to decide whether to inspect the original image.

## Data Flow

```text
PDF
  -> text/table/figure elements
  -> element-aware chunks
  -> figure chunks with searchable summaries
  -> ChromaDB + SQLite FTS metadata

query
  -> keyword extraction
  -> vector search + FTS search
  -> merge
  -> page/section expansion
  -> return text, page, context chain, related images
```

## Scope

This first implementation avoids new heavy dependencies. OCR and VLM summaries can be added later behind configuration flags. The immediate target is a testable improvement that returns the correct page and image path for timing-related PDF queries.

