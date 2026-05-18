"""解析器共享工具"""

from __future__ import annotations


def table_to_markdown(table: list[list]) -> str:
    if not table or len(table) < 2:
        return ""
    header = table[0]
    col_count = len(header)
    lines = []
    header_cells = [str(c or "").replace("\n", " ").strip() for c in header]
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
    for row in table[1:]:
        cells = [str(c or "").replace("\n", " ").strip() for c in row[:col_count]]
        while len(cells) < col_count:
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def html_to_elements(html: str, base_context: str = ""):
    """将 HTML 转为 DocElement 列表，供 WebParser 和 EpubParser 共用"""
    from . import DocElement

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("需要安装 beautifulsoup4: pip install beautifulsoup4 lxml")

    soup = BeautifulSoup(html, "lxml")
    content_root = soup.find("article") or soup.find("main") or soup.find("body") or soup
    elements: list[DocElement] = []
    heading_stack: list[str] = [base_context] if base_context else []

    for tag in content_root.find_all(True, recursive=True):
        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag.name[1])
            title = tag.get_text(strip=True)
            if not title:
                continue
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_stack.append(title)
            elements.append(DocElement(
                type="heading", content=title,
                context_chain=" > ".join(heading_stack), level=level,
            ))
        elif tag.name == "table":
            rows = []
            for tr in tag.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if len(rows) >= 2:
                md = table_to_markdown(rows)
                if md:
                    elements.append(DocElement(
                        type="table", content=md,
                        context_chain=" > ".join(heading_stack),
                    ))
        elif tag.name in ("pre", "code") and tag.parent.name != "pre":
            code = tag.get_text()
            if code.strip():
                elements.append(DocElement(
                    type="code", content=code.strip(),
                    context_chain=" > ".join(heading_stack),
                ))
        elif tag.name in ("ul", "ol"):
            items = [li.get_text(strip=True) for li in tag.find_all("li", recursive=False)]
            if items:
                content = "\n".join(f"- {item}" for item in items)
                elements.append(DocElement(
                    type="list", content=content,
                    context_chain=" > ".join(heading_stack),
                ))
        elif tag.name == "p":
            text = tag.get_text(strip=True)
            if text:
                elements.append(DocElement(
                    type="text", content=text,
                    context_chain=" > ".join(heading_stack),
                ))

    return elements
