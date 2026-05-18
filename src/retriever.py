"""双路检索器：向量相似度 + 关键词精确匹配"""

from __future__ import annotations

import json
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
    related_images: list[dict]
    expanded_context: list[dict]


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
            kw_results = self.fts_store.search(
                keywords, top_k=top_k * 2, doc_filter=doc_filter
            )

        # 融合
        return self._merge(vector_results, kw_results, top_k)

    def _extract_keywords(self, query: str) -> list[str]:
        # 带下划线的复合寄存器名优先匹配: SPI_CR1, GPIO_ODR, RCC_APB2ENR
        compound = r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b'
        # 时序参数: tSU, tHD, tWR, tLOW, tHIGH, tAA, tDH
        timing = r'\bt[A-Z][A-Z0-9.]*\b'
        # 2+ 字符的全大写词: TMOD, TCON, SPI, T2CON, TH0, IE, IP
        single = r'\b[A-Z][A-Z0-9]+\b'
        matches = re.findall(f"{compound}|{timing}|{single}", query)
        domain_terms = [
            "时序", "波形", "应答", "非应答", "应答查询",
            "起始", "停止", "字节写", "页写", "写周期",
            "当前地址读", "随机读", "顺序读", "读操作", "写操作",
            "建立时间", "保持时间",
        ]
        matches.extend(term for term in domain_terms if term in query)
        matches.extend(self._semantic_aliases(query))
        return list(dict.fromkeys(matches))

    def _semantic_aliases(self, query: str) -> list[str]:
        alias_map = {
            "时序": ["timing"],
            "波形": ["waveform"],
            "应答": ["ACK", "acknowledge"],
            "非应答": ["NACK", "no acknowledge"],
            "应答查询": ["ACK", "ACK polling"],
            "起始": ["START", "START condition"],
            "停止": ["STOP", "STOP condition"],
            "字节写": ["byte write"],
            "页写": ["page write"],
            "写周期": ["write cycle", "tWR"],
            "当前地址读": ["current address read"],
            "随机读": ["random read"],
            "顺序读": ["sequential read"],
            "建立时间": ["setup time", "tSU"],
            "保持时间": ["hold time", "tHD"],
        }
        aliases = []
        for term, values in alias_map.items():
            if term in query:
                aliases.extend(values)
        return aliases

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
            related_images=self._parse_related_images(meta.get("related_images", "[]")),
            expanded_context=self._expanded_context(meta, raw["chunk_id"]),
        )

    def _parse_related_images(self, value) -> list[dict]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _expanded_context(self, meta: dict, chunk_id: str) -> list[dict]:
        if not self.config.context_expand:
            return []

        doc_id = meta.get("doc_id", "")
        page = int(meta.get("page", 0) or 0)
        context_chain = meta.get("context_chain", "")
        if not doc_id:
            return []

        nearby = self.fts_store.fetch_context(
            doc_id=doc_id,
            page=page,
            context_chain=context_chain,
            radius=1,
            limit=6,
        )
        expanded = []
        for item in nearby:
            if item["chunk_id"] == chunk_id:
                continue
            item_meta = item.get("metadata", {})
            expanded.append({
                "chunk_id": item["chunk_id"],
                "content": item["content"],
                "context_chain": item_meta.get("context_chain", ""),
                "element_type": item_meta.get("element_type", ""),
                "page": item_meta.get("page", 0),
                "related_images": self._parse_related_images(
                    item_meta.get("related_images", "[]")
                ),
            })
        return expanded
