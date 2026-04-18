# em_rag：嵌入式开发文档 RAG 系统

## 定位

面向嵌入式开发者的轻量本地 RAG，基于标准 MCP 协议，可集成到任何支持 MCP 的 AI 编程工具（Claude Code、Cursor、Codex 等），让 AI 编程时能自动查阅芯片手册和 API 文档。

## 核心问题

嵌入式开发中 AI 编程效率低的根本原因：
1. 芯片手册是 PDF，AI 无法直接读取
2. 寄存器定义、时序要求等关键信息散落在文档各处
3. 不同外设间存在依赖关系（如 SPI 需要配置 GPIO、时钟、DMA），跨章节查找困难

## 设计原则

- **轻量优先**：最小依赖，CPU 可运行，< 200MB 安装体积
- **先跑通再优化**：Phase 1 就能用，后续迭代增强
- **嵌入式场景专注**：针对寄存器表、外设配置等场景优化

---

## 架构

```
┌───────────────────────────────────────────────┐
│            Claude Code / IDE                  │
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
│  PyMuPDF/pdfplumber → Element Classifier      │
│       → Chunker → ONNX Embedder → ChromaDB   │
└───────────────────────────────────────────────┘
```

---

## 数据流

```
文档导入：
  PDF
    → PyMuPDF 提取文本 + 页码 + 书签结构
    → pdfplumber 提取表格（精确行列）
    → 双路合并：文本用 PyMuPDF，表格用 pdfplumber 替换对应区域
    → 元素分类（标题/文本/表格/代码/列表）
    → 构建 context_chain（层级标题链）
    → 元素感知分块（表格不拆分，章节边界主动切分）
    → ONNX Embedding 向量化
    → 存入 ChromaDB（chunk + 元数据）+ SQLite（全文索引）

查询：
  用户 query
    → 提取精确关键词（寄存器名等大写_下划线模式）
    → 双路并行：
       · ChromaDB 向量相似度检索
       · SQLite FTS5 全文匹配
    → 结果融合（关键词命中优先，向量补充）
    → 按 context_chain 补充上下文
    → 返回 top_k 结果
```

---

## 模块设计

### 1. 文档解析（PyMuPDF + pdfplumber 双通道）

PyMuPDF（fitz）负责主体提取，pdfplumber 负责表格提取：

```python
class DocParser:
    def parse(self, pdf_path: str) -> list[DocElement]:
        # 通道 1：PyMuPDF 提取全文本 + 页码 + 书签结构
        doc = fitz.open(pdf_path)
        bookmarks = self._extract_bookmarks(doc)
        pages_text = self._extract_pages(doc)

        # 通道 2：pdfplumber 提取所有表格（行列精确）
        tables = self._extract_tables(pdfplumber.open(pdf_path))

        # 合并：表格区域用 pdfplumber 结果替换 PyMuPDF 文本
        return self._merge(pages_text, tables, bookmarks)
```

**为什么双通道**：
- PyMuPDF 文本提取快（< 1s/百页），支持书签/目录结构，但表格会变成乱序文本
- pdfplumber 表格提取精确（保留行列结构），但全文提取慢
- 两者互补，各自发挥优势

**表格提取后处理**：

```python
def _table_to_markdown(self, table) -> str:
    """将 pdfplumber 表格转为 Markdown 格式"""
    rows = table.extract()
    if not rows:
        return ""
    header = rows[0]
    md_lines = ["| " + " | ".join(str(c or "") for c in header) + " |"]
    md_lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows[1:]:
        md_lines.append("| " + " | ".join(str(c or "") for c in row) + " |")
    return "\n".join(md_lines)
```

### 2. 元素分类器（Context-Aware Processing）

解析合并后的内容，识别元素类型并构建上下文。

借鉴 [RAG-Anything](https://github.com/HKUDS/RAG-Anything) 的上下文感知处理：不直接粗暴分块，而是先识别元素类型，分类处理，保留元素间关系。

```python
@dataclass
class DocElement:
    type: str           # "heading" | "text" | "table" | "code" | "list"
    content: str        # 原始内容
    context_chain: str  # "SPI > Registers > SPI_CR1"
    level: int          # 标题层级（仅 heading）
    page: int           # 页码
    metadata: dict      # 附加信息（表格列数等）
```

关键逻辑：
- 利用 PyMuPDF 提取的书签结构作为 context_chain 骨架（比 Markdown `#` 解析更可靠）
- 遇到标题级别变化时，检查是否产生语义边界
- 表格类型标记 `element_type: "table"`，记录列数、行数
- 无书签时 fallback 到 Markdown 标题解析

### 3. 分块策略（Element-Aware Chunking）

| 元素类型 | 分块规则 |
|----------|----------|
| Table | 整表为一个 chunk，前置 context_chain + 表前说明文字 |
| Text | 按段落分块，同一小节内合并至 max_tokens，章节结尾处强制切分 |
| Code | 整块为一个 chunk |
| List | 完整列表为一个 chunk |

**语义边界检测**：

```python
def should_split(current_elements, new_element) -> bool:
    """在以下情况主动切分，避免跨主题合并"""
    # 1. 标题层级回退（主题切换）
    if new_element.type == "heading" and new_element.level <= current_level:
        return True
    # 2. 元素类型突变（非表格→表格，可能是新寄存器开始）
    if new_element.type == "table" and last_type != "table":
        return True
    # 3. 超过 max_tokens
    if current_tokens + new_element.tokens > max_tokens:
        return True
    return False
```

每个 chunk 的元数据：
```python
{
    "doc_id": "stm32f4_ref_manual",
    "doc_name": "STM32F4 Reference Manual",
    "context_chain": "SPI > Registers > SPI_CR1",
    "element_type": "table",
    "page": 876,
    "keywords": ["SPI_CR1", "BR", "CPOL", "CPHA"],
}
```

### 4. Embedding（ONNX 轻量化）

用 ONNX Runtime 替代 PyTorch，体积从 300MB+ 降到 ~60MB：

```python
class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.session = onnxruntime.InferenceSession(model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        inputs = self.tokenizer(texts, padding=True, truncation=True, return_tensors="np")
        outputs = self.session.run(None, dict(inputs))
        return mean_pool(outputs, inputs["attention_mask"])
```

模型选择：

| 场景 | 模型 | 大小 | 说明 |
|------|------|------|------|
| 英文文档（芯片手册） | all-MiniLM-L6-v2 (ONNX) | ~30MB | 通用，速度快 |
| 中文文档 | bge-small-zh-v1.5 (ONNX) | ~40MB | 中文优化 |
| 云端（可选） | text-embedding-3-small | 0MB | API 调用，需联网 |

> 注意：tokenizer 建议用 `tokenizers` 库（~5MB）直接加载，避免 `transformers` 库（~50MB）拉入 PyTorch 依赖。

### 5. 检索（向量 + 关键词双路）

```python
class Retriever:
    def search(self, query: str, top_k: int = 5) -> list[Result]:
        # 1. 提取精确关键词（寄存器名、外设名）
        keywords = self._extract_keywords(query)

        # 2. 双路并行检索
        vector_results = self.chroma.search(query_embedding, top_k=top_k * 2)
        fts_results = self.sqlite_fts.search(keywords, top_k=top_k) if keywords else []

        # 3. 融合：关键词命中优先，向量补充
        return self._merge_results(vector_results, fts_results, top_k)

    def _extract_keywords(self, query: str) -> list[str]:
        """提取寄存器名、外设名等精确匹配模式"""
        register_pattern = r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b'
        peripheral_pattern = r'\b(?:SPI|GPIO|UART|USART|TIM|I2C|DMA|ADC|DAC|RTC|WWDG|IWDG)\b'
        return re.findall(f"{register_pattern}|{peripheral_pattern}", query)

    def _merge_results(self, vector_res, kw_res, top_k):
        """关键词命中优先，向量补充"""
        seen = set()
        results = []
        for r in kw_res:
            if r.chunk_id not in seen:
                results.append(r)
                seen.add(r.chunk_id)
        for r in vector_res:
            if r.chunk_id not in seen:
                results.append(r)
                seen.add(r.chunk_id)
        return results[:top_k]
```

### 6. MCP Server

```python
tools = [
    {
        "name": "search_docs",
        "description": "搜索已索引的技术文档。支持寄存器名精确查询和语义查询。",
        "parameters": {
            "query": "搜索内容",
            "top_k": "返回数量，默认5",
            "doc_filter": "限定文档名（可选）"
        }
    },
    {
        "name": "list_docs",
        "description": "列出所有已索引文档"
    },
    {
        "name": "index_doc",
        "description": "索引新文档",
        "parameters": { "path": "文档路径" }
    },
    {
        "name": "remove_doc",
        "description": "移除已索引文档",
        "parameters": { "doc_id": "文档ID" }
    }
]
```

---

## 项目结构

```
em_rag/
├── src/
│   ├── __init__.py
│   ├── config.py              # 配置加载
│   ├── parser.py              # PyMuPDF + pdfplumber 双通道解析
│   ├── element_classifier.py  # 元素分类 + context_chain
│   ├── chunker.py             # 元素感知分块 + 语义边界检测
│   ├── embedder.py            # ONNX Embedding
│   ├── store.py               # ChromaDB + SQLite 双存储
│   ├── retriever.py           # 向量 + 关键词双路检索
│   ├── mcp_server.py          # MCP Server
│   └── cli.py                 # CLI 入口
├── models/                    # ONNX 模型文件（gitignored）
├── config.yaml
├── requirements.txt
└── data/
    ├── documents/             # 原始文档
    ├── chroma_db/             # 向量数据库
    └── fts.db                 # SQLite 全文索引
```

---

## 依赖

```txt
# 核心依赖（总计 ~80MB）
PyMuPDF>=1.24.0               # PDF 文本提取 + 书签，~15MB
pdfplumber>=0.11.0             # PDF 表格提取，~5MB
chromadb>=0.4.0                # 向量存储，~30MB
onnxruntime>=1.17.0            # 推理引擎（CPU），~30MB
tokenizers>=0.15.0             # HuggingFace tokenizer（轻量，~5MB）
mcp>=1.0.0                     # MCP SDK
pyyaml
```

可选：
```txt
openai>=1.0.0                  # 云端 embedding
networkx>=3.0                  # Phase 2 知识图谱
jieba>=0.42.0                  # Phase 2 中文 FTS 分词
```

---

## 实施计划

### Phase 1：最小可用（MVP）— 6 天

目标：能索引一份 STM32 芯片手册 PDF，通过 MCP 在 Claude Code 中精确查询寄存器信息。

| 天 | 任务 | 验收标准 |
|----|------|----------|
| D1 | 项目骨架 + config + PDF 解析验证 | 用真实 STM32 手册跑通 PyMuPDF+pdfplumber，表格提取率 > 80% |
| D2 | 元素分类器 + context_chain（书签结构） | 输出的 DocElement 列表层级正确 |
| D3 | 分块器 + ONNX Embedding + ChromaDB 存储 | 索引完整手册，chunk 质量肉眼可验 |
| D4 | SQLite FTS5 全文索引 + 双路检索器 | 查询 `SPI_CR1` 能精确命中对应 chunk |
| D5 | MCP Server + CLI | `search_docs` 和 `index_doc` 功能可用 |
| D6 | 集成测试 + 解析调优 | 在 Claude Code 中实际使用，修复边界问题 |

> D1 是关键验证点：如果 PyMuPDF+pdfplumber 对目标文档效果差，需在此日切换备选方案。

### Phase 2：增强检索 — 按需

- context_chain 上下文扩展（命中 chunk 后拉取同章节内容）
- 关键词 + 向量混合检索权重调优
- 图片/时序图处理（VLM 描述或 OCR 提取）
- 轻量知识图谱（NetworkX + JSON，捕获外设间依赖关系）
- Reranking（Cross-encoder 或 LLM rerank）
- 增量索引
- 中文 FTS 分词优化（jieba）

### Phase 3：体验优化 — 按需

- 文档管理 Web UI
- 多文档关联查询
- 表格结构化提取增强
- 文档版本管理

---

## 配置

```yaml
# config.yaml
embedding:
  provider: "local"                              # "local" | "openai" | "zhipu"
  local_model: "all-MiniLM-L6-v2"                # ONNX 格式
  # openai_api_key: "sk-..."
  # openai_model: "text-embedding-3-small"

parsing:
  table_strategy: "pdfplumber"                   # 表格提取引擎
  use_bookmarks: true                            # 用书签构建 context_chain
  fallback_to_markdown_headings: true            # 无书签时用 Markdown # 标题

chunking:
  max_tokens: 1000
  overlap_tokens: 100
  keep_tables_intact: true
  split_at_semantic_boundary: true               # 语义边界主动切分

storage:
  chroma_path: "./data/chroma_db"
  fts_path: "./data/fts.db"

documents:
  source_dir: "./data/documents"

retrieval:
  top_k: 5
  keyword_priority: true                         # 关键词命中优先
  context_expand: false                          # Phase 2 开启
```

---

## 使用示例

```bash
# 索引文档
python -m em_rag index ./data/documents/STM32F4_Reference_Manual.pdf
python -m em_rag index ./data/documents/FreeRTOS_API_Reference.pdf

# CLI 查询测试
python -m em_rag search "SPI_CR1 寄存器各位域含义"
python -m em_rag search "FreeRTOS xTaskCreate 参数说明"
python -m em_rag search "GPIOA 时钟使能"

# 列出已索引文档
python -m em_rag list

# 删除文档
python -m em_rag remove stm32f4_ref_manual

# Claude Code 中自动使用（配置 MCP 后）
# 开发者写代码时，Claude 自动调用 search_docs 获取文档上下文
```

---

## 与 RAG-Anything 的关系

借鉴 [RAG-Anything](https://github.com/HKUDS/RAG-Anything) 核心思想，轻量化实现：

| 思想 | RAG-Anything | em_rag 实现 |
|------|-------------|-------------|
| 上下文感知 | 元素级分类 + VLM 描述 | 元素分类 + context_chain + 书签结构 |
| 结构保留 | LightRAG 知识图谱 | 元数据 + context_chain（Phase 1）→ NetworkX（Phase 2） |
| 多模态 | Docling + Vision Model | PyMuPDF + pdfplumber（表格精确提取） |
| 检索增强 | 双层图谱检索 | 向量 + 关键词双路检索（Phase 1）→ 图谱（Phase 2） |

核心取舍：放弃重型多模态处理和完整知识图谱，换取轻量部署（~80MB vs >2GB）和快速落地。Phase 2 按实际效果决定是否引入图谱。

---

## 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| PyMuPDF+pdfplumber 对某些 PDF 表格效果差 | 索引质量下降 | D1 验证；备选：纯 pdfplumber 模式或 `camelot` |
| ONNX 模型对嵌入式术语 embedding 质量不够 | 检索召回率低 | 准备 bge-base 系列作为备选；Phase 2 微调 |
| 书签结构缺失或不完整 | context_chain 不准 | fallback 到 Markdown 标题解析 |
| SQLite FTS5 中文分词不佳 | 中文查询关键词匹配差 | Phase 2 用 jieba 分词后存入 FTS |
