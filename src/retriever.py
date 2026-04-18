"""双路检索器：向量相似度 + 关键词精确匹配"""

import re
from dataclasses import dataclass

from src.config import RetrievalConfig
from src.embedder import EmbedderProtocol
from src.store import VectorStore, FTSStore


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    context_chain: str
    element_type: str
    page: int
    doc_id: str
    score: float
    source: str  # "vector" | "keyword" | "both"


class Retriever:
    def __init__(
        self,
        config: RetrievalConfig,
        embedder: EmbedderProtocol,
        vector_store: VectorStore,
        fts_store: FTSStore,
    ):
        self.config = config
        self.embedder = embedder
        self.vector_store = vector_store
        self.fts_store = fts_store

    def search(
        self, query: str, top_k: int = None, doc_filter: str = None
    ) -> list[SearchResult]:
        top_k = top_k or self.config.top_k
        keywords = self._extract_keywords(query)

        # 向量检索
        query_embedding = self.embedder.embed([query])[0]
        vector_results = self.vector_store.search(
            query_embedding, top_k=top_k * 2, doc_filter=doc_filter
        )

        # 关键词检索
        kw_results = []
        if keywords:
            kw_results = self.fts_store.search(keywords, top_k=top_k)

        # 融合
        return self._merge(vector_results, kw_results, top_k)

    def _extract_keywords(self, query: str) -> list[str]:
        # 带下划线的复合寄存器名优先匹配: SPI_CR1, GPIO_ODR, RCC_APB2ENR
        compound = r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b'
        # 2+ 字符的全大写词: TMOD, TCON, SPI, T2CON, TH0, IE, IP
        single = r'\b[A-Z][A-Z0-9]+\b'
        matches = re.findall(f"{compound}|{single}", query)
        return list(set(matches))

    def _merge(
        self, vector_results: list[dict], kw_results: list[dict], top_k: int
    ) -> list[SearchResult]:
        seen: set[str] = set()
        results: list[SearchResult] = []

        kw_ids = {r["chunk_id"] for r in kw_results}

        if self.config.keyword_priority:
            for r in kw_results:
                if r["chunk_id"] not in seen:
                    seen.add(r["chunk_id"])
                    results.append(self._to_result(r, "keyword"))

        for r in vector_results:
            if r["chunk_id"] not in seen:
                seen.add(r["chunk_id"])
                source = "both" if r["chunk_id"] in kw_ids else "vector"
                results.append(self._to_result(r, source))

        return results[:top_k]

    def _to_result(self, raw: dict, source: str) -> SearchResult:
        meta = raw.get("metadata", {})
        return SearchResult(
            chunk_id=raw["chunk_id"],
            content=raw["content"],
            context_chain=meta.get("context_chain", ""),
            element_type=meta.get("element_type", "text"),
            page=meta.get("page", 0),
            doc_id=meta.get("doc_id", ""),
            score=1.0 - raw.get("distance", 0.0),
            source=source,
        )
