from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    local_model: str = "all-MiniLM-L6-v2"
    model_dir: str = "./models"
    openai_api_key: str = ""
    openai_model: str = "text-embedding-3-small"


@dataclass
class ParsingConfig:
    table_strategy: str = "pdfplumber"
    use_bookmarks: bool = True
    fallback_to_markdown_headings: bool = True


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
        return Config()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

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

    return config
