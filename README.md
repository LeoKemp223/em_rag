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

PDF 索引会额外保存疑似时序图相关页面的图片资产：默认保存整页截图，并在可识别嵌入图片块时额外保存裁剪图，检索结果会返回关联图片路径供后续 LLM/VLM 使用。

如果优先考虑准确率，可将 `figures.detection` 设为 `hybrid` 或 `llm`。`hybrid` 会先用宽松规则召回候选页，再让 LLM 判断是否确实与时序图/波形/开关特性有关；`llm` 会逐页判断，召回更充分但成本更高。

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
pip install -e .
python scripts/download_model.py
```

## 快速体验

```bash
python examples/demo.py
```

自带示例文档，无需额外文件，演示完整的 解析 → 分类 → 分块 → 向量化 → 存储 → 搜索 流程。

## 使用

### 小白快速接入工程

在业务工程目录执行：

```bash
/home/leo/work/open-git/em_rag/.venv/bin/python -m em_rag init
/home/leo/work/open-git/em_rag/.venv/bin/python -m em_rag add ./docs
/home/leo/work/open-git/em_rag/.venv/bin/python -m em_rag doctor
```

这会自动生成：

```text
your-project/
├── .em_rag/
│   ├── config.yaml
│   └── .gitignore
└── .mcp.json
```

然后重启支持 MCP 的 LLM 客户端即可。`add` 可以接收单个文件、URL 或目录；
传目录时会递归索引支持的文档格式。

如果需要覆盖已存在配置：

```bash
python -m em_rag init --force
```

如果只需要重新生成 MCP 配置：

```bash
python -m em_rag mcp --force
```

### 常用命令

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

# 递归索引目录
python -m em_rag add ./docs

# 生成或更新 .mcp.json
python -m em_rag mcp --force

# 检查当前工程 RAG 环境
python -m em_rag doctor
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

### 多工程隔离

如果多个业务工程使用不同文档，建议每个工程维护自己的 `.em_rag/config.yaml`
和索引库，`em_rag` 程序和模型只保留一份。

业务工程结构示例：

```text
your-project/
├── .em_rag/
│   ├── config.yaml
│   ├── chroma_db/
│   ├── fts.db
│   └── figures/
├── docs/
└── .mcp.json
```

`.em_rag/config.yaml` 示例：

```yaml
embedding:
  provider: "local"
  local_model: "all-MiniLM-L6-v2"
  model_dir: "/home/leo/work/open-git/em_rag/models"

storage:
  chroma_path: "chroma_db"
  fts_path: "fts.db"

figures:
  enabled: true
  output_dir: "figures"

retrieval:
  top_k: 5
  keyword_priority: true
  context_expand: true
```

`storage.*`、`figures.output_dir` 和 `documents.source_dir` 的相对路径会按
配置文件所在目录解析。上例会写入 `your-project/.em_rag/chroma_db`、
`your-project/.em_rag/fts.db` 和 `your-project/.em_rag/figures`。

业务工程 `.mcp.json` 示例：

```json
{
  "mcpServers": {
    "em-rag": {
      "command": "/home/leo/work/open-git/em_rag/.venv/bin/python",
      "args": [
        "-m",
        "em_rag.mcp_server",
        "--config",
        "/path/to/your-project/.em_rag/config.yaml",
        "--project-root",
        "/path/to/your-project"
      ],
      "cwd": "/home/leo/work/open-git/em_rag"
    }
  }
}
```

`cwd` 建议保持为 `em_rag` 仓库目录；`--project-root` 用于让 MCP 工具
`index_doc` 的相对路径按业务工程解析。

### Codex 全局自动识别工程

如果 Codex 使用全局 `~/.codex/config.toml`，建议只配置一次自动入口：

```toml
[mcp_servers.em-rag]
command = "/home/leo/work/open-git/em_rag/.venv/bin/python"
args = ["-m", "em_rag.mcp_auto"]
```

`mcp_auto` 会从当前工作目录向上查找 `.em_rag/config.yaml`：

- 找到后使用该配置，并把所在目录作为 `project-root`
- 找不到则回退到 `em_rag` 仓库默认 `config.yaml`

这样新工程只需要运行：

```bash
python -m em_rag init
python -m em_rag add ./docs
```

全局 Codex MCP 配置不用再改路径。

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

figures:
  enabled: true                  # 保存疑似时序图图片资产
  mode: "timing_related"         # "timing_related" | "all"
  detection: "heuristic"         # "heuristic" | "hybrid" | "llm"
  save_full_page: true           # 渲染整页，兜底矢量时序图
  save_crops: true               # 尝试保存可识别图片块裁剪
  render_dpi: 180
  output_dir: "./data/figures"
  llm_provider: "openai"
  llm_model: "gpt-4.1"          # 准确率优先；可改为更便宜的 mini 模型
  # llm_api_key: ""              # 留空时读取 OPENAI_API_KEY
  # llm_base_url: ""             # OpenAI-compatible endpoint，可选
  min_confidence: 0.65
  candidate_context_chars: 6000

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
