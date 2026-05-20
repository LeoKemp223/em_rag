from dataclasses import dataclass, field
import os
from pathlib import Path
import yaml


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    local_model: str = "all-MiniLM-L6-v2"
    model_dir: str = "auto"
    model: str = ""
    api_key: str = ""
    api_key_env: str = ""
    api_key_file: str = ""
    base_url: str = ""
    dimensions: int | None = None
    timeout: float = 60.0
    batch_size: int = 0
    max_retries: int = 3
    openai_api_key: str = ""
    openai_model: str = "text-embedding-3-small"


@dataclass
class ParsingConfig:
    pdf_backend: str = "pymupdf"
    table_strategy: str = "pdfplumber"
    use_bookmarks: bool = True
    fallback_to_markdown_headings: bool = True
    mineru_command: str = "mineru"
    mineru_args: list[str] = field(default_factory=list)
    mineru_output_dir: str = "./data/mineru"


@dataclass
class ChunkingConfig:
    max_tokens: int = 1000
    overlap_tokens: int = 100
    keep_tables_intact: bool = True
    split_at_semantic_boundary: bool = True


@dataclass
class StorageConfig:
    chroma_path: str = "./data/chroma_db"
    fts_path: str = "./data/fts.db"


@dataclass
class FiguresConfig:
    enabled: bool = True
    mode: str = "timing_related"
    detection: str = "heuristic"
    save_full_page: bool = True
    save_crops: bool = True
    render_dpi: int = 180
    output_dir: str = "./data/figures"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1"
    llm_api_key: str = ""
    llm_base_url: str = ""
    min_confidence: float = 0.65
    candidate_context_chars: int = 6000


@dataclass
class DocumentsConfig:
    source_dir: str = "./data/documents"


@dataclass
class RetrievalConfig:
    top_k: int = 5
    keyword_priority: bool = True
    context_expand: bool = False


@dataclass
class Config:
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    parsing: ParsingConfig = field(default_factory=ParsingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    figures: FiguresConfig = field(default_factory=FiguresConfig)
    documents: DocumentsConfig = field(default_factory=DocumentsConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


def load_config(config_path: str = "config.yaml") -> Config:
    path = Path(config_path)
    if not path.exists():
        config = Config()
        _resolve_project_paths(config, Path.cwd())
        _resolve_embedding_paths(config, Path.cwd())
        return config

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    config = Config()
    if "embedding" in data:
        config.embedding = EmbeddingConfig(**data["embedding"])
    if "parsing" in data:
        config.parsing = ParsingConfig(**data["parsing"])
    if "chunking" in data:
        config.chunking = ChunkingConfig(**data["chunking"])
    if "storage" in data:
        config.storage = StorageConfig(**data["storage"])
    if "figures" in data:
        config.figures = FiguresConfig(**data["figures"])
    if "documents" in data:
        config.documents = DocumentsConfig(**data["documents"])
    if "retrieval" in data:
        config.retrieval = RetrievalConfig(**data["retrieval"])

    _resolve_project_paths(config, path.parent)
    _resolve_embedding_paths(config, path.parent)
    return config


def _resolve_project_paths(config: Config, base_dir: Path):
    """Resolve project-local paths relative to the config file directory."""
    config.parsing.mineru_output_dir = _resolve_path(
        config.parsing.mineru_output_dir,
        base_dir,
    )
    config.storage.chroma_path = _resolve_path(config.storage.chroma_path, base_dir)
    config.storage.fts_path = _resolve_path(config.storage.fts_path, base_dir)
    config.figures.output_dir = _resolve_path(config.figures.output_dir, base_dir)
    config.documents.source_dir = _resolve_path(config.documents.source_dir, base_dir)


def _resolve_embedding_paths(config: Config, base_dir: Path):
    """Resolve embedding paths while keeping project configs portable across machines."""
    value = config.embedding.model_dir
    if value == "auto":
        env_dir = os.environ.get("EM_RAG_MODEL_DIR")
        config.embedding.model_dir = (
            str(Path(env_dir).expanduser().resolve()) if env_dir else str(default_model_dir())
        )
    else:
        config.embedding.model_dir = _resolve_path(value, base_dir)
    if config.embedding.api_key_file:
        config.embedding.api_key_file = _resolve_path(
            config.embedding.api_key_file,
            base_dir,
        )


def default_model_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "models"


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())
