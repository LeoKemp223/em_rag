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

必须使用 Python 3.11 或更高版本。不要用系统自带的旧版 `python`
（例如 Python 3.8）创建虚拟环境，否则启动时会因为类型语法和依赖兼容性报错。

新项目推荐直接运行中文交互式启动脚本：

Linux / macOS:

```bash
./setup.sh
```

Windows:

```bat
setup.bat
```

启动脚本会引导完成虚拟环境、依赖安装、项目配置和 MCP 配置生成。默认不会索引文档；
完成后按提示再运行 `python -m em_rag add ./docs`。

建议先确认版本：

```bash
python3.11 --version
```

Linux / macOS:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
python scripts/download_model.py
```

如果你的系统里 Python 3.11 命令名就是 `python`，也可以使用
`python -m venv .venv`；关键是创建虚拟环境的解释器必须是 Python 3.11+。

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python scripts\download_model.py
```

不要直接用 Anaconda base 环境或系统旧版 Python 执行 `pip install`。
如果 `pip` 路径指向 Anaconda 或 Python 3.8，先按上面命令创建并激活
Python 3.11 虚拟环境，再使用 `python -m pip ...` 安装。

Windows 如果提示脚本执行策略限制，可先在当前 PowerShell 会话执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Windows 平台支持核心功能，包括 CLI、MCP stdio、Chroma 持久化、
SQLite FTS、ONNX embedding，以及 Markdown / 文本 / 代码 / DOCX /
EPUB 解析。PDF 解析依赖 `PyMuPDF` 和 `pdfplumber`，请使用 64-bit
Python 3.11+，通常可直接安装 wheel。

配置文件按 UTF-8 读取，可以包含中文注释；建议编辑器保存为 UTF-8。
`requirements.txt` 保持 ASCII 注释，避免旧版 Windows `pip` 按 GBK 解码时报错。

安装后检查环境：

```bash
python -m em_rag doctor
```

如果没有激活虚拟环境，也可以显式调用虚拟环境里的 Python：

```bash
./.venv/bin/python -m em_rag doctor
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m em_rag doctor
```

## 快速体验

```bash
python examples/demo.py
```

自带示例文档，无需额外文件，演示完整的 解析 → 分类 → 分块 → 向量化 → 存储 → 搜索 流程。

## 可选流程怎么选

默认流程只做本地轻量索引和 MCP 配置，适合大多数新工程先跑起来。下面这些能力需要按场景主动打开：

| 场景 | 推荐流程 | 需要改什么 |
|------|----------|------------|
| 新工程先接入 AI 客户端 | 运行 `setup.sh` / `setup.bat`，或 `python -m em_rag init` | 默认不索引，确认文档目录后再运行 `python -m em_rag add ./docs` |
| 普通 PDF、Markdown、源码文档 | 保持默认 `pymupdf` PDF 后端 | 不需要额外配置 |
| 扫描件、复杂版式 PDF、表格较多的芯片手册 | 启用 MinerU 强解析 | 安装 MinerU，并设置 `parsing.pdf_backend: "mineru"` |
| MinerU 表格 OCR 太慢或不稳定 | 仍用 MinerU，但关闭表格解析 | 设置 `mineru_args: ["-b", "pipeline", "-m", "txt", "-l", "ch", "-f", "false", "-t", "false"]` |
| 希望检索附带时序图/波形图片 | 使用默认 `pymupdf` 后端的 `figures` 提取 | 配置 `figures.enabled: true`，必要时改 `figures.mode` / `figures.detection` |
| 希望用在线 embedding 提升中文语义召回 | 切换到 GLM 或 OpenAI-compatible embedding | 修改 `embedding.provider` 并重新索引 |
| 多个业务工程共用一套 em_rag | 每个业务工程保留独立 `.em_rag` | 每个工程分别运行 `python -m em_rag init` 和 `add` |
| 工程换电脑或路径变了 | 修复本地路径和 MCP 配置 | 运行 `python -m em_rag repair` 后再 `doctor` |

检查当前工程到底启用了哪些流程：

```bash
python -m em_rag doctor
```

`doctor` 会显示当前 PDF 后端、MinerU 输出目录、图片目录、索引库路径和已索引文档。

需要区分几个目录的用途：

- `.em_rag/chroma_db` / `.em_rag/fts.db`：真正用于检索的向量索引和全文索引。
- `.em_rag/mineru`：MinerU 解析 PDF 后生成的 Markdown、图片和 JSON 中间产物；启用 MinerU 后入库内容来自这里。
- `.em_rag/figures`：默认 PyMuPDF PDF 后端提取的时序图/波形图资产；启用 MinerU 后通常不走这套目录。

给 LLM / Agent 的操作约束见仓库根目录 `AGENTS.md`。同时提供常见客户端入口：
`CLAUDE.md`、`GEMINI.md` 和 `.cursor/rules/em-rag-agent.mdc`。MCP 工具描述中也写明了：
普通问答应先 `list_docs` / `search_docs`，只有用户明确要求新增、重建或刷新索引时才调用 `index_doc`。

## 使用

### 小白快速接入工程

在业务工程目录执行：

```bash
python -m em_rag init
python -m em_rag add ./docs
python -m em_rag doctor
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
重复索引同一个文档时，会先删除同 `doc_id` 的旧向量和全文索引，再写入新结果，
避免 chunk 数量变化后残留旧内容。

如果需要覆盖已存在配置：

```bash
python -m em_rag init --force
```

如果只需要重新生成 MCP 配置：

```bash
python -m em_rag mcp --force
```

如果工程是从另一台电脑拷贝过来的，先执行一次修复：

```bash
python -m em_rag repair
python -m em_rag doctor
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

# 修复旧工程或跨电脑迁移后的路径
python -m em_rag repair

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
      "command": "/path/to/em_rag/.venv/bin/python",
      "args": ["-m", "em_rag.mcp_auto"],
      "cwd": "/path/to/your-project"
    }
  }
}
```

Windows 示例：

```json
{
  "mcpServers": {
    "em-rag": {
      "command": "C:\\path\\to\\em_rag\\.venv\\Scripts\\python.exe",
      "args": ["-m", "em_rag.mcp_auto"],
      "cwd": "C:\\path\\to\\your-project"
    }
  }
}
```

### Cursor

在 Cursor Settings → MCP 中添加，配置同上。

### Codex / 其他 MCP 客户端

任何支持 stdio 传输的 MCP 客户端均可接入，启动命令：

```bash
python -m em_rag.mcp_auto
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
  model_dir: "auto"

parsing:
  pdf_backend: "pymupdf"
  table_strategy: "pdfplumber"
  use_bookmarks: true
  fallback_to_markdown_headings: true
  mineru_command: "mineru"
  mineru_args: []
  mineru_output_dir: "mineru"

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

如果希望使用智谱 GLM 在线 embedding，可改为：

```yaml
embedding:
  provider: "glm"
  api_key_env: "ZHIPU_API_KEY"
  # 如果 MCP 客户端无法继承环境变量，可改用 api_key_file。
  # api_key_file: "zhipu_api_key"
  model: "embedding-3"
  dimensions: 1024
  batch_size: 16
  max_retries: 3
```

然后设置环境变量：

```bash
export ZHIPU_API_KEY="your-api-key"
```

Windows PowerShell:

```powershell
$env:ZHIPU_API_KEY = "your-api-key"
```

如果希望 shell 和 MCP 始终使用同一份 key，或 LLM 客户端启动的 MCP 进程
无法读取 shell 里的环境变量，可以把 key 写入项目本地文件，并在配置中引用。
配置了 `api_key_file` 后，它会优先于环境变量。注意不要提交这个文件：

```bash
printf '%s\n' "your-api-key" > .em_rag/zhipu_api_key
chmod 600 .em_rag/zhipu_api_key
printf '%s\n' "zhipu_api_key" >> .em_rag/.gitignore
```

```yaml
embedding:
  provider: "glm"
  api_key_file: "zhipu_api_key"
  model: "embedding-3"
```

`glm` 是 `openai_compatible` 的便捷别名，默认使用
`https://open.bigmodel.cn/api/paas/v4` 和 `embedding-3`。如果使用其他
OpenAI-compatible embedding 服务，可以显式配置：

```yaml
embedding:
  provider: "openai_compatible"
  api_key_env: "EMBEDDING_API_KEY"
  base_url: "https://example.com/v1"
  model: "your-embedding-model"
```

GLM 默认 `batch_size` 为 16，会自动重试临时网络错误，并在批量请求失败时
自动拆成更小批次继续请求。若 PDF chunk 过长导致服务端返回 400，可适当降低
`chunking.max_tokens` 后重新索引。
如果最终错误里出现 `embedding HTTP 400 for 1 inputs ... preview=...`，说明
单条文本仍被服务端拒绝，可根据预览定位异常 PDF 文本，或继续降低 chunk 大小。

切换 embedding provider、模型或 `dimensions` 后，已有向量索引不能混用；
请换新的 `chroma_path` / `fts_path`，或删除旧文档后重新 `add`。

`storage.*`、`figures.output_dir` 和 `documents.source_dir` 的相对路径会按
配置文件所在目录解析。上例会写入 `your-project/.em_rag/chroma_db`、
`your-project/.em_rag/fts.db` 和 `your-project/.em_rag/figures`。

业务工程 `.mcp.json` 示例：

```json
{
  "mcpServers": {
    "em-rag": {
      "command": "/path/to/em_rag/.venv/bin/python",
      "args": [
        "-m",
        "em_rag.mcp_auto"
      ],
      "cwd": "/path/to/your-project"
    }
  }
}
```

`cwd` 指向业务工程根目录，`mcp_auto` 会自动发现该工程的
`.em_rag/config.yaml`。`.mcp.json` 可通过 `python -m em_rag mcp --force`
生成，不需要手写。

### Codex 全局自动识别工程

如果 Codex 使用全局 `~/.codex/config.toml`，建议只配置一次自动入口：

```toml
[mcp_servers.em-rag]
command = "/path/to/em_rag/.venv/bin/python"
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


### Windows 支持状态

核心 CLI、MCP stdio、项目配置、Chroma 持久化、SQLite FTS、ONNX embedding、
Markdown / 文本 / 代码 / DOCX / EPUB 解析都按跨平台路径实现，Windows 下应可使用。

需要注意的模块：

- SQLite：Windows 默认使用 Python 3.11+ 自带 `sqlite3`，不强制安装
  `pysqlite3-binary`；`doctor` 会检查 `sqlite.fts5`。
- PDF：依赖 `PyMuPDF` 和 `pdfplumber`，请使用 64-bit Python 3.11+，通常可直接安装 wheel。
- ChromaDB：依赖本机 SQLite 版本，若 `doctor` 显示 `sqlite.fts5: missing` 或
  vector store 报错，需要升级 Python 或换用带新版 SQLite 的 Python 发行版。
- MCP 客户端：Windows 路径必须写成 JSON 转义形式，例如
  `C:\\path\\to\\.venv\\Scripts\\python.exe`；推荐直接运行
  `python -m em_rag mcp --force` 自动生成。
- Shell 命令：README 同时提供 bash 和 PowerShell 写法，Windows 下不要使用
  `. .venv/bin/activate` 或 `export`。

提供的 MCP 工具：
- `search_docs` — 搜索已索引文档，支持寄存器名精确查询和语义查询
- `list_docs` — 列出所有已索引文档
- `index_doc` — 索引新文档
- `remove_doc` — 移除已索引文档

## 配置

编辑 `config.yaml` 调整参数：

```yaml
embedding:
  provider: "local"              # "local" | "openai" | "openai_compatible" | "glm"
  local_model: "all-MiniLM-L6-v2"

parsing:
  pdf_backend: "pymupdf"         # "pymupdf" | "mineru"
  table_strategy: "pdfplumber"
  use_bookmarks: true
  mineru_command: "mineru"       # pdf_backend=mineru 时使用
  mineru_output_dir: "./data/mineru"

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

可选强解析：
- MinerU — 复杂 PDF / 扫描件 / 复杂表格的 Markdown 结构化解析。安装 MinerU 后可设置
  `parsing.pdf_backend: "mineru"` 启用；默认仍使用轻量的 `pymupdf` 后端。
