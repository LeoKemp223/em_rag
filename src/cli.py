"""CLI 入口：索引文档、查询、管理"""

import argparse
import sys
import time
from pathlib import Path

from src.config import load_config


SUPPORTED_EXTENSIONS = {".pdf", ".md", ".h", ".c", ".s", ".txt", ".docx", ".epub"}
DEFAULT_PROJECT_CONFIG = ".em_rag/config.yaml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_model_dir() -> str:
    return str((_repo_root() / "models").resolve())


def index_path(path: str, config) -> tuple[str, int]:
    from src.parsers import create_parser
    from src.element_classifier import ElementClassifier
    from src.chunker import Chunker
    from src.embedder import create_embedder
    from src.store import VectorStore, FTSStore

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
    parser = create_parser(path, config.figures)
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
    if not chunks:
        print("\n跳过: 未生成可索引内容")
        return doc_id, 0

    print("  [4/5] Embedding...")
    embedder = create_embedder(config.embedding)
    texts = [c.retrieval_text for c in chunks]
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
    return doc_id, len(chunks)


def cmd_index(args, config):
    index_path(args.path, config)


def cmd_add(args, config):
    targets = _expand_add_targets(args.path)
    if not targets:
        print(f"未找到可索引文档: {args.path}")
        return

    print(f"准备索引 {len(targets)} 个文档")
    ok = 0
    failed = 0
    for target in targets:
        try:
            index_path(str(target), config)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"\n索引失败: {target}\n  {type(exc).__name__}: {exc}")

    print(f"\n批量索引完成: 成功 {ok}, 失败 {failed}")


def _expand_add_targets(path: str) -> list[str | Path]:
    if path.startswith(("http://", "https://")):
        return [path]

    target = Path(path)
    if target.is_file():
        return [target] if target.suffix.lower() in SUPPORTED_EXTENSIONS else []
    if not target.is_dir():
        return []

    results = []
    ignored_parts = {".git", ".venv", ".em_rag", "__pycache__", "node_modules"}
    for item in sorted(target.rglob("*")):
        if not item.is_file():
            continue
        if ignored_parts.intersection(item.parts):
            continue
        if item.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(item)
    return results


def cmd_search(args, config):
    from src.embedder import create_embedder
    from src.store import VectorStore, FTSStore
    from src.retriever import Retriever

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
        if r.related_images:
            print("    关联图片:")
            for image in r.related_images:
                asset = image.get("asset_type", "image")
                confidence = image.get("confidence")
                suffix = f" conf={confidence:.2f}" if isinstance(confidence, (int, float)) else ""
                print(f"      - [{asset}] {image.get('image_path')}{suffix}")
                if image.get("summary"):
                    print(f"        {image['summary'][:240]}")
        print(f"{'─'*60}")
        # 截断过长内容
        content = r.content
        if len(content) > 500:
            content = content[:500] + "\n... (截断)"
        print(content)
        if r.expanded_context:
            print("\n    扩展上下文:")
            for ctx in r.expanded_context[:3]:
                preview = ctx["content"][:180].replace("\n", " ")
                print(
                    f"      - p.{ctx['page'] + 1} {ctx['element_type']} "
                    f"{ctx['context_chain']}: {preview}"
                )

    fts_store.close()


def cmd_list(args, config):
    from src.store import VectorStore

    vector_store = VectorStore(config.storage)
    docs = vector_store.list_docs()
    if not docs:
        print("暂无已索引文档。")
        return
    print("已索引文档:")
    for d in docs:
        print(f"  - {d}")


def cmd_remove(args, config):
    from src.store import VectorStore, FTSStore

    doc_id = args.doc_id
    vector_store = VectorStore(config.storage)
    fts_store = FTSStore(config.storage)

    vector_store.remove_doc(doc_id)
    fts_store.remove_doc(doc_id)
    fts_store.close()
    print(f"已移除文档: {doc_id}")


def cmd_init(args, _config):
    project_root = Path(args.project_root).expanduser().resolve()
    rag_dir = project_root / ".em_rag"
    config_path = rag_dir / "config.yaml"
    mcp_path = project_root / ".mcp.json"
    rag_dir.mkdir(parents=True, exist_ok=True)

    if config_path.exists() and not args.force:
        print(f"已存在: {config_path}")
    else:
        config_path.write_text(_project_config_template(), encoding="utf-8")
        print(f"已写入: {config_path}")

    gitignore_path = rag_dir / ".gitignore"
    if not gitignore_path.exists() or args.force:
        gitignore_path.write_text(
            "chroma_db/\nfts.db\nfigures/\n", encoding="utf-8"
        )
        print(f"已写入: {gitignore_path}")

    if not args.no_mcp:
        if mcp_path.exists() and not args.force:
            print(f"已存在: {mcp_path}")
        else:
            mcp_path.write_text(
                _mcp_config_template(project_root, config_path),
                encoding="utf-8",
            )
            print(f"已写入: {mcp_path}")

    print("\n初始化完成。下一步:")
    print("  python -m em_rag --config .em_rag/config.yaml add ./docs")
    print("  python -m em_rag --config .em_rag/config.yaml doctor")


def cmd_mcp(args, _config):
    project_root = Path(args.project_root).expanduser().resolve()
    config_path = _mcp_config_path(args.config, project_root)
    mcp_path = project_root / ".mcp.json"

    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        print("请先运行: python -m em_rag init")
        sys.exit(1)

    if mcp_path.exists() and not args.force:
        print(f"已存在: {mcp_path}")
        print("如需覆盖，请运行: python -m em_rag mcp --force")
        return

    mcp_path.write_text(
        _mcp_config_template(project_root, config_path),
        encoding="utf-8",
    )
    print(f"已写入: {mcp_path}")


def _mcp_config_path(config_arg: str, project_root: Path) -> Path:
    if config_arg == "config.yaml":
        return (project_root / DEFAULT_PROJECT_CONFIG).resolve()
    config_path = Path(config_arg).expanduser()
    if config_path.is_absolute():
        return config_path
    return config_path.resolve()


def _project_config_template() -> str:
    return f"""embedding:
  provider: "local"
  local_model: "all-MiniLM-L6-v2"
  model_dir: "{_default_model_dir()}"

storage:
  chroma_path: "chroma_db"
  fts_path: "fts.db"

figures:
  enabled: true
  mode: "timing_related"
  detection: "heuristic"
  save_full_page: true
  save_crops: true
  render_dpi: 180
  output_dir: "figures"

retrieval:
  top_k: 5
  keyword_priority: true
  context_expand: true
"""


def _mcp_config_template(project_root: Path, config_path: Path) -> str:
    import json

    payload = {
        "mcpServers": {
            "em-rag": {
                "command": str(_repo_root() / ".venv/bin/python"),
                "args": [
                    "-m",
                    "em_rag.mcp_server",
                    "--config",
                    str(config_path),
                    "--project-root",
                    str(project_root),
                ],
                "cwd": str(_repo_root()),
            }
        }
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def cmd_doctor(args, config):
    print("em_rag doctor")
    print(f"  config: {Path(args.config).expanduser().resolve()}")
    print(f"  chroma: {config.storage.chroma_path}")
    print(f"  fts:    {config.storage.fts_path}")
    print(f"  figs:   {config.figures.output_dir}")
    print(f"  model:  {Path(config.embedding.model_dir) / config.embedding.local_model}")

    checks = [
        ("config", Path(args.config).exists()),
        ("model.onnx", (Path(config.embedding.model_dir) / config.embedding.local_model / "model.onnx").exists()),
        ("tokenizer.json", (Path(config.embedding.model_dir) / config.embedding.local_model / "tokenizer.json").exists()),
    ]
    for name, ok in checks:
        print(f"  {name}: {'ok' if ok else 'missing'}")

    try:
        from src.store import VectorStore
        docs = VectorStore(config.storage).list_docs()
        print(f"  vector store: ok")
        if docs:
            print("  indexed docs:")
            for doc in docs:
                print(f"    - {doc}")
        else:
            print("  indexed docs: none")
    except Exception as exc:
        print(f"  vector store: error ({type(exc).__name__}: {exc})")


def main():
    parser = argparse.ArgumentParser(description="em_rag: 嵌入式开发文档 RAG 系统")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="初始化当前工程的 .em_rag 配置")
    p_init.add_argument("--project-root", default=".", help="业务工程根目录")
    p_init.add_argument("--force", action="store_true", help="覆盖已有配置文件")
    p_init.add_argument("--no-mcp", action="store_true", help="不生成 .mcp.json")

    p_mcp = sub.add_parser("mcp", help="生成当前工程的 .mcp.json")
    p_mcp.add_argument("--project-root", default=".", help="业务工程根目录")
    p_mcp.add_argument("--force", action="store_true", help="覆盖已有 .mcp.json")

    p_add = sub.add_parser("add", help="索引文件或递归索引目录")
    p_add.add_argument("path", help="文档文件、目录或 URL")

    p_index = sub.add_parser("index", help="索引文档")
    p_index.add_argument("path", help="文档路径或 URL")

    p_search = sub.add_parser("search", help="搜索文档")
    p_search.add_argument("query", help="搜索内容")
    p_search.add_argument("--top-k", type=int, default=5, help="返回数量")
    p_search.add_argument("--doc-filter", help="限定文档")

    p_list = sub.add_parser("list", help="列出已索引文档")

    p_remove = sub.add_parser("remove", help="移除文档")
    p_remove.add_argument("doc_id", help="文档 ID")

    p_doctor = sub.add_parser("doctor", help="检查当前工程 RAG 环境")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    config_path = DEFAULT_PROJECT_CONFIG if (
        args.config == "config.yaml" and Path(DEFAULT_PROJECT_CONFIG).exists()
    ) else args.config
    args.config = config_path
    config = load_config(config_path)

    if args.command == "init":
        cmd_init(args, config)
    elif args.command == "mcp":
        cmd_mcp(args, config)
    elif args.command == "add":
        cmd_add(args, config)
    elif args.command == "index":
        cmd_index(args, config)
    elif args.command == "search":
        cmd_search(args, config)
    elif args.command == "list":
        cmd_list(args, config)
    elif args.command == "remove":
        cmd_remove(args, config)
    elif args.command == "doctor":
        cmd_doctor(args, config)


if __name__ == "__main__":
    main()
