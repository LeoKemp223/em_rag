"""多格式文档解析器"""

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
    ".pdf": "src.parsers.pdf_parser:PdfParser",
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
    return getattr(mod, class_name)()


def create_parser(path_or_url: str):
    if path_or_url.startswith(("http://", "https://")):
        from .web_parser import WebParser
        return WebParser()

    suffix = Path(path_or_url).suffix.lower()
    ref = EXTENSION_MAP.get(suffix)
    if not ref:
        supported = ", ".join(sorted(EXTENSION_MAP.keys()))
        raise ValueError(f"不支持的格式: {suffix}（支持: {supported}, URL）")
    return _load_parser(ref)
