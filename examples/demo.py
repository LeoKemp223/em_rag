"""
em_rag 演示脚本
演示完整流程：解析 → 分类 → 分块 → 向量化 → 存储 → 搜索

示例文档位于 examples/data/ 目录，包含 5 种格式：
  - stc89c52rc_eeprom.pdf   (PDF)
  - stc89c52rc_manual.md    (Markdown)
  - stc89c52rc.h            (C 头文件)
  - stc89c52rc_pinout.txt   (纯文本)
  - led_demo.c              (C 源文件)

运行方式：
    python examples/demo.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent / "data"

SAMPLE_FILES = [
    DATA_DIR / "stc89c52rc_eeprom.pdf",
    DATA_DIR / "stc89c52rc_manual.md",
    DATA_DIR / "stc89c52rc.h",
    DATA_DIR / "stc89c52rc_pinout.txt",
    DATA_DIR / "led_demo.c",
]

QUERIES = [
    "IE 中断允许寄存器",
    "外部中断触发方式",
    "定时器初值计算",
    "串口波特率 9600",
    "看门狗溢出时间",
    "GPIO P3 第二功能",
    "SCON_REN",
    "Timer0_Init",
    "P1.0 引脚功能",
    "LED 流水灯",
    "EEPROM 扇区擦除",
    "ISP_CMD 命令寄存器",
    "EEPROM_Read 函数",
]


def main():
    print("=" * 60)
    print("  em_rag 演示 — 多格式文档索引与搜索")
    print("=" * 60)

    for f in SAMPLE_FILES:
        if not f.exists():
            print(f"示例文件缺失: {f}")
            sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="em_rag_demo_")
    try:
        _run_demo(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"\n临时目录已清理: {tmpdir}")


def _index_file(path, config, classifier, chunker, embedder, vector_store, fts_store):
    from src.parsers import create_parser

    parser = create_parser(str(path), config.figures)
    doc_id = path.stem.lower().replace(" ", "_")

    elements = parser.parse(str(path))
    print(f"  {path.name} ({type(parser).__name__})")
    print(f"    提取 {len(elements)} 个元素")

    elements = classifier.classify(elements)
    type_counts = {}
    for el in elements:
        type_counts[el.type] = type_counts.get(el.type, 0) + 1
    print(f"    类型分布: {type_counts}")

    chunks = chunker.chunk(elements)
    print(f"    生成 {len(chunks)} 个 chunks")

    texts = [c.content for c in chunks]
    embeddings = embedder.embed(texts)

    vector_store.add_chunks(chunks, embeddings, doc_id)
    fts_store.add_chunks(chunks, doc_id)
    return len(chunks)


def _run_demo(tmpdir: str):
    from src.config import load_config
    from src.element_classifier import ElementClassifier
    from src.chunker import Chunker
    from src.embedder import create_embedder
    from src.store import VectorStore, FTSStore
    from src.retriever import Retriever

    config = load_config()
    config.storage.chroma_path = f"{tmpdir}/chroma_db"
    config.storage.fts_path = f"{tmpdir}/fts.db"
    config.figures.output_dir = f"{tmpdir}/figures"

    classifier = ElementClassifier()
    chunker = Chunker(config.chunking)
    embedder = create_embedder(config.embedding)
    vector_store = VectorStore(config.storage)
    fts_store = FTSStore(config.storage)

    print(f"\n索引 {len(SAMPLE_FILES)} 个文档...")
    print("-" * 40)
    total_chunks = 0
    for path in SAMPLE_FILES:
        total_chunks += _index_file(
            path, config, classifier, chunker, embedder, vector_store, fts_store
        )
        print()

    print(f"索引完成: {total_chunks} chunks, 文档列表: {vector_store.list_docs()}")

    retriever = Retriever(config.retrieval, embedder, vector_store, fts_store)

    print("\n" + "=" * 60)
    print("  搜索演示")
    print("=" * 60)

    for query in QUERIES:
        print(f"\n查询: \"{query}\"")
        print("-" * 40)
        results = retriever.search(query, top_k=2)
        if not results:
            print("  无结果")
            continue
        for i, r in enumerate(results, 1):
            content = r.content[:120].replace("\n", " ")
            print(f"  [{i}] {r.context_chain} ({r.doc_id})")
            print(f"      类型: {r.element_type} | 来源: {r.source} | 得分: {r.score:.3f}")
            print(f"      {content}...")

    fts_store.close()
    print("\n演示完成!")


if __name__ == "__main__":
    main()
