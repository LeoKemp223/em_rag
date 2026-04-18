"""CLI 入口：索引文档、查询、管理"""

import argparse
import sys
import time
from pathlib import Path

from src.config import load_config
from src.parsers import create_parser
from src.element_classifier import ElementClassifier
from src.chunker import Chunker
from src.embedder import create_embedder
from src.store import VectorStore, FTSStore
from src.retriever import Retriever


def cmd_index(args, config):
    path = args.path
    is_url = path.startswith(("http://", "https://"))

    if not is_url and not Path(path).exists():
        print(f"文件不存在: {path}")
        sys.exit(1)

    if is_url:
        from urllib.parse import urlparse
        parsed = urlparse(path)
        doc_id = (parsed.netloc + parsed.path).strip("/").replace("/", "_").lower()
    else:
        doc_id = Path(path).stem.lower().replace(" ", "_")

    print(f"索引文档: {path}")
    print(f"文档 ID: {doc_id}")

    t0 = time.time()

    print("  [1/5] 解析文档...")
    parser = create_parser(path)
    elements = parser.parse(path)
    print(f"         提取 {len(elements)} 个元素")

    print("  [2/5] 元素分类...")
    classifier = ElementClassifier()
    elements = classifier.classify(elements)
    type_counts = {}
    for el in elements:
        type_counts[el.type] = type_counts.get(el.type, 0) + 1
    print(f"         类型分布: {type_counts}")

    print("  [3/5] 分块...")
    chunker = Chunker(config.chunking)
    chunks = chunker.chunk(elements)
    print(f"         生成 {len(chunks)} 个 chunks")

    print("  [4/5] Embedding...")
    embedder = create_embedder(config.embedding)
    texts = [c.content for c in chunks]
    # 分批处理，避免内存溢出
    batch_size = 64
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings.extend(embedder.embed(batch))
        if len(texts) > batch_size:
            print(f"         {min(i + batch_size, len(texts))}/{len(texts)}")

    print("  [5/5] 存储...")
    vector_store = VectorStore(config.storage)
    vector_store.add_chunks(chunks, embeddings, doc_id)

    fts_store = FTSStore(config.storage)
    fts_store.add_chunks(chunks, doc_id)
    fts_store.close()

    elapsed = time.time() - t0
    print(f"\n索引完成! 耗时 {elapsed:.1f}s, {len(chunks)} chunks")


def cmd_search(args, config):
    embedder = create_embedder(config.embedding)
    vector_store = VectorStore(config.storage)
    fts_store = FTSStore(config.storage)
    retriever = Retriever(config.retrieval, embedder, vector_store, fts_store)

    results = retriever.search(
        args.query,
        top_k=args.top_k,
        doc_filter=args.doc_filter,
    )

    if not results:
        print("未找到相关内容。")
        return

    for i, r in enumerate(results, 1):
        print(f"\n{'='*60}")
        print(f"[{i}] {r.context_chain}")
        print(f"    文档: {r.doc_id} | 页: {r.page + 1} | 类型: {r.element_type} | 来源: {r.source}")
        print(f"    得分: {r.score:.3f}")
        print(f"{'─'*60}")
        # 截断过长内容
        content = r.content
        if len(content) > 500:
            content = content[:500] + "\n... (截断)"
        print(content)

    fts_store.close()


def cmd_list(args, config):
    vector_store = VectorStore(config.storage)
    docs = vector_store.list_docs()
    if not docs:
        print("暂无已索引文档。")
        return
    print("已索引文档:")
    for d in docs:
        print(f"  - {d}")


def cmd_remove(args, config):
    doc_id = args.doc_id
    vector_store = VectorStore(config.storage)
    fts_store = FTSStore(config.storage)

    vector_store.remove_doc(doc_id)
    fts_store.remove_doc(doc_id)
    fts_store.close()
    print(f"已移除文档: {doc_id}")


def main():
    parser = argparse.ArgumentParser(description="em_rag: 嵌入式开发文档 RAG 系统")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    sub = parser.add_subparsers(dest="command")

    p_index = sub.add_parser("index", help="索引文档")
    p_index.add_argument("path", help="文档路径或 URL")

    p_search = sub.add_parser("search", help="搜索文档")
    p_search.add_argument("query", help="搜索内容")
    p_search.add_argument("--top-k", type=int, default=5, help="返回数量")
    p_search.add_argument("--doc-filter", help="限定文档")

    p_list = sub.add_parser("list", help="列出已索引文档")

    p_remove = sub.add_parser("remove", help="移除文档")
    p_remove.add_argument("doc_id", help="文档 ID")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config(args.config)

    if args.command == "index":
        cmd_index(args, config)
    elif args.command == "search":
        cmd_search(args, config)
    elif args.command == "list":
        cmd_list(args, config)
    elif args.command == "remove":
        cmd_remove(args, config)


if __name__ == "__main__":
    main()
