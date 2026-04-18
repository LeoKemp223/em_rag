"""EPUB 电子书解析器"""

from pathlib import Path
from . import DocElement
from .utils import html_to_elements


class EpubParser:
    def parse(self, file_path: str) -> list[DocElement]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            import ebooklib
            from ebooklib import epub
        except ImportError:
            raise ImportError("需要安装 ebooklib: pip install ebooklib")

        book = epub.read_epub(file_path)
        elements: list[DocElement] = []

        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            html = item.get_content().decode("utf-8", errors="replace")
            chapter_name = item.get_name().rsplit("/", 1)[-1].rsplit(".", 1)[0]
            chapter_elements = html_to_elements(html, chapter_name)
            elements.extend(chapter_elements)

        return elements
