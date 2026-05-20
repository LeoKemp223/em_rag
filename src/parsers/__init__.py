"""多格式文档解析器"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocElement:
    type: str           # "heading" | "text" | "table" | "code" | "list"
    content: str
    context_chain: str  # "SPI > Registers > SPI_CR1"
    level: int = 0
    page: int = 0
    metadata: dict = field(default_factory=dict)


EXTENSION_MAP = {
    ".md": "src.parsers.markdown_parser:MarkdownParser",
    ".h": "src.parsers.code_parser:CodeParser",
    ".c": "src.parsers.code_parser:CodeParser",
    ".s": "src.parsers.code_parser:CodeParser",
    ".txt": "src.parsers.text_parser:TextParser",
    ".docx": "src.parsers.docx_parser:DocxParser",
    ".epub": "src.parsers.epub_parser:EpubParser",
}


def _load_parser(ref: str):
    module_path, class_name = ref.rsplit(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    parser_cls = getattr(mod, class_name)
    return parser_cls()


def _create_pdf_parser(config=None, figures_config=None):
    if figures_config is None and config is not None and not hasattr(config, "pdf_backend"):
        figures_config = config
        config = None

    backend = getattr(config, "pdf_backend", "pymupdf") if config is not None else "pymupdf"
    if backend == "pymupdf":
        from .pdf_parser import PdfParser

        return PdfParser(figures_config)
    if backend == "mineru":
        from .mineru_pdf_parser import MinerUPdfParser

        return MinerUPdfParser(config, figures_config)
    raise ValueError(f"不支持的 PDF 后端: {backend}（支持: pymupdf, mineru）")


def create_parser(path_or_url: str, config=None, figures_config=None):
    if path_or_url.startswith(("http://", "https://")):
        from .web_parser import WebParser
        return WebParser()

    suffix = Path(path_or_url).suffix.lower()
    if suffix == ".pdf":
        return _create_pdf_parser(config, figures_config)

    ref = EXTENSION_MAP.get(suffix)
    if not ref:
        supported = ", ".join(sorted([*EXTENSION_MAP.keys(), ".pdf"]))
        raise ValueError(f"不支持的格式: {suffix}（支持: {supported}, URL）")
    return _load_parser(ref)
