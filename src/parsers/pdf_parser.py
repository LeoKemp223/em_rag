"""双通道 PDF 解析：PyMuPDF（文本+书签） + pdfplumber（表格）"""

from pathlib import Path

import fitz
import pdfplumber

from . import DocElement
from .utils import table_to_markdown


class PdfParser:
    def parse(self, pdf_path: str) -> list[DocElement]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"不是 PDF 格式: {path.suffix}")

        doc = fitz.open(pdf_path)
        bookmarks = self._extract_bookmarks(doc)
        pages_text = self._extract_pages(doc)
        doc.close()

        tables_by_page = self._extract_tables(pdf_path)
        return self._merge(pages_text, tables_by_page, bookmarks)

    def _extract_bookmarks(self, doc: fitz.Document) -> list[dict]:
        toc = doc.get_toc(simple=True)
        return [{"level": level, "title": title.strip(), "page": page - 1}
                for level, title, page in toc]

    def _extract_pages(self, doc: fitz.Document) -> list[dict]:
        return [{"page": i, "text": doc[i].get_text("text")} for i in range(len(doc))]

    def _extract_tables(self, pdf_path: str) -> dict[int, list[str]]:
        tables_by_page: dict[int, list[str]] = {}
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    md_tables = [table_to_markdown(t) for t in tables]
                    md_tables = [m for m in md_tables if m]
                    if md_tables:
                        tables_by_page[page_num] = md_tables
        return tables_by_page

    def _merge(
        self,
        pages_text: list[dict],
        tables_by_page: dict[int, list[str]],
        bookmarks: list[dict],
    ) -> list[DocElement]:
        elements: list[DocElement] = []
        heading_stack: list[str] = []
        bookmark_map: dict[int, list[dict]] = {}
        for bm in bookmarks:
            bookmark_map.setdefault(bm["page"], []).append(bm)

        for page_info in pages_text:
            page_num = page_info["page"]
            text = page_info["text"]

            for bm in bookmark_map.get(page_num, []):
                self._update_heading_stack(heading_stack, bm["level"], bm["title"])
                elements.append(DocElement(
                    type="heading",
                    content=bm["title"],
                    context_chain=" > ".join(heading_stack),
                    level=bm["level"],
                    page=page_num,
                ))

            for table_md in tables_by_page.get(page_num, []):
                elements.append(DocElement(
                    type="table",
                    content=table_md,
                    context_chain=" > ".join(heading_stack),
                    page=page_num,
                    metadata={"row_count": table_md.count("\n")},
                ))

            text_content = text.strip()
            if text_content:
                elements.append(DocElement(
                    type="text",
                    content=text_content,
                    context_chain=" > ".join(heading_stack),
                    page=page_num,
                ))

        return elements

    def _update_heading_stack(self, stack: list[str], level: int, title: str):
        while len(stack) >= level:
            stack.pop()
        stack.append(title)
