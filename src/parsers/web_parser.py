"""网页解析器 — 抓取 URL 并提取文档内容"""

from . import DocElement
from .utils import html_to_elements


class WebParser:
    def parse(self, url: str) -> list[DocElement]:
        try:
            import httpx
        except ImportError:
            raise ImportError("需要安装 httpx: pip install httpx")

        resp = httpx.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()

        from urllib.parse import urlparse
        parsed = urlparse(url)
        base_context = parsed.netloc + parsed.path.rstrip("/")

        elements = html_to_elements(resp.text, base_context)
        for el in elements:
            el.metadata["source_url"] = url

        return elements
