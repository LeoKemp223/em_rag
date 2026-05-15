"""向后兼容 shim — 新代码请使用 src.parsers"""

from src.parsers import DocElement, create_parser


class DocParser:
    """Lazy PDF parser proxy kept for older imports.

    Importing ``src.parser`` should not require optional PDF dependencies.
    """

    def __new__(cls, *args, **kwargs):
        from src.parsers.pdf_parser import PdfParser

        return PdfParser(*args, **kwargs)


__all__ = ["DocElement", "DocParser", "create_parser"]
