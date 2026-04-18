"""向后兼容 shim — 新代码请使用 src.parsers"""

from src.parsers import DocElement, create_parser
from src.parsers.pdf_parser import PdfParser as DocParser

__all__ = ["DocElement", "DocParser", "create_parser"]
