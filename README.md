# em_rag：嵌入式开发文档 RAG 系统

面向嵌入式开发者的轻量本地 RAG，基于标准 MCP 协议，可集成到任何支持 MCP 的 AI 编程工具（Claude Code、Cursor、Codex 等），让 AI 编程时能自动查阅芯片手册和 API 文档。

## 支持格式

| 格式 | 扩展名 | 典型用途 |
|------|--------|----------|
| PDF | .pdf | 芯片手册、参考手册、应用笔记 |
| Markdown | .md | SDK 文档、开发笔记 |
| 代码文件 | .h/.c/.s | 寄存器宏定义、HAL 库源码、BSP 驱动 |
| 纯文本 | .txt | 寄存器映射表、引脚定义 |
| 网页 | URL | 芯片厂商在线文档、技术博客 |
| Word | .docx | 硬件设计文档、接口协议说明 |
| 电子书 | .epub | 嵌入式教材、协议规范 |

## 架构

```
┌───────────────────────────────────────────────┐
│         AI IDE / Agent (MCP Client)           │
│                  ↕ MCP (stdio)                │
├───────────────────────────────────────────────┤
│           MCP RAG Server (Python)             │
│                                               │
│  ┌─────────┐    ┌───────────┐    ┌────────┐  │
│  │ search  │    │ Retriever │    │ index  │  │
│  │ (query) │ →  │ (向量+KW) │ ←  │ (add)  │  │
│  └─────────┘    └───────────┘    └────────┘  │
│                       ↕                       │
│  ┌────────────────────────────────────────┐   │
│  │     ChromaDB (向量) + SQLite (全文)    │   │
│  │  chunks + metadata + context_chain     │   │
│  └────────────────────────────────────────┘   │
├───────────────────────────────────────────────┤
│  Indexing Pipeline:                           │
│  Multi-format Parser → Element Classifier     │
│       → Chunker → ONNX Embedder → ChromaDB   │
└───────────────────────────────────────────────┘
```

## 项目结构

```
em_rag/
├── src/
│   ├── parsers/               # 多格式文档解析器
│   │   ├── __init__.py        # DocElement + create_parser 分发
│   │   ├── pdf_parser.py      # PDF（PyMuPDF + pdfplumber）
│   │   ├── markdown_parser.py # Markdown
│   │   ├── code_parser.py     # C/H/ASM 代码文件
│   │   ├── text_parser.py     # 纯文本
│   │   ├── web_parser.py      # 网页 URL
│   │   ├── docx_parser.py     # Word 文档
│   │   ├── epub_parser.py     # EPUB 电子书
│   │   └── utils.py           # 共享工具
│   ├── config.py              # 配置加载
│   ├── element_classifier.py  # 元素分类 + context_chain
│   ├── chunker.py             # 元素感知分块 + 语义边界检测
│   ├── embedder.py            # ONNX Embedding
│   ├── store.py               # ChromaDB + SQLite 双存储
│   ├── retriever.py           # 向量 + 关键词双路检索
│   ├── mcp_server.py          # MCP Server
│   └── cli.py                 # CLI 入口
├── em_rag/                    # python -m em_rag 公开入口
├── models/                    # ONNX 模型文件（gitignored）
├── scripts/
│   └── download_model.py      # 模型下载脚本
├── config.yaml
├── requirements.txt
├── docs/
│   └── technical_proposal.md  # 技术方案文档
└── data/
    ├── documents/             # 原始文档
    ├── chroma_db/             # 向量数据库
    └── fts.db                 # SQLite 全文索引
```

## 安装

```bash
pip install -r requirements.txt
python scripts/download_model.py
```

## 快速体验

```bash
python examples/demo.py
```

自带示例文档，无需额外文件，演示完整的 解析 → 分类 → 分块 → 向量化 → 存储 → 搜索 流程。

## 使用

```bash
# 索引各种格式的文档
python -m em_rag index ./path/to/datasheet.pdf
python -m em_rag index ./docs/sdk_guide.md
python -m em_rag index ./drivers/stm32f4xx.h
python -m em_rag index https://docs.vendor.com/chip-reference

# CLI 查询
python -m em_rag search "SPI_CR1 寄存器各位域含义"

# 列出已索引文档
python -m em_rag list

# 删除文档
python -m em_rag remove <doc_id>
```

## MCP 集成

em_rag 是标准的 MCP Server，兼容所有支持 MCP 协议的客户端。

### Claude Code

在项目根目录 `.mcp.json` 中配置：

```json
{
  "mcpServers": {
    "em-rag": {
      "command": "python3",
      "args": ["-m", "em_rag.mcp_server"],
      "cwd": "/path/to/em_rag"
    }
  }
}
```

### Cursor

在 Cursor Settings → MCP 中添加，配置同上。

### Codex / 其他 MCP 客户端

任何支持 stdio 传输的 MCP 客户端均可接入，启动命令：

```bash
python3 -m em_rag.mcp_server
```

提供的 MCP 工具：
- `search_docs` — 搜索已索引文档，支持寄存器名精确查询和语义查询
- `list_docs` — 列出所有已索引文档
- `index_doc` — 索引新文档
- `remove_doc` — 移除已索引文档

## 配置

编辑 `config.yaml` 调整参数：

```yaml
embedding:
  provider: "local"              # "local" | "openai"
  local_model: "all-MiniLM-L6-v2"

parsing:
  table_strategy: "pdfplumber"
  use_bookmarks: true

chunking:
  max_tokens: 1000
  keep_tables_intact: true

retrieval:
  top_k: 5
  keyword_priority: true         # 关键词命中优先
```

## 依赖

核心依赖（总计 ~80MB）：
- PyMuPDF — PDF 文本提取 + 书签
- pdfplumber — PDF 表格精确提取
- chromadb — 向量存储
- onnxruntime — ONNX 推理引擎（CPU）
- tokenizers — HuggingFace tokenizer
- huggingface_hub — 下载本地 embedding 模型
- mcp — MCP SDK

多格式支持：
- httpx — HTTP 请求（网页抓取）
- beautifulsoup4 + lxml — HTML 解析
- python-docx — Word 文档解析
- ebooklib — EPUB 电子书解析
